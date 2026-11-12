"""Index private source discovery by its stable page order."""

from alembic import op

revision = "0004_source_inbox"
down_revision = "0003_task_proposals"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_sources_owner_created", "source_items", ["workspace_id", "owner_id", "created_at", "id"]
    )


def downgrade():
    op.drop_index("ix_sources_owner_created", table_name="source_items")
