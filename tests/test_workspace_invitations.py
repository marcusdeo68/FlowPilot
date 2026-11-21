import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from flowpilot_api.access import Role
from flowpilot_api.membership_service import (
    InvitationConflict,
    MemberNotFound,
    MembershipConflict,
    MembershipService,
)
from flowpilot_api.work_service import Principal
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.postgres


def test_invitation_api_requires_recipient_consent_and_exact_version(workspace_client, setup):
    client, workspace, other, users, sign = workspace_client
    service, _, _, _ = setup

    def auth(subject, **overrides):
        return {"Authorization": "Bearer " + sign(subject, overrides=overrides)}

    owner, recipient, outsider = (auth(name) for name in ("owner", "invitee", "outsider"))
    base = f"/api/v2/workspaces/{workspace}"
    assert client.get("/api/v2/me", headers=recipient).status_code == 404
    read_only = auth("invitee", scope="flowpilot:read")
    assert client.post("/api/v2/me", headers=read_only).status_code == 403
    profile = client.post("/api/v2/me", headers=recipient)
    assert profile.status_code == 200
    assert client.post("/api/v2/me", headers=recipient).json() == profile.json()
    target = profile.json()["id"]
    offer_cmd = {"user_id": target, "role": "observer"}
    assert (
        client.post(base + "/invitations", headers=auth("member"), json=offer_cmd).status_code
        == 403
    )
    assert client.get(base + "/invitations", headers=recipient).status_code == 403
    offered = client.post(base + "/invitations", headers=owner, json=offer_cmd)
    assert offered.status_code == 201
    invite = offered.json()
    assert (invite["status"], invite["version"], invite["role"]) == ("pending", 1, "observer")
    assert client.get("/api/v2/workspaces", headers=recipient).json() == []
    assert client.get(base, headers=recipient).status_code == 403
    assert client.get(base + "/work", headers=recipient).status_code == 403
    assert client.get("/api/v2/invitations", headers=recipient).json() == [invite]
    assert client.get("/api/v2/invitations", headers=outsider).json() == []
    assert client.get(base + "/invitations", headers=owner).json() == [invite]
    assert client.post(base + "/invitations", headers=owner, json=offer_cmd).status_code == 409
    bad_revoke = f"/api/v2/workspaces/{other}/invitations/{invite['id']}/revoke"
    assert (
        client.post(bad_revoke, headers=outsider, json={"expected_version": 1}).status_code == 404
    )
    decision = f"/api/v2/invitations/{invite['id']}/decision"
    answer = {"decision": "accept", "expected_version": 1}
    assert client.post(decision, headers=outsider, json=answer).status_code == 404
    assert client.post(decision, headers=read_only, json=answer).status_code == 403
    assert (
        client.post(decision, headers=recipient, json={**answer, "expected_version": 2}).status_code
        == 409
    )
    assert (
        client.post(
            decision, headers=recipient, json={**answer, "expected_version": True}
        ).status_code
        == 422
    )
    accepted = client.post(decision, headers=recipient, json=answer)
    assert accepted.status_code == 200
    assert accepted.json() == {**invite, "status": "accepted", "version": 2}
    assert client.post(decision, headers=recipient, json=answer).status_code == 409
    assert client.get("/api/v2/invitations", headers=recipient).json() == []
    assert client.get(base + "/work", headers=recipient).status_code == 200
    assert client.get(base, headers=recipient).json() == {
        "id": str(workspace),
        "name": "Synthetic A",
        "role": "observer",
    }
    member = [
        item
        for item in client.get(base + "/members", headers=owner).json()
        if item["user_id"] == target
    ]
    assert member == [{"user_id": target, "role": "observer", "active": True, "version": 1}]
    with service.engine.begin() as connection:
        events = connection.execute(
            text("SELECT operation, actor_id::text FROM invitation_events ORDER BY version")
        ).all()
    assert events == [("created", str(users["owner"])), ("accepted", target)]


def test_invitation_expiry_and_inviter_version_cannot_revive_stale_authority(setup):
    work, workspace, _, users = setup
    service = MembershipService(work.engine)
    owner = Principal("test", "owner")
    second = Principal("test", "member")
    recipient = Principal("test", "invitee")
    eligible = service.register_profile(recipient).id
    foreign = service.register_profile(Principal("other-issuer", "invitee")).id
    for missing in (foreign, uuid4()):
        with pytest.raises(MemberNotFound):
            service.invite(owner, workspace, missing, role=Role.OBSERVER)
    service.change_member(
        owner, workspace, users["member"], role=Role.OWNER, active=True, expected_version=1
    )
    offered = service.invite(owner, workspace, eligible, role=Role.MEMBER)
    service.change_member(
        second, workspace, users["owner"], role=Role.MEMBER, active=True, expected_version=1
    )
    service.change_member(
        second, workspace, users["owner"], role=Role.OWNER, active=True, expected_version=2
    )
    assert service.invitations(recipient) == []
    with pytest.raises(InvitationConflict):
        service.decide_invitation(recipient, offered.id, decision="accept", expected_version=1)
    revoked = service.revoke_invitation(second, workspace, offered.id, expected_version=1)
    assert revoked.status == "revoked" and revoked.version == 2
    expiring = service.invite(second, workspace, eligible, role=Role.OBSERVER)
    with work.engine.begin() as connection:
        connection.execute(
            text("""UPDATE workspace_invitations
            SET created_at=now()-INTERVAL '8 days', expires_at=now()-INTERVAL '1 day'
            WHERE id=:id"""),
            {"id": expiring.id},
        )
    with pytest.raises(InvitationConflict):
        service.decide_invitation(recipient, expiring.id, decision="decline", expected_version=1)
    valid = service.invite(second, workspace, eligible, role=Role.OWNER)
    assert service.invitations(recipient) == [valid]
    assert (
        service.decide_invitation(
            recipient, valid.id, decision="decline", expected_version=1
        ).status
        == "declined"
    )
    assert service.list_workspaces(recipient) == []


