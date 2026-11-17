import base64
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC

import pytest
from alembic import command
from flowpilot_api.browser_sessions import BrowserConfig
from flowpilot_api.login_transactions import (
    InvalidLoginTransaction,
    LoginStorageUnavailable,
    LoginTransactions,
    PendingLogin,
)
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


def service(engine, token_tools, **kwargs):
    config = token_tools[0]
    return LoginTransactions(engine, config, BrowserConfig("http://127.0.0.1:8001"), **kwargs)


def test_pkce_standard_vector_and_secret_repr():
    from datetime import datetime

    pending = PendingLogin(
        "secret-state", "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk", datetime.now(UTC)
    )
    assert pending.challenge == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert pending.state not in repr(pending) and pending.verifier not in repr(pending)


@pytest.mark.postgres
def test_generation_digest_only_storage_and_replay(pg, token_tools):
    engine, _ = pg
    logins = service(engine, token_tools, client_id="synthetic-client")
    first, second = logins.begin(), logins.begin()
    assert len({first.state, first.verifier, second.state, second.verifier}) == 4
    with engine.connect() as c:
        rows = c.execute(text("SELECT * FROM login_transactions")).mappings().all()
        persisted = str(rows)
        assert all(
            value not in persisted
            for value in (first.state, first.verifier, second.state, second.verifier)
        )
        for row in rows:
            assert (row["expires_at"] - row["created_at"]).total_seconds() == 300
    assert first.challenge == base64.urlsafe_b64encode(
        hashlib.sha256(first.verifier.encode()).digest()
    ).decode().rstrip("=")
    assert logins.consume(first.state, first.verifier) is None
    with pytest.raises(InvalidLoginTransaction):
        logins.consume(first.state, first.verifier)
    with engine.connect() as c:
        assert (
            c.execute(
                text("SELECT count(*) FROM login_transaction_audit WHERE operation='consumed'")
            ).scalar_one()
            == 1
        )


@pytest.mark.postgres
def test_wrong_secrets_binding_and_expiry_do_not_consume(pg, token_tools):
    engine, _ = pg
    logins = service(engine, token_tools, client_id="synthetic-client")
    pending, other = logins.begin(), logins.begin()
    for state, verifier in ((pending.state, other.verifier), (other.state, pending.verifier)):
        with pytest.raises(InvalidLoginTransaction):
            logins.consume(state, verifier)
    config = token_tools[0]
    mismatches = [
        (
            replace(config, audience="other"),
            BrowserConfig("http://127.0.0.1:8001"),
            "synthetic-client",
        ),
        (
            replace(config, issuer="https://other.example", jwks_url="https://other.example/jwks"),
            BrowserConfig("http://127.0.0.1:8001"),
            "synthetic-client",
        ),
        (config, BrowserConfig("http://127.0.0.1:8002"), "synthetic-client"),
        (config, BrowserConfig("http://127.0.0.1:8001"), "other-client"),
    ]
    for identity, browser, client in mismatches:
        with pytest.raises(InvalidLoginTransaction):
            LoginTransactions(engine, identity, browser, client).consume(
                pending.state, pending.verifier
            )
    logins.consume(pending.state, pending.verifier)
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE login_transactions SET created_at=clock_timestamp()-interval '10 minutes', expires_at=clock_timestamp()-interval '1 minute' WHERE consumed_at IS NULL"
            )
        )
    with pytest.raises(InvalidLoginTransaction):
        logins.consume(other.state, other.verifier)


@pytest.mark.postgres
def test_concurrent_consume_and_immutable_audit(pg, token_tools):
    engine, _ = pg
    logins = service(engine, token_tools, client_id="synthetic-client")
    pending = logins.begin()

    def consume(_):
        try:
            logins.consume(pending.state, pending.verifier)
            return True
        except InvalidLoginTransaction:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(consume, range(2))) == [False, True]
    for query in (
        "UPDATE login_transaction_audit SET operation='created'",
        "DELETE FROM login_transaction_audit",
        "TRUNCATE login_transaction_audit",
    ):
        with pytest.raises(DBAPIError), engine.begin() as c:
            c.execute(text(query))


