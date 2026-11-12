from uuid import uuid4

import pytest
from flowpilot_api.access import (
    AccessDenied,
    Membership,
    Role,
    Visibility,
    require_membership,
    require_work_access,
)


def test_unknown_role_is_denied_even_for_reads():
    member = Membership(uuid4(), uuid4(), "invented")
    with pytest.raises(AccessDenied):
        require_membership(member, member.workspace_id)


def test_unknown_visibility_is_not_treated_as_shared():
    member = Membership(uuid4(), uuid4(), Role.MEMBER)
    with pytest.raises(AccessDenied):
        require_work_access(member, member.workspace_id, uuid4(), "invented")
    require_work_access(member, member.workspace_id, member.user_id, Visibility.PRIVATE)
