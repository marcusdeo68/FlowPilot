"""One private task suggestion per manual source, with immutable review history."""

from alembic import op

revision = "0003_task_proposals"
down_revision = "0002_membership_admin"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE task_proposals (
            id uuid PRIMARY KEY,
            workspace_id uuid NOT NULL,
            source_id uuid NOT NULL,
            owner_id uuid NOT NULL,
            title varchar(200) NOT NULL CHECK (length(trim(title)) > 0),
            due_date date,
            state text NOT NULL DEFAULT 'pending_review'
                CHECK (state IN ('pending_review','accepted','dismissed')),
            version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
            work_id uuid UNIQUE,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((state = 'accepted') = (work_id IS NOT NULL)),
            UNIQUE (workspace_id, source_id),
            UNIQUE (workspace_id, id, owner_id),
            FOREIGN KEY (workspace_id, source_id, owner_id)
                REFERENCES source_items(workspace_id, id, owner_id),
            FOREIGN KEY (workspace_id, work_id) REFERENCES work_items(workspace_id, id)
        )
    """)
    op.execute("""CREATE INDEX ix_task_proposals_queue ON task_proposals
        (workspace_id, owner_id, state, updated_at DESC, id)""")
    op.execute("""
        CREATE TABLE proposal_events (
            workspace_id uuid NOT NULL,
            proposal_id uuid NOT NULL,
            actor_id uuid NOT NULL,
            version integer NOT NULL CHECK (version >= 1),
            operation text NOT NULL CHECK (operation IN ('suggested','corrected','accepted','dismissed')),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, proposal_id, version),
            FOREIGN KEY (workspace_id, proposal_id, actor_id)
                REFERENCES task_proposals(workspace_id, id, owner_id)
        )
    """)
    op.execute("""CREATE TRIGGER proposal_events_no_edit BEFORE UPDATE OR DELETE ON proposal_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_edit()""")
    op.execute("""CREATE TRIGGER proposal_events_no_truncate BEFORE TRUNCATE ON proposal_events
        FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_edit()""")


def downgrade():
    # Accepted canonical tasks and private evidence survive this development downgrade.
    op.drop_table("proposal_events")
    op.drop_table("task_proposals")
