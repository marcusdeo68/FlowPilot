"""Strict RS256 JWT access-token verification; no login, issuance, or role trust."""

import os
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
    def from_environment(cls):
        names = ("FLOWPILOT_OIDC_ISSUER", "FLOWPILOT_OIDC_AUDIENCE", "FLOWPILOT_OIDC_JWKS_URL")
        values = [os.environ.get(name) for name in names]
        if not all(values):
            raise ValueError(
                "Configure issuer, API audience, and JWKS URL before starting workspace API"
            )
        return cls(*values)


@dataclass(frozen=True)
class AccessIdentity:
    principal: Principal
    scopes: frozenset[str]


class AccessTokenVerifier:
    def __init__(self, config: IdentityConfig, *, key_resolver: Callable | None = None):
        self.config = config
        # Token headers can select a kid, never the URL from which keys are fetched.
        self._keys = PyJWKClient(config.jwks_url, cache_keys=False, lifespan=300, timeout=5)
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