@pytest.mark.postgres
def test_audit_failure_rolls_back_begin_and_consume(pg, token_tools):
    engine, _ = pg
    logins = service(engine, token_tools, client_id="synthetic-client")
    pending = logins.begin()
    with engine.begin() as c:
        c.execute(
            text(
                "CREATE TRIGGER fail_login_audit BEFORE INSERT ON login_transaction_audit FOR EACH ROW EXECUTE FUNCTION reject_audit_edit()"
            )
        )
    with pytest.raises(LoginStorageUnavailable):
        logins.begin()
    with pytest.raises(LoginStorageUnavailable):
        logins.consume(pending.state, pending.verifier)
    with engine.begin() as c:
        assert c.execute(text("SELECT count(*) FROM login_transactions")).scalar_one() == 1
        assert c.execute(text("SELECT consumed_at FROM login_transactions")).scalar_one() is None
        c.execute(text("DROP TRIGGER fail_login_audit ON login_transaction_audit"))
    logins.consume(pending.state, pending.verifier)


@pytest.mark.postgres
def test_login_migration_roundtrip(pg, token_tools):
    engine, config = pg
    service(engine, token_tools, client_id="synthetic").begin()
    with engine.begin() as c:
        config.attributes["connection"] = c
        command.downgrade(config, "0005_browser_sessions")
        assert c.execute(text("SELECT to_regclass('login_transactions')")).scalar_one() is None
        assert c.execute(text("SELECT to_regclass('browser_sessions')")).scalar_one() is not None
        command.upgrade(config, "head")
    service(engine, token_tools, client_id="synthetic").begin()


@pytest.mark.postgres
def test_expiry_is_rechecked_after_waiting_for_row_lock(pg, token_tools):
    engine, _ = pg
    logins = service(engine, token_tools, client_id="synthetic-client")
    pending = logins.begin()
    with engine.begin() as c:
        c.execute(
            text("UPDATE login_transactions SET expires_at=clock_timestamp()+interval '2 seconds'")
        )
    # Hold an unchanged row: PostgreSQL need not recheck UPDATE predicates after
    # this wait, unlike a lock holder that actually updates the tuple (FP-014).
    with ThreadPoolExecutor(max_workers=1) as pool:
        with engine.begin() as blocker:
            blocker.execute(text("SELECT id FROM login_transactions FOR UPDATE")).all()
            future = pool.submit(logins.consume, pending.state, pending.verifier)
            deadline = time.monotonic() + 1.5
            with engine.connect() as observer:
                while True:
                    waiting = observer.execute(
                        text("""SELECT count(*) FROM pg_stat_activity
                        WHERE wait_event_type='Lock' AND pid <> pg_backend_pid()
                        AND query LIKE '%login_transactions%'
                        AND query NOT LIKE '%pg_stat_activity%'""")
                    ).scalar_one()
                    if waiting:
                        break
                    assert time.monotonic() < deadline, "Consumer never waited on the locked row"
                    time.sleep(0.01)
            blocker.execute(text("SELECT pg_sleep(2.1)"))
        with pytest.raises(InvalidLoginTransaction):
            future.result(timeout=5)
    with engine.connect() as c:
        assert c.execute(text("SELECT consumed_at FROM login_transactions")).scalar_one() is None
        assert (
            c.execute(
                text("SELECT count(*) FROM login_transaction_audit WHERE operation='consumed'")
            ).scalar_one()
            == 0
        )


def test_malformed_secrets_and_storage_failure(token_tools):
    engine = create_engine("sqlite://")
    try:
        logins = service(engine, token_tools, client_id="synthetic-client")
        for value in ("", "x" * 42, "x" * 44, "!" * 43, "é" * 43, None):
            with pytest.raises(InvalidLoginTransaction):
                logins.consume(value, "x" * 43)
            with pytest.raises(InvalidLoginTransaction):
                logins.consume("x" * 43, value)
        with pytest.raises(LoginStorageUnavailable):
            logins.begin()
        with pytest.raises(LoginStorageUnavailable):
            logins.consume("x" * 43, "x" * 43)
        for client in ("", " ", "a" * 301, "bad\n", None):
            with pytest.raises(ValueError):
                service(engine, token_tools, client_id=client)
    finally:
        engine.dispose()
