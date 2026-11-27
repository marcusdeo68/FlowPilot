"""Add immutable workspace project names and optional task assignment."""

from alembic import op

revision = "0010_workspace_projects"
down_revision = "0009_workspace_invitations"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE workspace_projects (
            workspace_id uuid NOT NULL,
            id uuid NOT NULL,
            name varchar(100) NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 100),
            created_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, id),
            FOREIGN KEY (workspace_id, created_by) REFERENCES memberships(workspace_id, user_id)
        )
    """)
    op.execute("""CREATE UNIQUE INDEX uq_workspace_projects_name
        ON workspace_projects (workspace_id, lower(name))""")
    op.execute("""CREATE TRIGGER workspace_projects_no_edit
        BEFORE UPDATE OR DELETE ON workspace_projects
        FOR EACH ROW EXECUTE FUNCTION reject_audit_edit()""")
    op.execute("""CREATE TRIGGER workspace_projects_no_truncate
        BEFORE TRUNCATE ON workspace_projects
        FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_edit()""")
    op.execute("""
        ALTER TABLE work_items
            ADD COLUMN project_id uuid,
            ADD CONSTRAINT work_items_project_fk
                FOREIGN KEY (workspace_id, project_id) REFERENCES workspace_projects(workspace_id, id),
            ADD CONSTRAINT work_items_task_project_only CHECK (project_id IS NULL OR kind = 'task')
    """)
    op.execute("""CREATE INDEX ix_work_project_page
        ON work_items (workspace_id, project_id, created_at DESC, id DESC)
        WHERE project_id IS NOT NULL""")


def downgrade():
    op.execute("LOCK TABLE workspace_projects IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM workspace_projects) THEN
                RAISE EXCEPTION 'Cannot downgrade while workspace projects exist'
                    USING ERRCODE = '23514';
            END IF;
        END $$
    """)
    op.drop_column("work_items", "project_id")
    op.drop_table("workspace_projects")