def test_invitation_terminal_state_and_membership_audit_commit_together(setup, pg):
    work, workspace, _, _ = setup
    service = MembershipService(work.engine)
    owner = Principal("test", "owner")
    recipient = Principal("test", "invitee")
    target = service.register_profile(recipient).id
    offered = service.invite(owner, workspace, target, role=Role.MEMBER)
    with work.engine.begin() as connection:
        connection.execute(
            text("""CREATE FUNCTION fail_member_added() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'forced member audit failure'; END; $$""")
        )
        connection.execute(
            text("""CREATE TRIGGER fail_member_added BEFORE INSERT ON workspace_events
            FOR EACH ROW WHEN (NEW.operation = 'member_added') EXECUTE FUNCTION fail_member_added()""")
        )
    with pytest.raises(DBAPIError, match="forced member audit failure"):
        service.decide_invitation(recipient, offered.id, decision="accept", expected_version=1)
    assert service.list_workspaces(recipient) == []
    assert service.invitations(recipient) == [offered]
    with work.engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM invitation_events")).scalar_one() == 1
        connection.execute(text("DROP TRIGGER fail_member_added ON workspace_events"))
    with pytest.raises(DBAPIError), work.engine.begin() as connection:
        connection.execute(text("DELETE FROM invitation_events"))
    _, config = pg
    with pytest.raises(IntegrityError, match="Cannot downgrade while workspace invitations exist"):
        with work.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0008_private_notes")

    service.add_member(owner, workspace, target, role=Role.OBSERVER)
    assert service.invitations(recipient) == []
    with pytest.raises(MembershipConflict):
        service.decide_invitation(recipient, offered.id, decision="accept", expected_version=1)
    assert service.invitations(owner, workspace_id=workspace) == [offered]
    assert service.list_workspaces(recipient)[0].role == Role.OBSERVER


def test_acceptance_racing_revocation_has_one_terminal_result(setup):
    work, workspace, _, _ = setup
    service = MembershipService(work.engine)
    owner = Principal("test", "owner")
    recipient = Principal("test", "invitee")
    offered = service.invite(
        owner, workspace, service.register_profile(recipient).id, role=Role.MEMBER
    )
    both = Barrier(2)

    def race(action):
        both.wait(timeout=10)
        try:
            return action().status
        except InvitationConflict:
            return "conflict"

    with ThreadPoolExecutor(2) as pool:
        accept = pool.submit(
            race,
            lambda: service.decide_invitation(
                recipient, offered.id, decision="accept", expected_version=1
            ),
        )
        revoke = pool.submit(
            race,
            lambda: service.revoke_invitation(owner, workspace, offered.id, expected_version=1),
        )
        results = [accept.result(timeout=15), revoke.result(timeout=15)]
    assert results.count("conflict") == 1
    assert bool(service.list_workspaces(recipient)) == ("accepted" in results)
    with work.engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM invitation_events")).scalar_one() == 2


def test_invitation_expiry_is_checked_after_waiting_on_an_unchanged_row(setup):
    work, workspace, _, _ = setup
    service = MembershipService(work.engine)
    owner = Principal("test", "owner")
    recipient = Principal("test", "invitee")
    offered = service.invite(
        owner, workspace, service.register_profile(recipient).id, role=Role.MEMBER
    )
    with work.engine.begin() as connection:
        connection.execute(
            text("""UPDATE workspace_invitations
            SET expires_at=clock_timestamp()+INTERVAL '2 seconds' WHERE id=:id"""),
            {"id": offered.id},
        )
    with ThreadPoolExecutor(max_workers=1) as pool:
        with work.engine.begin() as blocker:
            blocker.execute(text("SELECT id FROM workspace_invitations FOR UPDATE")).all()
            pid = blocker.execute(text("SELECT pg_backend_pid()")).scalar_one()
            decision = pool.submit(
                service.decide_invitation,
                recipient,
                offered.id,
                decision="accept",
                expected_version=1,
            )
            deadline = time.monotonic() + 1.5
            with work.engine.connect() as observer:
                while not observer.execute(
                    text("""SELECT EXISTS (SELECT 1 FROM pg_locks
                    WHERE NOT granted AND pid IS NOT NULL AND :pid = ANY(pg_blocking_pids(pid)))"""),
                    {"pid": pid},
                ).scalar_one():
                    assert time.monotonic() < deadline, (
                        "Invitation decision never waited on its locked row"
                    )
                    time.sleep(0.01)
            blocker.execute(text("SELECT pg_sleep(2.1)"))
        with pytest.raises(InvitationConflict):
            decision.result(timeout=5)
    assert service.list_workspaces(recipient) == []
