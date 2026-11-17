"""Single-use pending login transactions and append-only lifecycle audit."""

from alembic import op

revision = "0006_login_transactions"
down_revision = "0005_browser_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE login_transactions (
            id uuid PRIMARY KEY,
            state_hash text NOT NULL UNIQUE CHECK (state_hash ~ '^[0-9a-f]{64}$'),
            verifier_hash text NOT NULL CHECK (verifier_hash ~ '^[0-9a-f]{64}$'),
            issuer text NOT NULL,
            audience text NOT NULL,
            client_id text NOT NULL,
            redirect_uri text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            expires_at timestamptz NOT NULL DEFAULT (statement_timestamp() + interval '5 minutes'),
            consumed_at timestamptz,
            CHECK (expires_at > created_at)
        )
    """)
    op.execute("""
        CREATE TABLE login_transaction_audit (
            id uuid PRIMARY KEY,
            transaction_id uuid NOT NULL REFERENCES login_transactions(id),
            operation text NOT NULL CHECK (operation IN ('created', 'consumed')),
            occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (transaction_id, operation)
        )
    """)
    op.execute("""
        CREATE TRIGGER login_transaction_audit_immutable
        BEFORE UPDATE OR DELETE ON login_transaction_audit
        FOR EACH ROW EXECUTE FUNCTION reject_audit_edit()
    """)
    op.execute("""
        CREATE TRIGGER login_transaction_audit_no_truncate
        BEFORE TRUNCATE ON login_transaction_audit
        FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_edit()
    """)


def downgrade():
    op.drop_table("login_transaction_audit")
    op.drop_table("login_transactions")
