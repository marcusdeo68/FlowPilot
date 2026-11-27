"""Check a deployed Railway pilot using public, credential-free GET requests."""

import argparse
import http.client
import ssl
from collections.abc import Sequence

from flowpilot_api.browser_sessions import BrowserConfig

CHECKS = (
    ("/", 307, {"Location": "/api/v2/workspace"}),
    ("/api/v2/workspace", 200, {}),
    ("/api/v2/session", 401, {}),
    ("/healthz", 404, {}),
    ("/readyz", 404, {}),
)


def check(origin: str) -> list[str]:
    host = BrowserConfig(origin, hosted=True).authority
    if not host.endswith(".up.railway.app"):
        raise ValueError("Use the public Railway HTTPS origin")
    failures = []
    for path, expected_status, expected_headers in CHECKS:
        connection = http.client.HTTPSConnection(host, timeout=15)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            if response.status != expected_status:
                failures.append(f"{path}: expected {expected_status}, got {response.status}")
            else:
                for name, value in {"Cache-Control": "no-store", **expected_headers}.items():
                    if response.getheader(name) != value:
                        failures.append(f"{path}: unexpected {name}")
                content_type = response.getheader("Content-Type") or ""
                if path == "/api/v2/workspace" and content_type.split(";", 1)[0] != "text/html":
                    failures.append(f"{path}: expected HTML")
        except (OSError, http.client.HTTPException) as exc:
            category = (
                "TLS certificate verification failed"
                if isinstance(exc, ssl.SSLCertVerificationError)
                else type(exc).__name__
            )
            failures.append(f"{path}: {category}")
        finally:
            connection.close()
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", help="Canonical https://<service>.up.railway.app origin")
    args = parser.parse_args(argv)
    try:
        failures = check(args.origin)
    except ValueError as exc:
        parser.error(str(exc))
    if failures:
        for failure in failures:
            print(failure)
        return 1
    print(f"Passed {len(CHECKS)} public HTTPS checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
