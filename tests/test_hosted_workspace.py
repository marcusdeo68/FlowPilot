from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from flowpilot_api.browser_sessions import BrowserConfig
from flowpilot_api.login import LOGIN_PATH, LoginConfig
from flowpilot_api.workspace_api import create_workspace_app
from sqlalchemy import create_engine
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

ORIGIN = "https://app.flowpilot.example"
PROBE_HOST = "healthcheck.railway.app"
UPSTREAM = "flowpilot-test.up.railway.app"
SECRET = "0123456789abcdef" * 4
PROXY_HEADER = "X-FlowPilot-Proxy-Secret"
RAILWAY_ORIGIN = f"https://{UPSTREAM}"


@pytest.mark.parametrize(
    "origin",
    [
        "http://app.flowpilot.example",
        "https://APP.flowpilot.example",
        "https://app.flowpilot.example:443",
        "https://app.flowpilot.example/",
        "https://app.flowpilot.example?x=1",
        "https://app.flowpilot.example#login",
        "https://user@app.flowpilot.example",
        "https://127.0.0.1",
        "https://localhost",
        "https://app.localhost",
        "https://127.0.0.0x1",
    ],
)
def test_hosted_origin_requires_canonical_https_dns(origin):
    with pytest.raises(ValueError, match="canonical HTTPS DNS origin"):
        BrowserConfig(origin, hosted=True)


def test_hosted_proxy_gate_preserves_exact_host_and_health_checks(token_tools, monkeypatch):
    _, verifier, _ = token_tools
    monkeypatch.setenv("FLOWPILOT_HOSTED", "1")
    monkeypatch.delenv("FLOWPILOT_BROWSER_ORIGIN", raising=False)
    with pytest.raises(ValueError, match="requires FLOWPILOT_BROWSER_ORIGIN"):
        create_workspace_app(verifier=verifier)
    monkeypatch.setenv("FLOWPILOT_BROWSER_ORIGIN", ORIGIN)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    try:
        app = create_workspace_app(engine=engine, verifier=verifier)
        proxy = ProxyHeadersMiddleware(app, trusted_hosts=["192.0.2.5"])
        endpoint = "http://app.flowpilot.example"
        with TestClient(proxy, base_url=endpoint, client=("192.0.2.5", 50000)) as client:
            https = {"X-Forwarded-Proto": "https"}
            home = client.get("/", headers=https, follow_redirects=False)
            assert home.status_code == 307
            assert home.headers["location"] == "/api/v2/workspace"
            assert client.get("/api/v2/workspace", headers=https).status_code == 200
            assert client.get("/api/v2/workspace").status_code == 400
            assert client.get("/", headers={**https, "Host": "wrong.example"}).status_code == 400
            assert (
                client.get(
                    "/",
                    headers={
                        **https,
                        "Host": "wrong.example",
                        "X-Forwarded-Host": "app.flowpilot.example",
                    },
                ).status_code
                == 400
            )
            assert client.get("/healthz", headers={"Host": "192.0.2.9:8000"}).json() == {
                "status": "ok",
            }
            assert client.get("/readyz", headers={"Host": "192.0.2.9:8000"}).status_code == 503
            assert client.post("/healthz", headers={"Host": "192.0.2.9:8000"}).status_code == 400
            assert client.get("/commitments", headers=https).status_code == 404
        with TestClient(proxy, base_url=endpoint, client=("192.0.2.6", 50000)) as client:
            assert (
                client.get("/api/v2/workspace", headers={"X-Forwarded-Proto": "https"}).status_code
                == 400
            )
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_hosted_readiness_on_separate_probe_host(pg, token_tools, monkeypatch):
    _, verifier, _ = token_tools
    monkeypatch.setenv("FLOWPILOT_PROBE_HOST", PROBE_HOST)
    app = create_workspace_app(engine=pg[0], verifier=verifier, hosted=True, browser_origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/readyz").status_code == 404
        assert client.get("/healthz").status_code == 404
        assert client.get("/readyz", headers={"X-Forwarded-Host": PROBE_HOST}).status_code == 404
        probe_url = f"http://{PROBE_HOST}/readyz"
        assert client.get(probe_url).json() == {"status": "ready"}
        assert (
            client.get(probe_url, headers=[("Host", PROBE_HOST), ("Host", PROBE_HOST)]).status_code
            == 404
        )
        assert client.post(probe_url).status_code == 400
        assert client.get(f"https://{PROBE_HOST}/api/v2/workspace").status_code == 400
        assert client.get("/api/v2/workspace").status_code == 200


@pytest.mark.parametrize("probe_host", ["app.flowpilot.example", "probe.railway.app/path", ""])
def test_hosted_rejects_invalid_or_public_probe_host(token_tools, monkeypatch, probe_host):
    _, verifier, _ = token_tools
    monkeypatch.setenv("FLOWPILOT_PROBE_HOST", probe_host)
    with pytest.raises(ValueError, match="must differ|canonical HTTPS DNS origin"):
        create_workspace_app(verifier=verifier, hosted=True, browser_origin=ORIGIN)


@pytest.mark.parametrize(
    ("upstream", "secret", "probe_host"),
    [
        (UPSTREAM, None, PROBE_HOST),
        (UPSTREAM, SECRET, None),
        (UPSTREAM, "short", PROBE_HOST),
        ("app.flowpilot.example", SECRET, PROBE_HOST),
        (PROBE_HOST, SECRET, PROBE_HOST),
    ],
)
def test_authenticated_ingress_fails_on_invalid_configuration(
    monkeypatch, upstream, secret, probe_host
):
    for key, value in (
        ("FLOWPILOT_PROXY_UPSTREAM_HOST", upstream),
        ("FLOWPILOT_PROXY_SECRET", secret),
        ("FLOWPILOT_PROBE_HOST", probe_host),
    ):
        monkeypatch.delenv(key, raising=False)
        if value is not None:
            monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="Proxy ingress|PROXY_SECRET|upstream host"):
        create_workspace_app(hosted=True, browser_origin=ORIGIN)


