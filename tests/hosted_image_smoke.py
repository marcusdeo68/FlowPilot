"""Run inside the isolated hosted workspace container."""

import argparse
import http.client
import os
from contextlib import closing

from flowpilot_api.check_railway import CHECKS

PUBLIC_HOST = "flowpilot-ci.up.railway.app"
PROBE_HOST = "healthcheck.railway.app"


def expect_response(
    path: str,
    status: int,
    *,
    host: str = PUBLIC_HOST,
    forwarded_scheme: str | None = "https",
    headers: dict[str, str] | None = None,
) -> tuple[bytes, str]:
    request_headers = {"Host": host}
    if forwarded_scheme is not None:
        request_headers["X-Forwarded-Proto"] = forwarded_scheme
    with closing(http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)) as connection:
        connection.request("GET", path, headers=request_headers)
        with connection.getresponse() as response:
            assert response.status == status, (
                f"{host}{path}: expected {status}, got {response.status}"
            )
            for name, value in (headers or {}).items():
                assert response.getheader(name) == value, f"{host}{path}: unexpected {name}"
            return response.read(), response.getheader("Content-Type", "").split(";", 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before-migration", "after-migration"))
    phase = parser.parse_args().phase
    assert os.getuid() != 0, "The workspace container must run as a non-root user"
    expect_response("/healthz", 200, host=PROBE_HOST, forwarded_scheme=None)
    expect_response(
        "/readyz",
        503 if phase == "before-migration" else 200,
        host=PROBE_HOST,
        forwarded_scheme=None,
    )
    if phase == "after-migration":
        for path, status, headers in CHECKS:
            body, content_type = expect_response(
                path, status, headers={"Cache-Control": "no-store", **headers}
            )
            if path == "/api/v2/workspace":
                assert content_type == "text/html"
                assert b'data-login-enabled="false"' in body
        expect_response("/api/v2/workspace", 404, forwarded_scheme=None)
        expect_response("/api/v2/workspace", 404, host=PROBE_HOST)
        for extension, expected_type in (("js", "text/javascript"), ("css", "text/css")):
            body, content_type = expect_response(
                f"/api/v2/workspace.{extension}", 200, headers={"Cache-Control": "no-store"}
            )
            assert body and content_type == expected_type
    print(f"Hosted image smoke checks passed ({phase}).")


if __name__ == "__main__":
    main()
