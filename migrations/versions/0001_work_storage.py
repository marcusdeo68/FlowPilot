"""Tenant-aware manual work storage. Frozen schema; do not import live models.

Revision ID: 0001_work_storage
Revises: none
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_work_storage"
down_revision = None
branch_labels = None
depends_on = None


def member_fk(column):
    return sa.ForeignKeyConstraint(
        ["workspace_id", column], ["memberships.workspace_id", "memberships.user_id"]
    )


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("issuer", sa.String(300), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.UniqueConstraint("issuer", "subject"),
        sa.CheckConstraint("length(trim(issuer)) BETWEEN 1 AND 300"),
        sa.CheckConstraint("length(trim(subject)) BETWEEN 1 AND 300"),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 200"),
    )
    op.create_table(
        "memberships",
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("role IN ('owner', 'member', 'observer')"),
    )
    op.create_table(
        "source_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(300), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("excerpt", sa.String(2000), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        member_fk("owner_id"),
        sa.UniqueConstraint("workspace_id", "owner_id", "reference"),
        sa.UniqueConstraint("workspace_id", "id", "owner_id"),
        sa.CheckConstraint("length(trim(reference)) BETWEEN 1 AND 300"),
        sa.CheckConstraint("length(trim(summary)) BETWEEN 1 AND 500"),
        sa.CheckConstraint("length(trim(excerpt)) BETWEEN 1 AND 2000"),
    )
    op.create_table(
        "work_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("creator_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(4000)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
        sa.Column("due_date", sa.Date()),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("time_zone", sa.String(100)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        member_fk("creator_id"),
        member_fk("owner_id"),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.CheckConstraint("length(trim(title)) BETWEEN 1 AND 200"),
        sa.CheckConstraint("version >= 1"),
        sa.CheckConstraint("visibility IN ('private', 'workspace')"),
        sa.CheckConstraint("""
            (kind = 'commitment' AND status IN
                ('detected','confirmed','active','blocked','completed','canceled','disputed'))
            OR (kind = 'task' AND status IN ('open','active','blocked','completed','canceled'))
            OR (kind = 'event' AND status IN ('scheduled','canceled'))
        """),
        sa.CheckConstraint("""
            (kind = 'event' AND starts_at IS NOT NULL AND ends_at IS NOT NULL
                AND ends_at > starts_at AND time_zone IS NOT NULL AND due_date IS NULL)
            OR (kind IN ('task','commitment') AND starts_at IS NULL
                AND ends_at IS NULL AND time_zone IS NULL)
        """),
    )
    op.create_index("ix_work_workspace_updated", "work_items", ["workspace_id", "updated_at", "id"])
    op.create_table(
        "evidence_links",
        sa.Column("workspace_id", sa.Uuid(), primary_key=True),
        sa.Column("work_id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), primary_key=True),
        sa.Column("source_owner_id", sa.Uuid(), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column("shared_by", sa.Uuid()),
        sa.Column("shared_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["workspace_id", "work_id"], ["work_items.workspace_id", "work_items.id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_id", "source_owner_id"],
            ["source_items.workspace_id", "source_items.id", "source_items.owner_id"],
        ),
        sa.CheckConstraint("visibility IN ('private','summary_shared','excerpt_shared')"),
        sa.CheckConstraint("""
            (visibility = 'private' AND shared_by IS NULL AND shared_at IS NULL)
            OR (visibility IN ('summary_shared','excerpt_shared') AND shared_by IS NOT NULL
                AND shared_by = source_owner_id AND shared_at IS NOT NULL)
        """),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("work_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        member_fk("actor_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "work_id"], ["work_items.workspace_id", "work_items.id"]
        ),
        sa.CheckConstraint("operation IN ('created','status_changed','shared','evidence_linked')"),
        sa.CheckConstraint("version >= 1"),
    )
    op.create_index("ix_audit_work", "audit_events", ["workspace_id", "work_id", "version"])
    op.execute("""CREATE FUNCTION reject_audit_edit() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Audit events are append-only'; END; $$""")
    op.execute("""CREATE TRIGGER audit_no_edit BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_edit()""")
    op.execute("""CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_edit()""")


def downgrade():
    # Explicit operator action on development databases; drops records as documented.
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION reject_audit_edit()")
    op.drop_table("evidence_links")
    op.drop_table("work_items")
    op.drop_table("source_items")
    op.drop_table("memberships")
    op.drop_table("workspaces")
    op.drop_table("users")
