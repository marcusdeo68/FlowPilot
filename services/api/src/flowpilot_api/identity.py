"""Strict RS256 JWT access-token verification; no login, issuance, or role trust."""

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError

from flowpilot_api.work_service import Principal


class InvalidAccessToken(Exception):
    pass


class IdentityUnavailable(Exception):
    pass


@dataclass(frozen=True)
class IdentityConfig:
    issuer: str
    audience: str
    jwks_url: str

    def __post_init__(self):
        for value in (self.issuer, self.jwks_url):
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.fragment
                or parsed.query
            ):
                raise ValueError(
                    "Identity URLs must be trusted HTTPS URLs without credentials/query"
                )
        if urlsplit(self.issuer).netloc != urlsplit(self.jwks_url).netloc:
            raise ValueError("JWKS must be on the configured issuer origin")
        if not self.audience.strip() or len(self.issuer) > 300:
            raise ValueError("A nonempty API audience and bounded issuer are required")

    @classmethod
    def from_environment(cls) -> "IdentityConfig":
        issuer = os.environ.get("FLOWPILOT_OIDC_ISSUER")
        audience = os.environ.get("FLOWPILOT_OIDC_AUDIENCE")
        jwks_url = os.environ.get("FLOWPILOT_OIDC_JWKS_URL")
        if not issuer or not audience or not jwks_url:
            raise ValueError(
                "Configure issuer, API audience, and JWKS URL before starting workspace API"
            )
        return cls(issuer, audience, jwks_url)


@dataclass(frozen=True)
class AccessIdentity:
    principal: Principal
    scopes: frozenset[str]


class _ThrottledJWKClient(PyJWKClient):
    """Unknown kid values cannot force a fresh network request on every token."""

    def __init__(self, url: str):
        super().__init__(url, cache_keys=False, lifespan=300, timeout=5)
        self._fetch_lock = threading.Lock()
        self._last_attempt = float("-inf")
        self._last_response = None

    def fetch_data(self):
        with self._fetch_lock:
            now = time.monotonic()
            if now - self._last_attempt < 30:
                if self._last_response is None:
                    raise PyJWKClientConnectionError("Signing key refresh temporarily unavailable")
                return self._last_response
            self._last_attempt = now
            self._last_response = None
            self._last_response = super().fetch_data()
            return self._last_response


class AccessTokenVerifier:
    def __init__(self, config: IdentityConfig, *, key_resolver: Callable | None = None):
        self.config = config
        # Token headers can select a kid, never the URL from which keys are fetched.
        self._keys = _ThrottledJWKClient(config.jwks_url)
        self._resolve = key_resolver or self._keys.get_signing_key_from_jwt

    def verify(self, token: str) -> AccessIdentity:
        if not isinstance(token, str) or len(token) > 16384:
            raise InvalidAccessToken
        try:
            header = jwt.get_unverified_header(token)
            if (
                header.get("alg") != "RS256"
                or header.get("typ") not in ("at+jwt", "application/at+jwt")
                or not isinstance(header.get("kid"), str)
                or not 1 <= len(header["kid"]) <= 200
                or any(name in header for name in ("jku", "jwk", "x5u", "crit"))
            ):
                raise InvalidAccessToken
            resolved = self._resolve(token)
            key = resolved.key if hasattr(resolved, "key") else resolved
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.config.issuer,
                audience=self.config.audience,
                leeway=30,
                options={"require": ["iss", "aud", "sub", "exp", "iat", "jti", "client_id"]},
            )
            for name in ("sub", "jti", "client_id"):
                if (
                    not isinstance(claims[name], str)
                    or not 1 <= len(claims[name]) <= 300
                    or not claims[name].strip()
                    or any(ord(char) < 32 for char in claims[name])
                ):
                    raise InvalidAccessToken
            if (
                type(claims["iat"]) is not int
                or type(claims["exp"]) is not int
                or not 0 < claims["exp"] - claims["iat"] <= 900
            ):
                raise InvalidAccessToken
            scope = claims.get("scope", "")
            if not isinstance(scope, str) or len(scope) > 1000:
                raise InvalidAccessToken
            return AccessIdentity(
                Principal(self.config.issuer, claims["sub"]), frozenset(scope.split())
            )
        except PyJWKClientConnectionError as exc:
            raise IdentityUnavailable from exc
        except (PyJWTError, ValueError, TypeError) as exc:
            raise InvalidAccessToken from exc
