"""Allow versioned task detail edits in append-only work history."""

from alembic import op

revision = "0007_task_details_audit"
down_revision = "0006_login_transactions"
branch_labels = None
depends_on = None


def _replace_constraint(*, allow_details: bool) -> None:
    # PostgreSQL assigned this name to the multi-column CHECK in revision 0001.
    operations = "'created','status_changed','shared','evidence_linked'"
    if allow_details:
        operations += ",'details_changed'"
    op.drop_constraint("audit_events_check", "audit_events", type_="check")
    op.create_check_constraint(
        "audit_events_check",
        "audit_events",
        "(source_id IS NOT NULL AND work_id IS NULL AND operation = 'source_created')"
        " OR (work_id IS NOT NULL AND source_id IS NULL"
        f" AND operation IN ({operations}))",
    )


def upgrade():
    _replace_constraint(allow_details=True)


def downgrade():
    # Constraint validation refuses a downgrade with task edit history present.
    # Keep the append-only records intact and let PostgreSQL roll back the DDL.
    _replace_constraint(allow_details=False)
