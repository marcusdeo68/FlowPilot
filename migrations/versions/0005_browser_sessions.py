"""Bounded opaque browser sessions and append-only lifecycle history."""

from alembic import op

revision = "0005_browser_sessions"
down_revision = "0004_source_inbox"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE browser_sessions (
            id uuid PRIMARY KEY,
            credential_hash text NOT NULL UNIQUE CHECK (credential_hash ~ '^[0-9a-f]{64}$'),
            issuer text NOT NULL,
            subject text NOT NULL,
            audience text NOT NULL,
            origin text NOT NULL,
            scopes text[] NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            expires_at bigint NOT NULL,
            revoked_at timestamptz
        )
    """)
    op.execute("""
        CREATE TABLE browser_session_audit (
            id uuid PRIMARY KEY,
            session_id uuid NOT NULL REFERENCES browser_sessions(id),
            operation text NOT NULL CHECK (operation IN ('created', 'revoked')),
            occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (session_id, operation)
        )
    """)
    op.execute("""
        CREATE TRIGGER browser_session_audit_immutable
        BEFORE UPDATE OR DELETE ON browser_session_audit
        FOR EACH ROW EXECUTE FUNCTION reject_audit_edit()
    """)
    op.execute("""
        CREATE TRIGGER browser_session_audit_no_truncate
        BEFORE TRUNCATE ON browser_session_audit
        FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_edit()
    """)


def downgrade():
    op.drop_table("browser_session_audit")
    op.drop_table("browser_sessions")
