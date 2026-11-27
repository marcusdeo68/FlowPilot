from types import SimpleNamespace

import pytest
from flowpilot_api import check_railway

ORIGIN = "https://flowpilot-test.up.railway.app"


@pytest.mark.parametrize("failing_probe", [False, True])
def test_railway_smoke_uses_public_gets_and_reports_probe_leaks(monkeypatch, capsys, failing_probe):
    seen = []
    closed = []
    routes = {
        "/": (307, {"Location": "/api/v2/workspace"}),
        "/api/v2/workspace": (200, {"Content-Type": "text/html; charset=utf-8"}),
        "/api/v2/session": (401, {}),
        "/healthz": (404, {}),
        "/readyz": (200 if failing_probe else 404, {}),
    }

    class Connection:
        def __init__(self, host, *, timeout):
            assert host == "flowpilot-test.up.railway.app"
            assert timeout == 15

        def request(self, method, path):
            assert method == "GET"
            self.path = path
            seen.append(path)

        def getresponse(self):
            status, headers = routes[self.path]
            return SimpleNamespace(
                status=status, getheader={"Cache-Control": "no-store", **headers}.get
            )

        def close(self):
            closed.append(self.path)

    monkeypatch.setattr(check_railway.http.client, "HTTPSConnection", Connection)
    assert check_railway.main([ORIGIN]) == int(failing_probe)
    assert seen == closed == list(routes)
    output = capsys.readouterr().out
    if failing_probe:
        assert "/readyz: expected 404, got 200" in output
    else:
        assert "Passed 5 public HTTPS checks." in output


@pytest.mark.parametrize("origin", ["http://flowpilot-test.up.railway.app", "https://example.test"])
def test_railway_smoke_rejects_other_origins(origin):
    with pytest.raises(ValueError):
        check_railway.check(origin)
