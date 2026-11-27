"""Authenticate a controlled proxy before restoring the browser's public origin."""

import hmac
import os
import re
from dataclasses import dataclass

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from flowpilot_api.browser_sessions import BrowserConfig

PROXY_HEADER = b"x-flowpilot-proxy-secret"
PROBE_PATHS = ("/healthz", "/readyz")
RAILWAY_PROBE_HOST = "healthcheck.railway.app"


def railway_edge_enabled(
    browser: BrowserConfig | None, probe_host: str | None, proxy: "ProxyIngress | None"
) -> bool:
    enabled = os.environ.get("FLOWPILOT_RAILWAY_EDGE", "0")
    if enabled not in ("0", "1"):
        raise ValueError("Set FLOWPILOT_RAILWAY_EDGE to 0 or 1")
    if enabled == "0":
        return False
    if (
        browser is None
        or not browser.hosted
        or not browser.authority.endswith(".up.railway.app")
        or probe_host != RAILWAY_PROBE_HOST
        or proxy is not None
        or os.environ.get("FORWARDED_ALLOW_IPS")
    ):
        raise ValueError(
            "Railway edge requires a hosted Railway origin, the Railway probe host, "
            "empty FORWARDED_ALLOW_IPS, and no authenticated proxy settings"
        )
    return True


class RailwayIngress:
    """Trust Railway HTTPS metadata within the dedicated pilot environment."""

    def __init__(self, app: ASGIApp, public_host: str):
        self.app = app
        self.public_host = public_host.encode("ascii")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http" or (scope["method"] == "GET" and scope["path"] in PROBE_PATHS):
            await self.app(scope, receive, send)
            return
        headers = scope["headers"]
        hosts = [value for name, value in headers if name == b"host"]
        schemes = [value for name, value in headers if name == b"x-forwarded-proto"]
        if hosts != [self.public_host] or schemes != [b"https"]:
            response = JSONResponse(
                {"detail": "Not found"}, status_code=404, headers={"Cache-Control": "no-store"}
            )
            await response(scope, receive, send)
            return
        headers = [
            (name, value)
            for name, value in headers
            if name != b"forwarded" and not name.startswith(b"x-forwarded-")
        ]
        await self.app({**scope, "scheme": "https", "headers": headers}, receive, send)


@dataclass(frozen=True, repr=False)
class ProxyIngress:
    public_host: str
    upstream_host: bytes
    secret: bytes

    @classmethod
    def from_environment(
        cls, browser: BrowserConfig | None, probe_host: str | None
    ) -> "ProxyIngress | None":
        upstream = os.environ.get("FLOWPILOT_PROXY_UPSTREAM_HOST")
        secret = os.environ.get("FLOWPILOT_PROXY_SECRET")
        if upstream is None and secret is None:
            return None
        if (
            browser is None
            or not browser.hosted
            or probe_host is None
            or upstream is None
            or secret is None
        ):
            raise ValueError(
                "Proxy ingress requires hosted mode, a probe host, and both proxy settings"
            )
        if not re.fullmatch(r"[a-f0-9]{64}", secret):
            raise ValueError("FLOWPILOT_PROXY_SECRET must be a 64-character lowercase hex secret")
        upstream_host = BrowserConfig(f"https://{upstream}", hosted=True).authority
        if upstream_host in (browser.authority, probe_host):
            raise ValueError("Proxy upstream host must differ from the public and probe hosts")
        return cls(browser.authority, upstream_host.encode("ascii"), secret.encode("ascii"))


class AuthenticatedIngress:
    def __init__(self, app: ASGIApp, config: ProxyIngress):
        self.app = app
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["method"] == "GET" and scope["path"] in PROBE_PATHS:
            await self.app(scope, receive, send)
            return
        headers = scope["headers"]
        hosts = [value for name, value in headers if name == b"host"]
        secrets = [value for name, value in headers if name == PROXY_HEADER]
        if (
            hosts != [self.config.upstream_host]
            or len(secrets) != 1
            or not hmac.compare_digest(secrets[0], self.config.secret)
        ):
            response = JSONResponse(
                {"detail": "Not found"}, status_code=404, headers={"Cache-Control": "no-store"}
            )
            await response(scope, receive, send)
            return
        # Browser Origin and cookies pass through for the existing session and CSRF checks.
        public_headers = [
            (name, value)
            for name, value in headers
            if name not in (b"host", b"forwarded", PROXY_HEADER)
            and not name.startswith(b"x-forwarded-")
        ]
        public_headers.append((b"host", self.config.public_host.encode("ascii")))
        await self.app(
            {
                **scope,
                "scheme": "https",
                "server": (self.config.public_host, 443),
                "headers": public_headers,
            },
            receive,
            send,
        )