@pytest.mark.postgres
def test_authenticated_ingress_rejects_direct_and_ambiguous_requests(pg, token_tools, monkeypatch):
    _, verifier, _ = token_tools
    monkeypatch.setenv("FLOWPILOT_PROXY_UPSTREAM_HOST", UPSTREAM)
    monkeypatch.setenv("FLOWPILOT_PROXY_SECRET", SECRET)
    monkeypatch.setenv("FLOWPILOT_PROBE_HOST", PROBE_HOST)
    app = create_workspace_app(engine=pg[0], verifier=verifier, hosted=True, browser_origin=ORIGIN)
    with TestClient(app, base_url=f"http://{UPSTREAM}") as client:
        assert client.get("/", headers={"X-Forwarded-Proto": "https"}).status_code == 404
        assert client.get(f"{ORIGIN}/").status_code == 404
        assert client.get("/", headers={PROXY_HEADER: "bad"}).status_code == 404
        assert (
            client.get("/", headers=[(PROXY_HEADER, SECRET), (PROXY_HEADER, SECRET)]).status_code
            == 404
        )
        assert (
            client.get("/", headers={PROXY_HEADER: SECRET, "Host": "wrong.example"}).status_code
            == 404
        )
        home = client.get("/", headers={PROXY_HEADER: SECRET}, follow_redirects=False)
        assert home.status_code == 307
        assert home.headers["location"] == "/api/v2/workspace"
        assert client.get("/readyz", headers={PROXY_HEADER: SECRET}).status_code == 404
        assert client.get("/readyz", headers={"Host": PROBE_HOST}).status_code == 200


@pytest.mark.parametrize("problem", ["mode", "origin", "probe", "wildcard", "proxy"])
def test_railway_edge_rejects_incompatible_configuration(monkeypatch, problem):
    monkeypatch.setenv("FLOWPILOT_RAILWAY_EDGE", "yes" if problem == "mode" else "1")
    monkeypatch.setenv(
        "FLOWPILOT_PROBE_HOST", "wrong.example" if problem == "probe" else PROBE_HOST
    )
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*" if problem == "wildcard" else "")
    if problem == "proxy":
        monkeypatch.setenv("FLOWPILOT_PROXY_UPSTREAM_HOST", "worker-backend.example")
        monkeypatch.setenv("FLOWPILOT_PROXY_SECRET", SECRET)
    with pytest.raises(ValueError, match="RAILWAY_EDGE|Railway edge"):
        create_workspace_app(
            hosted=True, browser_origin=ORIGIN if problem == "origin" else RAILWAY_ORIGIN
        )


