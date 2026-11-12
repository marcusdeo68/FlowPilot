from uuid import uuid4

import pytest
from flowpilot_api.access import (
    AccessDenied,
    EvidenceVisibility,
    Membership,
    Role,
    Visibility,
    require_connection_action,
    require_membership,
    require_source_access,
    require_work_access,
    visible_evidence,
)


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("write", [False, True])
def test_role_matrix(role, write):
    member = Membership(uuid4(), uuid4(), role)
    if write and role == Role.OBSERVER:
        with pytest.raises(AccessDenied):
            require_membership(member, member.workspace_id, write=write)
    else:
        require_membership(member, member.workspace_id, write=write)
    with pytest.raises(AccessDenied):
        require_membership(member, uuid4(), write=write)


@pytest.mark.parametrize("role", list(Role))
def test_private_source_and_work_are_not_visible_to_other_members(role):
    member = Membership(uuid4(), uuid4(), role)
    owner = uuid4()
    with pytest.raises(AccessDenied):
        require_source_access(member, member.workspace_id, owner)
    with pytest.raises(AccessDenied):
        require_work_access(member, member.workspace_id, owner, Visibility.PRIVATE)
    require_work_access(member, member.workspace_id, owner, Visibility.WORKSPACE)


@pytest.mark.parametrize(
    "visibility,keys",
    [
        (EvidenceVisibility.PRIVATE, set()),
        (EvidenceVisibility.SUMMARY_SHARED, {"summary"}),
        (EvidenceVisibility.EXCERPT_SHARED, {"summary", "excerpt"}),
    ],
)
def test_evidence_projection(visibility, keys):
    member = Membership(uuid4(), uuid4(), Role.OWNER)
    result = visible_evidence(
        member,
        member.workspace_id,
        uuid4(),
        visibility,
        summary="Synthetic summary",
        excerpt="Private excerpt",
    )
    assert set(result) == keys


def test_inactive_members_and_revoked_connections():
    user, workspace = uuid4(), uuid4()
    inactive = Membership(user, workspace, Role.OWNER, active=False)
    with pytest.raises(AccessDenied):
        require_membership(inactive, workspace)
    member = Membership(user, workspace, Role.MEMBER)
    require_connection_action(member, workspace, user, revoked=False)
    for owner, revoked in ((uuid4(), False), (user, True)):
        with pytest.raises(AccessDenied):
            require_connection_action(member, workspace, owner, revoked=revoked)
