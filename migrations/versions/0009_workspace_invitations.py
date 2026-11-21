"""Store recipient-bound workspace invitations and immutable decision history."""

from alembic import op

revision = "0009_workspace_invitations"
down_revision = "0008_private_notes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE workspace_invitations (
            id uuid PRIMARY KEY,
            workspace_id uuid NOT NULL,
            inviter_id uuid NOT NULL,
            inviter_version integer NOT NULL CHECK (inviter_version >= 1),
            recipient_id uuid NOT NULL REFERENCES users(id),
            role text NOT NULL CHECK (role IN ('owner', 'member', 'observer')),
            status text NOT NULL DEFAULT 'pending',
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            expires_at timestamptz NOT NULL CHECK (expires_at > created_at),
            CHECK (recipient_id <> inviter_id),
            CHECK ((status = 'pending' AND version = 1) OR
                   (status IN ('accepted', 'declined', 'revoked') AND version = 2)),
            FOREIGN KEY (workspace_id, inviter_id) REFERENCES memberships(workspace_id, user_id)
        )
    """)
    op.execute("""CREATE INDEX ix_workspace_invitations_pending
        ON workspace_invitations (workspace_id, recipient_id, expires_at) WHERE status = 'pending'""")
    op.execute("""CREATE INDEX ix_workspace_invitations_recipient
        ON workspace_invitations (recipient_id, expires_at, id) WHERE status = 'pending'""")
    op.execute("""
        CREATE TABLE invitation_events (
            invitation_id uuid NOT NULL REFERENCES workspace_invitations(id),
            version integer NOT NULL,
            actor_id uuid NOT NULL REFERENCES users(id),
            operation text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (invitation_id, version),
            CHECK ((version = 1 AND operation = 'created') OR
                   (version = 2 AND operation IN ('accepted', 'declined', 'revoked')))
        )
    """)
    op.execute("""CREATE TRIGGER invitation_events_no_edit BEFORE UPDATE OR DELETE
        ON invitation_events FOR EACH ROW EXECUTE FUNCTION reject_audit_edit()""")
    op.execute("""CREATE TRIGGER invitation_events_no_truncate BEFORE TRUNCATE
        ON invitation_events FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_edit()""")


def downgrade():
    op.execute("LOCK TABLE workspace_invitations, invitation_events IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM workspace_invitations) THEN
                RAISE EXCEPTION 'Cannot downgrade while workspace invitations exist'
                    USING ERRCODE = '23514';
            END IF;
        END $$
    """)
    op.drop_table("invitation_events")
    op.drop_table("workspace_invitations")
