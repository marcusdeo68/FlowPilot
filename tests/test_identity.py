import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from flowpilot_api.identity import (
    AccessTokenVerifier,
    IdentityConfig,
    IdentityUnavailable,
    InvalidAccessToken,
)


def test_verified_identity_and_scopes(token_tools):
    config, verifier, sign = token_tools
    identity = verifier.verify(sign())
    assert identity.principal.issuer == config.issuer
    assert identity.principal.subject == "owner"
    assert identity.scopes == frozenset({"flowpilot:read", "flowpilot:write"})


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://other.example"},
        {"aud": "other-api"},
        {"exp": 0},
        {"iat": 0},
        {"sub": ""},
        {"sub": ["owner"]},
        {"scope": ["flowpilot:write"]},
        {"client_id": ""},
        {"jti": ""},
    ],
)
def test_bad_claims_rejected(token_tools, overrides):
    _, verifier, sign = token_tools
    with pytest.raises(InvalidAccessToken):
        verifier.verify(sign(overrides=overrides))


@pytest.mark.parametrize("field", ["iss", "aud", "sub", "exp", "iat", "jti", "client_id"])
def test_required_claims(token_tools, field):
    _, verifier, sign = token_tools
    with pytest.raises(InvalidAccessToken):
        verifier.verify(sign(remove=[field]))


@pytest.mark.parametrize(
    "headers",
    [
        {"typ": "JWT"},
        {"kid": "unknown"},
        {"jku": "https://attacker.example/keys"},
        {"jwk": {}},
        {"x5u": "https://attacker.example/cert"},
        {"crit": ["custom"]},
    ],
)
def test_header_confusion_rejected(token_tools, headers):
    _, verifier, sign = token_tools
    with pytest.raises(InvalidAccessToken):
        verifier.verify(sign(headers=headers))


def test_signature_and_symmetric_algorithm_rejected(token_tools):
    config, verifier, sign = token_tools
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wrong_verifier = AccessTokenVerifier(config, key_resolver=lambda _: wrong_key.public_key())
    with pytest.raises(InvalidAccessToken):
        wrong_verifier.verify(sign())
    with pytest.raises(InvalidAccessToken):
        verifier.verify(
            jwt.encode(
                {},
                "synthetic-secret-never-a-real-token",
                algorithm="HS256",
                headers={"kid": "synthetic-key", "typ": "at+jwt"},
            )
        )


def test_future_and_excessive_lifetimes_rejected(token_tools):
    _, verifier, sign = token_tools
    now = int(time.time())
    for overrides in (
        {"iat": now + 300, "exp": now + 600},
        {"exp": now + 3600},
        {"iat": str(now)},
        {"nbf": now + 300},
    ):
        with pytest.raises(InvalidAccessToken):
            verifier.verify(sign(overrides=overrides))


def test_invalid_config_and_missing_config(monkeypatch):
    for name in ("FLOWPILOT_OIDC_ISSUER", "FLOWPILOT_OIDC_AUDIENCE", "FLOWPILOT_OIDC_JWKS_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError):
        IdentityConfig.from_environment()
    for issuer, jwks in (
        ("http://identity.example", "https://identity.example/jwks"),
        ("https://identity.example", "https://other.example/jwks"),
    ):
        with pytest.raises(ValueError):
            IdentityConfig(issuer, "flowpilot-api", jwks)


def test_network_failure_never_accepts_token(token_tools):
    config, _, sign = token_tools

    def unavailable(_):
        raise jwt.PyJWKClientConnectionError("Synthetic unavailable server")

    verifier = AccessTokenVerifier(config, key_resolver=unavailable)
    with pytest.raises(IdentityUnavailable):
        verifier.verify(sign())


@pytest.mark.parametrize("field", ["ISSUER", "AUDIENCE", "JWKS_URL"])
def test_identity_environment_requires_each_setting(monkeypatch, field):
    values = {
        "ISSUER": "https://identity.example",
        "AUDIENCE": "flowpilot-api",
        "JWKS_URL": "https://identity.example/keys",
    }
    for name, value in values.items():
        monkeypatch.setenv("FLOWPILOT_OIDC_" + name, value)
    assert IdentityConfig.from_environment() == IdentityConfig(
        values["ISSUER"], values["AUDIENCE"], values["JWKS_URL"]
    )
    setting = "FLOWPILOT_OIDC_" + field
    monkeypatch.setenv(setting, "")
    with pytest.raises(ValueError, match="Configure issuer"):
        IdentityConfig.from_environment()
    monkeypatch.delenv(setting)
    with pytest.raises(ValueError, match="Configure issuer"):
        IdentityConfig.from_environment()


def test_jwks_resolution_uses_configured_keys(token_tools, monkeypatch):
    config, _, sign = token_tools
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(sign(), options={"verify_signature": False})
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "jwks-key", "typ": "at+jwt"})
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update({"kid": "jwks-key", "use": "sig", "alg": "RS256"})
    verifier = AccessTokenVerifier(config)
    monkeypatch.setattr(verifier._keys, "fetch_data", lambda: {"keys": [jwk]})
    assert verifier.verify(token).principal.subject == "owner"


@pytest.mark.parametrize("token", ["", "not-a-token", "x" * 16385])
def test_malformed_or_oversize_token(token_tools, token):
    _, verifier, _ = token_tools
    with pytest.raises(InvalidAccessToken):
        verifier.verify(token)


@pytest.mark.parametrize("subject", ["   ", "bad\x00subject", "bad\nsubject"])
def test_subject_control_characters_rejected(token_tools, subject):
    _, verifier, sign = token_tools
    with pytest.raises(InvalidAccessToken):
        verifier.verify(sign(subject))


def test_jwks_network_refresh_is_throttled(monkeypatch):
    from flowpilot_api.identity import _ThrottledJWKClient

    calls = []
    clock = [100.0]
    monkeypatch.setattr("flowpilot_api.identity.time.monotonic", lambda: clock[0])

    def fetch(_):
        calls.append("request")
        return {"keys": []}

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", fetch)
    keys = _ThrottledJWKClient("https://identity.example/jwks")
    keys.fetch_data()
    keys.fetch_data()
    assert len(calls) == 1
    clock[0] += 31
    keys.fetch_data()
    assert len(calls) == 2


def test_failed_key_refresh_is_fail_closed_and_backed_off(monkeypatch):
    from flowpilot_api.identity import _ThrottledJWKClient

    calls = []

    def fetch(_):
        calls.append("request")
        raise jwt.PyJWKClientConnectionError("Synthetic outage")

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", fetch)
    keys = _ThrottledJWKClient("https://identity.example/jwks")
    for _ in range(2):
        with pytest.raises(jwt.PyJWKClientConnectionError):
            keys.fetch_data()
    assert len(calls) == 1
