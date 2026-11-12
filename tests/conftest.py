import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from flowpilot_api.main import app
from flowpilot_api.work_service import WorkService
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema


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


@pytest.fixture
def pg():
    url = os.environ.get("FLOWPILOT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set FLOWPILOT_TEST_DATABASE_URL for real PostgreSQL checks")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or not (parsed.database or "").endswith("_test"):
        pytest.fail("Integration tests require a PostgreSQL database ending in _test")
    schema = "fp_test_" + uuid4().hex
    root = create_engine(parsed, hide_parameters=True)
    with root.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(
        parsed, connect_args={"options": f"-csearch_path={schema}"}, hide_parameters=True
    )
    config = Config("alembic.ini")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine, config
    finally:
        engine.dispose()
        # The target is the exact random schema created above, never public/user schemas.
        with root.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        root.dispose()


@pytest.fixture
def setup(pg):
    engine, _ = pg
    workspace, other = uuid4(), uuid4()
    users = {name: uuid4() for name in ("owner", "member", "observer", "outsider")}
    with engine.begin() as connection:
        for label, value in (("Synthetic A", workspace), ("Synthetic B", other)):
            connection.execute(
                text("INSERT INTO workspaces (id, name) VALUES (:id, :name)"),
                {"id": value, "name": label},
            )
        for name, user_id in users.items():
            connection.execute(
                text("INSERT INTO users (id, issuer, subject) VALUES (:id, 'test', :name)"),
                {"id": user_id, "name": name},
            )
            connection.execute(
                text("""INSERT INTO memberships (workspace_id, user_id, role)
                VALUES (:workspace, :user, :role)"""),
                {
                    "workspace": other if name == "outsider" else workspace,
                    "user": user_id,
                    "role": "owner" if name == "outsider" else name,
                },
            )
    return WorkService(engine), workspace, other, users


@pytest.fixture
def workspace_client(setup, token_tools):
    from fastapi.testclient import TestClient
    from flowpilot_api.workspace_api import create_workspace_app

    service, workspace, other, users = setup
    config, verifier, sign = token_tools
    with service.engine.begin() as connection:
        connection.execute(text("UPDATE users SET issuer=:issuer"), {"issuer": config.issuer})
    app = create_workspace_app(engine=service.engine, verifier=verifier)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, workspace, other, users, sign
