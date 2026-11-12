from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from flowpilot_api.access import AccessDenied
from flowpilot_api.proposals import (
    Correction,
    ProposalNotFound,
    ProposalService,
    Review,
    ReviewConflict,
)
from flowpilot_api.work_service import ManualSource, Principal, SourceNotFound
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "  "},
        {"title": "bad\x00title"},
        {"expected_version": True},
        {"owner_id": "me"},
    ],
)
def test_correction_rejects_invalid_or_authority_fields(fields):
    with pytest.raises(ValidationError):
        Correction.model_validate(
            {"title": "Task", "due_date": None, "expected_version": 1, **fields}
        )


@pytest.fixture
def scenario(setup):
    work, ws, other, users = setup
    p = Principal("test", "member")
    src = work.create_source(
        p,
        ws,
        ManualSource(reference="manual:1", summary="Review sample", excerpt="Private context"),
    )
    return ProposalService(work.engine), work, ws, other, users, p, src


@pytest.mark.postgres
def test_suggestion_retries_and_terminal_dismissal(scenario):
    proposals, work, ws, _, _, p, src = scenario
    barrier = Barrier(2)

    def suggest(_):
        barrier.wait(timeout=10)
        return proposals.suggest(p, ws, src)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.map(suggest, range(2))
    assert a == b and work.list_work(p, ws) == []
    closed = proposals.review(p, ws, a.id, Review(decision="dismiss", expected_version=1))
    assert closed.state == "dismissed" and closed.work_id is None
    assert proposals.suggest(p, ws, src) == closed
    assert proposals.queue(p, ws, 50) == [] and work.list_work(p, ws) == []
    with pytest.raises(ReviewConflict):
        proposals.review(p, ws, a.id, Review(decision="accept", expected_version=closed.version))
    with work.engine.connect() as conn:
        assert conn.execute(
            text("SELECT operation FROM proposal_events ORDER BY version")
        ).scalars().all() == ["suggested", "dismissed"]


@pytest.mark.postgres
def test_racing_acceptance_creates_one_private_task_and_evidence(scenario):
    proposals, work, ws, _, _, p, src = scenario
    draft = proposals.suggest(p, ws, src)
    barrier = Barrier(2)

    def accept(_):
        barrier.wait(timeout=10)
        try:
            return proposals.review(p, ws, draft.id, Review(decision="accept", expected_version=1))
        except ReviewConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(accept, range(2)))
    assert outcomes.count(None) == 1
    accepted = next(result for result in outcomes if result)
    (item,) = work.list_work(p, ws)
    assert accepted.work_id == item.id and item.visibility == "private"
    assert work.evidence(p, ws, item.id) == [
        {"summary": "Review sample", "excerpt": "Private context"}
    ]
    work.share_work(p, ws, item.id, expected_version=1)
    assert work.evidence(Principal("test", "owner"), ws, item.id) == []


@pytest.mark.postgres
def test_proposal_privacy_and_revocation(scenario):
    proposals, work, ws, other, users, p, src = scenario
    draft = proposals.suggest(p, ws, src)
    owner = Principal("test", "owner")
    assert proposals.queue(owner, ws, 50) == []
    with pytest.raises(SourceNotFound):
        proposals.suggest(owner, ws, src)
    with pytest.raises(ProposalNotFound):
        proposals.review(owner, ws, draft.id, Review(decision="accept", expected_version=1))
    with pytest.raises(ProposalNotFound):
        proposals.get(Principal("test", "outsider"), other, draft.id)
    with work.engine.begin() as c:
        c.execute(
            text("UPDATE memberships SET role='observer' WHERE user_id=:user"),
            {"user": users["member"]},
        )
    assert proposals.get(p, ws, draft.id) == draft
    with pytest.raises(AccessDenied):
        proposals.review(p, ws, draft.id, Review(decision="accept", expected_version=1))
    with work.engine.begin() as c:
        c.execute(
            text("UPDATE memberships SET active=false WHERE user_id=:user"),
            {"user": users["member"]},
        )
    with pytest.raises(AccessDenied):
        proposals.get(p, ws, draft.id)


@pytest.mark.postgres
def test_acceptance_is_atomic_and_review_history_immutable(scenario):
    proposals, work, ws, _, _, p, src = scenario
    draft = proposals.suggest(p, ws, src)
    with work.engine.begin() as c:
        c.execute(text("ALTER TABLE proposal_events ADD CHECK (operation <> 'accepted')"))
    with pytest.raises(DBAPIError):
        proposals.review(p, ws, draft.id, Review(decision="accept", expected_version=1))
    assert proposals.get(p, ws, draft.id) == draft and work.list_work(p, ws) == []
    with work.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM evidence_links")).scalar_one() == 0
    for statement in (
        "UPDATE proposal_events SET version=2",
        "DELETE FROM proposal_events",
        "TRUNCATE proposal_events",
    ):
        with pytest.raises(DBAPIError, match="append-only"), work.engine.begin() as c:
            c.execute(text(statement))


@pytest.mark.postgres
def test_http_private_review_correct_then_accept(workspace_client):
    client, ws, _, _, sign = workspace_client
    base = f"/api/v2/workspaces/{ws}"
    headers = {"Authorization": "Bearer " + sign("member")}
    readonly = {"Authorization": "Bearer " + sign("member", overrides={"scope": "flowpilot:read"})}
    source = client.post(
        base + "/sources",
        headers=headers,
        json={
            "reference": "synthetic:agenda",
            "summary": "Draft agenda",
            "excerpt": "Untrusted note",
        },
    ).json()["id"]
    path = f"{base}/sources/{source}/task-proposal"
    assert client.put(path).status_code == 401
    assert client.put(path, headers=readonly).status_code == 403
    draft = client.put(path, headers=headers).json()
    assert draft["state"] == "pending_review" and draft["work_id"] is None
    assert client.get(base + "/proposals", headers=readonly).json() == [draft]
    path = f"{base}/proposals/{draft['id']}"
    correction = {"expected_version": 1, "title": "  Circulate agenda  ", "due_date": "2027-02-03"}
    assert client.patch(path, headers=headers, json=correction).json()["version"] == 2
    assert client.patch(path, headers=headers, json=correction).status_code == 409
    review = {"decision": "accept", "expected_version": 1}
    assert client.post(path + "/review", headers=headers, json=review).status_code == 409
    review["expected_version"] = 2
    assert (
        client.post(
            path + "/review", headers=headers, json={**review, "title": "Unreviewed"}
        ).status_code
        == 422
    )
    accepted = client.post(path + "/review", headers=headers, json=review).json()
    assert accepted["state"] == "accepted" and accepted["version"] == 3
    assert client.get(path, headers=headers).json() == accepted
    task = client.get(f"{base}/work/{accepted['work_id']}", headers=headers).json()
    assert (task["data"]["title"], task["data"]["due_date"]) == ("Circulate agenda", "2027-02-03")
