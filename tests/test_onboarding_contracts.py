import pytest
from flowpilot_api.membership_service import WorkspaceCreate
from flowpilot_api.workspace_api import AddMember, ChangeMember
from pydantic import ValidationError


@pytest.mark.parametrize("name", ["", "   ", "x" * 201, "bad\x00name"])
def test_invalid_workspace_names(name):
    with pytest.raises(ValidationError):
        WorkspaceCreate(name=name)


def test_workspace_inputs_cannot_self_assert_identity_or_role():
    assert WorkspaceCreate(name=" Synthetic workspace ").name == "Synthetic workspace"
    with pytest.raises(ValidationError):
        WorkspaceCreate(name="Synthetic", owner_id="caller-selected")
    with pytest.raises(ValidationError):
        AddMember(user_id="00000000-0000-0000-0000-000000000001", role="admin")
    with pytest.raises(ValidationError):
        ChangeMember(role="member", active=1, expected_version=1)
    with pytest.raises(ValidationError):
        ChangeMember(role="member", active=True, expected_version=True)
