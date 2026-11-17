"""Internal pending-login records. Claiming one never authenticates a user."""

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from flowpilot_api.browser_sessions import BrowserConfig
from flowpilot_api.identity import IdentityConfig


class InvalidLoginTransaction(Exception):
    pass


class LoginStorageUnavailable(Exception):
    pass


def _digest(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
        raise InvalidLoginTransaction
    return hashlib.sha256(value.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class PendingLogin:
    state: str = field(repr=False)
    verifier: str = field(repr=False)
    expires_at: datetime

    @property
    def challenge(self) -> str:
        return base64.urlsafe_b64encode(bytes.fromhex(_digest(self.verifier))).decode().rstrip("=")


class LoginTransactions:
    def __init__(
        self, engine: Engine, identity: IdentityConfig, browser: BrowserConfig, client_id: str
    ):
        if (
            not isinstance(client_id, str)
            or not 1 <= len(client_id) <= 300
            or not client_id.strip()
            or any(ord(char) < 32 for char in client_id)
        ):
            raise ValueError("A bounded, nonblank login client ID is required")
        self.engine = engine
        self.binding = {
            "issuer": identity.issuer,
            "audience": identity.audience,
            "client": client_id,
            "redirect": browser.origin + "/api/v2/login/callback",
        }

    def begin(self) -> PendingLogin:
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        params = self.binding | {
            "id": uuid4(),
            "state": _digest(state),
            "verifier": _digest(verifier),
            "audit": uuid4(),
        }
        try:
            with self.engine.begin() as c:
                expiry = c.execute(
                    text("""
                    INSERT INTO login_transactions
                    (id, state_hash, verifier_hash, issuer, audience, client_id, redirect_uri)
                    VALUES (:id, :state, :verifier, :issuer, :audience, :client, :redirect)
                    RETURNING expires_at
                """),
                    params,
                ).scalar_one()
                c.execute(
                    text("""INSERT INTO login_transaction_audit (id, transaction_id, operation)
                    VALUES (:audit, :id, 'created')"""),
                    params,
                )
        except SQLAlchemyError as exc:
            raise LoginStorageUnavailable from exc
        return PendingLogin(state, verifier, expiry)

    def consume(self, state: str, verifier: str) -> None:
        params = self.binding | {"state": _digest(state), "verifier": _digest(verifier)}
        try:
            with self.engine.begin() as c:
                # Lock first: an UPDATE may evaluate its time predicate before
                # waiting on an unchanged locked row. Check expiry after waiting.
                c.execute(
                    text("""SELECT id FROM login_transactions
                    WHERE state_hash=:state AND verifier_hash=:verifier
                    AND issuer=:issuer AND audience=:audience AND client_id=:client
                    AND redirect_uri=:redirect FOR UPDATE"""),
                    params,
                ).all()
                transaction_id = c.execute(
                    text("""
                    UPDATE login_transactions SET consumed_at=clock_timestamp()
                    WHERE state_hash=:state AND verifier_hash=:verifier
                    AND issuer=:issuer AND audience=:audience AND client_id=:client
                    AND redirect_uri=:redirect AND consumed_at IS NULL
                    AND expires_at > clock_timestamp() RETURNING id
                """),
                    params,
                ).scalar_one_or_none()
                if transaction_id is None:
                    raise InvalidLoginTransaction
                c.execute(
                    text("""INSERT INTO login_transaction_audit (id, transaction_id, operation)
                    VALUES (:audit, :id, 'consumed')"""),
                    {"audit": uuid4(), "id": transaction_id},
                )
        except SQLAlchemyError as exc:
            raise LoginStorageUnavailable from exc
