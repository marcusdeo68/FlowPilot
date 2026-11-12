"""Versioned membership administration and immutable workspace audit.

Revision ID: 0002_membership_admin
Revises: 0001_work_storage
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_membership_admin"
down_revision = "0001_work_storage"
branch_labels = None
depends_on = None


def upgrade():
    ownerless = (
        op.get_bind()
        .execute(
            sa.text("""SELECT w.id FROM workspaces w
        WHERE NOT EXISTS (SELECT 1 FROM memberships m WHERE m.workspace_id=w.id
                          AND m.active=true AND m.role='owner') LIMIT 1""")
        )
        .first()
    )
    if ownerless is not None:
        raise RuntimeError("Repair workspaces without active owners before applying this migration")
    op.add_column(
        "memberships", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.create_check_constraint("ck_memberships_version_positive", "memberships", "version >= 1")
    op.create_table(
        "workspace_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(30), nullable=False),
        sa.Column("from_role", sa.String(20)),
        sa.Column("to_role", sa.String(20), nullable=False),
        sa.Column("from_active", sa.Boolean()),
        sa.Column("to_active", sa.Boolean(), nullable=False),
        sa.Column("membership_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "target_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.CheckConstraint(
            "operation IN ('workspace_created', 'member_added', 'membership_changed')"
        ),
        sa.CheckConstraint("from_role IS NULL OR from_role IN ('owner','member','observer')"),
        sa.CheckConstraint("to_role IN ('owner','member','observer')"),
        sa.CheckConstraint("membership_version >= 1"),
    )
    op.create_index(
        "ix_workspace_events_history", "workspace_events", ["workspace_id", "created_at", "id"]
    )
    op.execute("""CREATE TRIGGER workspace_events_no_edit BEFORE UPDATE OR DELETE ON workspace_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_edit()""")
    op.execute("""CREATE TRIGGER workspace_events_no_truncate BEFORE TRUNCATE ON workspace_events
        FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_edit()""")


def downgrade():
    # Development-only rollback: preserves users/work, drops this increment's admin history.
    op.drop_table("workspace_events")
    op.drop_constraint("ck_memberships_version_positive", "memberships", type_="check")
    op.drop_column("memberships", "version")
