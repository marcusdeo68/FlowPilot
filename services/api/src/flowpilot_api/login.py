"""Opt-in public-client OAuth code login; no ID-token or provider-data scopes."""

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from http.client import HTTPException as HTTPClientError
from http.client import HTTPSConnection
from socket import SHUT_RDWR, socket
from threading import Timer
from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from flowpilot_api.browser_sessions import (
    COOKIE_NAME,
    COOKIE_PATH,
    InvalidSession,
    SessionUnavailable,
)
from flowpilot_api.identity import AccessTokenVerifier, IdentityUnavailable, InvalidAccessToken
from flowpilot_api.login_transactions import (
    InvalidLoginTransaction,
    LoginStorageUnavailable,
    LoginTransactions,
)
from flowpilot_api.session_routes import BrowserAuth, session_cookie
from flowpilot_api.workspace_ui import WORKSPACE_URL

LOGIN_PATH = "/api/v2/login"
PENDING_COOKIE = "flowpilot_login"
SCOPES = "flowpilot:read flowpilot:write"
Exchange = Callable[[str, str], str]
EXCHANGE_SECONDS = 5.0


@dataclass(frozen=True)
class LoginConfig:
    client_id: str
    authorization_url: str
    token_url: str

    def __post_init__(self):
        if (
            not 1 <= len(self.client_id) <= 300
            or not self.client_id.strip()
            or any(ord(c) < 33 or ord(c) == 127 for c in self.client_id)
        ):
            raise ValueError("Login client ID must be bounded and contain no whitespace/controls")
        for url in (self.authorization_url, self.token_url):
            parsed = urlsplit(url)
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError("Login endpoint port must be valid") from exc
            if (
                len(url) > 1000
                or any(ord(c) <= 32 or ord(c) == 127 for c in url)
                or parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or "\\" in url
                or port == 0
                or parsed.geturl() != url
                or not url.isascii()
                or not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]{1,5})?", parsed.netloc)
            ):
                raise ValueError("Login endpoints must be explicit trusted HTTPS URLs")

    @classmethod
    def from_environment(cls) -> "LoginConfig | None":
        values = [
            os.environ.get("FLOWPILOT_LOGIN_" + name)
            for name in ("CLIENT_ID", "AUTHORIZATION_URL", "TOKEN_URL")
        ]
        if all(value is None for value in values):
            return None
        if not all(values):
            raise ValueError("Configure all three login settings, or omit them all")
        return cls(values[0] or "", values[1] or "", values[2] or "")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


