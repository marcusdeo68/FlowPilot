"""Opaque, absolute-expiry sessions; no provider tokens or membership snapshots."""

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from flowpilot_api.identity import AccessIdentity, IdentityConfig
from flowpilot_api.work_service import Principal

COOKIE_NAME = "flowpilot_session"
COOKIE_PATH = "/api/v2"


class InvalidSession(Exception):
    pass


class SessionUnavailable(Exception):
    pass


@dataclass(frozen=True)
class BrowserConfig:
    origin: str

    def __post_init__(self):
        match = re.fullmatch(
            r"(https?)://(localhost|127\.0\.0\.1)(?::([1-9][0-9]{0,4}))?", self.origin
        )
        if not match:
            raise ValueError("Browser origin must be an exact canonical loopback HTTP(S) origin")
        scheme, _, port = match.groups()
        if port and (int(port) > 65535 or int(port) == (443 if scheme == "https" else 80)):
            raise ValueError("Browser origin requires a valid port; omit the scheme's default port")

    @property
    def secure(self) -> bool:
        return self.origin.startswith("https:")


def credential_digest(credential: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", credential):
        raise InvalidSession
    return hashlib.sha256(credential.encode("ascii")).hexdigest()


def csrf_token(credential: str) -> str:
    credential_digest(credential)
    return hmac.new(credential.encode("ascii"), b"flowpilot session csrf v1", "sha256").hexdigest()


class BrowserSessions:
    def __init__(self, engine: Engine, identity: IdentityConfig, browser: BrowserConfig):
        self.engine = engine
        self.identity = identity
        self.browser = browser

    def _binding(self, credential: str) -> dict:
        return {
            "digest": credential_digest(credential),
            "issuer": self.identity.issuer,
            "audience": self.identity.audience,
            "origin": self.browser.origin,
        }

    def issue(self, identity: AccessIdentity) -> str:
        # JWT verification permits clock skew; session issuance never extends expiry.
        if identity.expires_at <= time.time() or identity.principal.issuer != self.identity.issuer:
            raise InvalidSession
        credential = secrets.token_urlsafe(32)
        params = self._binding(credential) | {
            "id": uuid4(),
            "subject": identity.principal.subject,
            "scopes": sorted(identity.scopes),
            "expiry": identity.expires_at,
            "audit": uuid4(),
        }
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text("""
                    INSERT INTO browser_sessions
                    (id, credential_hash, issuer, subject, audience, origin, scopes, expires_at)
                    VALUES (:id, :digest, :issuer, :subject, :audience, :origin, :scopes, :expiry)
                """),
                    params,
                )
                connection.execute(
                    text("""
                    INSERT INTO browser_session_audit (id, session_id, operation)
                    VALUES (:audit, :id, 'created')
                """),
                    params,
                )
        except SQLAlchemyError as exc:
            raise SessionUnavailable from exc
        return credential

    def resolve(self, credential: str) -> AccessIdentity:
        params = self._binding(credential)
        try:
            with self.engine.connect() as connection:
                row = (
                    connection.execute(
                        text("""
                    SELECT issuer, subject, scopes, expires_at FROM browser_sessions
                    WHERE credential_hash=:digest AND issuer=:issuer AND audience=:audience
                    AND origin=:origin AND revoked_at IS NULL
                """),
                        params,
                    )
                    .mappings()
                    .one_or_none()
                )
        except SQLAlchemyError as exc:
            raise SessionUnavailable from exc
        if row is None or row["expires_at"] <= time.time():
            raise InvalidSession
        return AccessIdentity(
            Principal(row["issuer"], row["subject"]), frozenset(row["scopes"]), row["expires_at"]
        )

    def revoke(self, credential: str) -> None:
        # Idempotent, including expired sessions. Concurrent revokes emit one event.
        params = self._binding(credential) | {"audit": uuid4()}
        try:
            with self.engine.begin() as connection:
                session_id = connection.execute(
                    text("""
                    UPDATE browser_sessions SET revoked_at=clock_timestamp()
                    WHERE credential_hash=:digest AND issuer=:issuer AND audience=:audience
                    AND origin=:origin AND revoked_at IS NULL RETURNING id
                """),
                    params,
                ).scalar_one_or_none()
                if session_id is not None:
                    connection.execute(
                        text("""
                        INSERT INTO browser_session_audit (id, session_id, operation)
                        VALUES (:audit, :id, 'revoked')
                    """),
                        {"audit": params["audit"], "id": session_id},
                    )
        except SQLAlchemyError as exc:
            raise SessionUnavailable from exc
