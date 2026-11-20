"""Store private sticky notes and append-only note history."""

from alembic import op

revision = "0008_private_notes"
down_revision = "0007_task_details_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE notes (
            id uuid PRIMARY KEY,
            workspace_id uuid NOT NULL,
            owner_id uuid NOT NULL,
            body varchar(2000) NOT NULL CHECK (length(trim(body)) > 0),
            archived boolean NOT NULL DEFAULT false,
            version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, id, owner_id),
            FOREIGN KEY (workspace_id, owner_id) REFERENCES memberships(workspace_id, user_id)
        )
    """)
    op.execute("""CREATE INDEX ix_notes_owner_page ON notes
        (workspace_id, owner_id, archived, created_at DESC, id DESC)""")
    op.execute("""
        CREATE TABLE note_events (
            workspace_id uuid NOT NULL,
            note_id uuid NOT NULL,
            actor_id uuid NOT NULL,
            version integer NOT NULL CHECK (version >= 1),
            operation text NOT NULL CHECK (operation IN ('created','edited','archived','restored')),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, note_id, version),
            FOREIGN KEY (workspace_id, note_id, actor_id)
                REFERENCES notes(workspace_id, id, owner_id)
        )
    """)
    op.execute("""CREATE TRIGGER note_events_no_edit BEFORE UPDATE OR DELETE ON note_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_edit()""")
    op.execute("""CREATE TRIGGER note_events_no_truncate BEFORE TRUNCATE ON note_events
        FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_edit()""")


def downgrade():
    op.execute("LOCK TABLE notes, note_events IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM notes) THEN
                RAISE EXCEPTION 'Cannot downgrade while private notes exist'
                    USING ERRCODE = '23514';
            END IF;
        END $$
    """)
    op.drop_table("note_events")
    op.drop_table("notes")