@pytest.mark.postgres
def test_railway_edge_requires_exact_host_and_one_https_header(pg, token_tools, monkeypatch):
    _, verifier, _ = token_tools
    monkeypatch.setenv("FLOWPILOT_RAILWAY_EDGE", "1")
    monkeypatch.setenv("FLOWPILOT_PROBE_HOST", PROBE_HOST)
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "")
    app = create_workspace_app(
        engine=pg[0], verifier=verifier, hosted=True, browser_origin=RAILWAY_ORIGIN
    )
    with TestClient(app, base_url=f"http://{UPSTREAM}") as client:
        for headers in (
            {},
            {"X-Forwarded-Proto": "http"},
            {"X-Forwarded-Proto": "http, https"},
            {"Forwarded": "proto=https"},
            {"X-Forwarded-Proto": "https", "Host": "wrong.example"},
            [("X-Forwarded-Proto", "https"), ("X-Forwarded-Proto", "https")],
        ):
            assert client.get("/", headers=headers).status_code == 404
        assert client.get(f"{RAILWAY_ORIGIN}/").status_code == 404
        https = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "spoofed.example"}
        assert client.get("/api/v2/workspace", headers=https).status_code == 200
        assert client.get("/readyz", headers=https).status_code == 404
        assert client.get("/readyz", headers={"Host": PROBE_HOST}).status_code == 200


@pytest.mark.postgres
@pytest.mark.parametrize("proxy", [False, True, "railway"])
def test_hosted_callback_and_session_use_configured_origin(pg, token_tools, monkeypatch, proxy):
    _, verifier, sign = token_tools
    origin = RAILWAY_ORIGIN if proxy == "railway" else ORIGIN
    proxy_headers = {}
    if proxy == "railway":
        monkeypatch.setenv("FLOWPILOT_RAILWAY_EDGE", "1")
        monkeypatch.setenv("FLOWPILOT_PROBE_HOST", PROBE_HOST)
        monkeypatch.setenv("FORWARDED_ALLOW_IPS", "")
        proxy_headers = {"X-Forwarded-Proto": "https"}
    elif proxy:
        monkeypatch.setenv("FLOWPILOT_PROXY_UPSTREAM_HOST", UPSTREAM)
        monkeypatch.setenv("FLOWPILOT_PROXY_SECRET", SECRET)
        monkeypatch.setenv("FLOWPILOT_PROBE_HOST", PROBE_HOST)
        proxy_headers = {"Host": UPSTREAM, PROXY_HEADER: SECRET}
    login = LoginConfig(
        "synthetic-client", "https://identity.example/authorize", "https://identity.example/token"
    )
    app = create_workspace_app(
        engine=pg[0],
        verifier=verifier,
        hosted=True,
        browser_origin=origin,
        login_config=login,
        login_exchange=lambda *_: sign("staging-user"),
    )
    with TestClient(app, base_url=origin, headers=proxy_headers) as client:
        start = client.post(LOGIN_PATH, headers={"Origin": origin}, follow_redirects=False)
        assert start.status_code == 303
        assert "Secure" in start.headers["set-cookie"]
        query = parse_qs(urlsplit(start.headers["location"]).query)
        assert query["redirect_uri"] == [origin + LOGIN_PATH + "/callback"]
        data = {"state": query["state"][0], "iss": "https://identity.example", "code": "synthetic"}
        assert client.get(LOGIN_PATH + "/callback", params=data).status_code == 200
        issued = client.post(LOGIN_PATH + "/complete", data=data, headers={"Origin": origin})
        assert issued.status_code == 200
        cookie = next(
            c for c in issued.headers.get_list("set-cookie") if c.startswith("flowpilot_session=")
        )
        assert all(attr in cookie for attr in ("Secure", "HttpOnly", "SameSite=strict"))
        session = client.get("/api/v2/session")
        assert session.status_code == 200
        headers = {"Origin": origin, "X-CSRF-Token": session.json()["csrf_token"]}
        assert (
            client.post(
                "/api/v2/workspaces",
                json={"name": "Staging"},
                headers={**headers, "Origin": "https://other.example"},
            ).status_code
            == 403
        )
        assert (
            client.post("/api/v2/workspaces", json={"name": "Staging"}, headers=headers).status_code
            == 201
        )
