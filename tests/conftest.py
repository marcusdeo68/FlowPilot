import pytest
from fastapi.testclient import TestClient
from flowpilot_api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOWPILOT_DB_PATH", str(tmp_path / "test.sqlite3"))
    with TestClient(app, base_url="http://127.0.0.1") as session:
        yield session


@pytest.fixture(scope="session")
def token_tools():
    import time
    from uuid import uuid4

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from flowpilot_api.identity import AccessTokenVerifier, IdentityConfig

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = IdentityConfig(
        "https://identity.example", "flowpilot-api", "https://identity.example/jwks"
    )

    def resolve(token):
        if jwt.get_unverified_header(token)["kid"] != "synthetic-key":
            raise jwt.PyJWKClientError("Unknown key")
        return key.public_key()

    verifier = AccessTokenVerifier(config, key_resolver=resolve)

    def sign(subject="owner", *, overrides=None, headers=None, remove=()):
        now = int(time.time())
        claims = {
            "iss": config.issuer,
            "aud": config.audience,
            "sub": subject,
            "iat": now,
            "exp": now + 300,
            "jti": str(uuid4()),
            "client_id": "synthetic-client",
            "scope": "flowpilot:read flowpilot:write",
        }
        claims.update(overrides or {})
        for field in remove:
            claims.pop(field, None)
        token_headers = {"typ": "at+jwt", "kid": "synthetic-key"}
        token_headers.update(headers or {})
        return jwt.encode(claims, key, algorithm="RS256", headers=token_headers)

    return config, verifier, sign
