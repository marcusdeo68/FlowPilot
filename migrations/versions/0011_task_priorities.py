"""Store task priority overrides. A NULL override is Normal for tasks."""

from alembic import op

revision = "0011_task_priorities"
down_revision = "0010_workspace_projects"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE work_items
            ADD COLUMN task_priority varchar(10),
            ADD CONSTRAINT work_items_task_priority_check
                CHECK (task_priority IS NULL OR (
                    kind = 'task' AND task_priority IN ('low', 'high')
                ))
    """)


def downgrade():
    op.execute("LOCK TABLE work_items IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM work_items WHERE task_priority IS NOT NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade while task priority overrides exist'
                    USING ERRCODE = '23514';
            END IF;
        END $$
    """)
    op.drop_column("work_items", "task_priority")