class TokenExchange:
    def __init__(self, config: LoginConfig, redirect: str):
        self.config, self.redirect = config, redirect

    def __call__(self, code: str, verifier: str) -> str:
        data = urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": self.config.client_id,
                "redirect_uri": self.redirect,
            }
        ).encode("ascii")
        endpoint = urlsplit(self.config.token_url)
        # A direct TLS connection has no redirect/proxy/retry machinery.
        connection = HTTPSConnection(
            endpoint.hostname or "", endpoint.port, timeout=EXCHANGE_SECONDS
        )
        deadline = 0.0
        active_socket: socket | None = None

        def abort():
            # A socket timeout alone cannot bound a stream of slowly arriving
            # header bytes. Interrupt the actual socket at the overall deadline.
            target = active_socket or connection.sock
            if target is not None:
                try:
                    target.shutdown(SHUT_RDWR)
                except OSError:
                    pass

        def remaining():
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError
            # HTTPResponse closes a Connection:close socket at body EOF.
            # The deadline still applies, but there is no socket left to tune.
            if active_socket is not None and active_socket.fileno() >= 0:
                active_socket.settimeout(left)

        watchdog: Timer | None = None
        try:
            # Standard connect/TLS socket timeouts apply here; OS DNS resolution
            # is not cancellable by this synchronous client. The response budget
            # starts after TLS so its watchdog always has the actual TLS socket.
            connection.connect()
            active_socket = connection.sock
            deadline = time.monotonic() + EXCHANGE_SECONDS
            watchdog = Timer(EXCHANGE_SECONDS, abort)
            watchdog.daemon = True
            watchdog.start()
            remaining()
            connection.request(
                "POST",
                endpoint.path or "/",
                body=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "Connection": "close",
                },
            )
            remaining()
            with connection.getresponse() as response:
                remaining()
                if (
                    response.status != 200
                    or response.headers.get_content_type() != "application/json"
                ):
                    raise ValueError("Unexpected token response")
                raw = bytearray()
                while True:
                    remaining()
                    chunk = response.read1(min(4096, 32769 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > 32768:
                        raise ValueError("Token response too large")
                remaining()
                payload = json.loads(raw, object_pairs_hook=_unique_object)
                if (
                    not isinstance(payload, dict)
                    or "error" in payload
                    or not isinstance(payload.get("token_type"), str)
                    or payload["token_type"].lower() != "bearer"
                    or not isinstance(payload.get("access_token"), str)
                    or not 1 <= len(payload["access_token"]) <= 16384
                ):
                    raise ValueError("Invalid token response")
                return payload["access_token"]
        except (OSError, HTTPClientError, ValueError, RecursionError) as exc:
            raise IdentityUnavailable from exc
        finally:
            if watchdog is not None:
                watchdog.cancel()
                watchdog.join()
            connection.close()


def _pending_cookie(request: Request) -> str:
    count = sum(
        "=" in part and part.split("=", 1)[0].strip() == PENDING_COOKIE
        for header in request.headers.getlist("cookie")
        for part in header.split(";")
    )
    value = request.cookies.get(PENDING_COOKIE)
    if count != 1 or not value or not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
        raise InvalidLoginTransaction
    return value


def _fields(raw: str, issuer: str) -> dict[str, str]:
    try:
        pairs = parse_qsl(
            raw,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=16,
            encoding="utf-8",
            errors="strict",
        )
    except ValueError as exc:
        raise InvalidLoginTransaction from exc
    fields = dict(pairs)
    if (
        len(fields) != len(pairs)
        or ("code" in fields) == ("error" in fields)
        or fields.get("iss") != issuer
        or not re.fullmatch(r"[A-Za-z0-9_-]{43}", fields.get("state", ""))
        or any(
            not v or len(v) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in v)
            for v in fields.values()
        )
    ):
        raise InvalidLoginTransaction
    # OAuth response extensions and diagnostic fields never enter the form.
    result = {"state": fields["state"], "iss": fields["iss"]}
    if "error" in fields:
        return result | {"error": "provider_error"}
    return result | {"code": fields["code"]}


class LoginFlow:
    def __init__(
        self,
        browser: BrowserAuth,
        verifier: AccessTokenVerifier,
        config: LoginConfig,
        exchange: Exchange | None = None,
    ):
        issuer = urlsplit(verifier.config.issuer)
        if any(
            urlsplit(url).netloc != issuer.netloc
            for url in (config.authorization_url, config.token_url)
        ):
            raise ValueError("Login endpoints must share the configured issuer origin")
        self.browser, self.verifier, self.config = browser, verifier, config
        self.transactions = LoginTransactions(
            browser.sessions.engine, verifier.config, browser.sessions.browser, config.client_id
        )
        self.redirect = browser.sessions.browser.origin + LOGIN_PATH + "/callback"
        self.exchange = exchange or TokenExchange(config, self.redirect)

    def _no_session(self, request: Request):
        if "authorization" in request.headers or session_cookie(request) is not None:
            raise HTTPException(409, "Sign out before starting another login")

    def _origin(self, request: Request):
        if f"{request.url.scheme}://{request.url.netloc}" != self.browser.sessions.browser.origin:
            raise InvalidLoginTransaction

    def _page(self, content: str, status: int = 200, *, authorize: bool = False) -> HTMLResponse:
        # Form navigation policies also apply to the initiation POST's redirect.
        form_action = "'self'"
        if authorize:
            form_action += " https://" + urlsplit(self.config.authorization_url).netloc
        return HTMLResponse(
            "<!doctype html><html lang=en><meta charset=utf-8>"
            "<title>FlowPilot sign-in</title><main>" + content + "</main></html>",
            status_code=status,
            headers={
                "Content-Security-Policy": "default-src 'none'; form-action "
                + form_action
                + "; base-uri 'none'; frame-ancestors 'none'",
                "Cache-Control": "no-store",
                # Keep callback query strings private while allowing Chromium to
                # supply the actual Origin on same-origin form submissions.
                "Referrer-Policy": "strict-origin",
            },
        )

    def _clear(self, response: Response):
        response.delete_cookie(
            PENDING_COOKIE,
            path=LOGIN_PATH,
            httponly=True,
            secure=self.browser.sessions.browser.secure,
            samesite="lax",
        )
        return response

    def _complete(self, request: Request, raw: str) -> Response:
        try:
            self._no_session(request)
            verifier = _pending_cookie(request)
            fields = _fields(raw, self.verifier.config.issuer)
            self.transactions.consume(fields["state"], verifier)
            if "error" in fields:
                return self._clear(
                    self._page("<h1>Sign-in cancelled</h1><p>Start again when ready.</p>", 400)
                )
            identity = self.verifier.verify(
                self.exchange(fields["code"], verifier), expected_client_id=self.config.client_id
            )
            if not {"flowpilot:read", "flowpilot:write"} <= identity.scopes:
                raise InvalidAccessToken
            credential = self.browser.sessions.issue(identity)
            response = self._page(
                '<h1>Signed in to FlowPilot</h1><p><a href="'
                + WORKSPACE_URL
                + '">Open workspace</a></p>'
            )
            response.set_cookie(
                COOKIE_NAME,
                credential,
                path=COOKIE_PATH,
                httponly=True,
                secure=self.browser.sessions.browser.secure,
                samesite="strict",
                max_age=max(0, identity.expires_at - int(time.time())),
            )
            return self._clear(response)
        except HTTPException as exc:
            return self._clear(
                self._page(
                    "<h1>Sign-in could not complete</h1><p>Sign out or start again.</p>",
                    exc.status_code,
                )
            )
        except (InvalidLoginTransaction, InvalidAccessToken, InvalidSession):
            return self._clear(
                self._page("<h1>Sign-in could not complete</h1><p>Start a new sign-in.</p>", 400)
            )
        except (IdentityUnavailable, LoginStorageUnavailable, SessionUnavailable):
            return self._clear(
                self._page("<h1>Sign-in unavailable</h1><p>Start again later.</p>", 503)
            )

    def routes(self) -> APIRouter:
        router = APIRouter()

        @router.get(LOGIN_PATH, response_class=HTMLResponse)
        def page(request: Request):
            self._origin(request)
            return self._page(
                '<h1>Sign in to FlowPilot</h1><form method=post action="/api/v2/login">'
                "<button type=submit>Sign in</button></form>",
                authorize=True,
            )

        @router.post(LOGIN_PATH)
        def begin(request: Request):
            self.browser.check_origin(request, required=True)
            self._no_session(request)
            if PENDING_COOKIE in request.cookies:
                raise HTTPException(409, "A login is already pending; retry after it expires")
            pending = self.transactions.begin()
            url = (
                self.config.authorization_url
                + "?"
                + urlencode(
                    {
                        "response_type": "code",
                        "client_id": self.config.client_id,
                        "redirect_uri": self.redirect,
                        "scope": SCOPES,
                        "state": pending.state,
                        "code_challenge": pending.challenge,
                        "code_challenge_method": "S256",
                    }
                )
            )
            response = RedirectResponse(url, status_code=303)
            response.set_cookie(
                PENDING_COOKIE,
                pending.verifier,
                path=LOGIN_PATH,
                max_age=300,
                httponly=True,
                secure=self.browser.sessions.browser.secure,
                samesite="lax",
            )
            return response

        @router.get(LOGIN_PATH + "/callback")
        def callback(request: Request):
            try:
                self._origin(request)
                _pending_cookie(request)
                raw = request.scope["query_string"]
                if len(raw) > 8192:
                    raise InvalidLoginTransaction
                fields = _fields(raw.decode("ascii"), self.verifier.config.issuer)
                hidden = "".join(
                    '<input type=hidden name="'
                    + escape(k, quote=True)
                    + '" value="'
                    + escape(v, quote=True)
                    + '">'
                    for k, v in fields.items()
                )
                return self._page(
                    '<h1>Complete sign-in</h1><form method=post action="/api/v2/login/complete">'
                    + hidden
                    + "<button type=submit>Continue sign-in</button></form>"
                )
            except (InvalidLoginTransaction, UnicodeError):
                return self._page("<h1>Invalid sign-in callback</h1>", 400)

        @router.post(LOGIN_PATH + "/complete")
        async def complete(request: Request):
            self.browser.check_origin(request, required=True)
            if request.headers.get("content-type") != "application/x-www-form-urlencoded":
                return self._clear(self._page("<h1>Invalid sign-in request</h1>", 400))
            raw = bytearray()
            async for chunk in request.stream():
                if len(raw) + len(chunk) > 8192:
                    return self._clear(self._page("<h1>Invalid sign-in request</h1>", 400))
                raw.extend(chunk)
            try:
                decoded = raw.decode("ascii")
            except UnicodeError:
                return self._clear(self._page("<h1>Invalid sign-in request</h1>", 400))
            return await run_in_threadpool(self._complete, request, decoded)

        return router
