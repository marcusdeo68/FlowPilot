"""Same-origin cookie authentication and session lifecycle for the workspace API."""

import hmac
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from flowpilot_api.browser_sessions import (
    COOKIE_NAME,
    COOKIE_PATH,
    BrowserSessions,
    InvalidSession,
    csrf_token,
)
from flowpilot_api.identity import AccessIdentity


def session_cookie(request: Request) -> str | None:
    # Reject duplicate credentials rather than depend on cookie/header parsing order.
    count = sum(
        "=" in part and part.split("=", 1)[0].strip() == COOKIE_NAME
        for header in request.headers.getlist("cookie")
        for part in header.split(";")
    )
    if count > 1 or (
        (count or COOKIE_NAME in request.cookies) and "authorization" in request.headers
    ):
        raise HTTPException(401, "Ambiguous credentials")
    return request.cookies.get(COOKIE_NAME)


class BrowserAuth:
    def __init__(self, sessions: BrowserSessions):
        self.sessions = sessions

    def check_origin(self, request: Request, *, required: bool) -> None:
        origin = self.sessions.browser.origin
        origins = request.headers.getlist("origin")
        fetch_sites = request.headers.getlist("sec-fetch-site")
        if (
            f"{request.url.scheme}://{request.url.netloc}" != origin
            or (required and origins != [origin])
            or (origins and origins != [origin])
            or (fetch_sites and fetch_sites not in (["same-origin"], ["none"]))
        ):
            raise HTTPException(403, "Same-origin browser request required")

    def check_csrf(self, request: Request, credential: str) -> None:
        tokens = request.headers.getlist("x-csrf-token")
        if len(tokens) != 1 or not hmac.compare_digest(
            tokens[0].encode("utf-8"), csrf_token(credential).encode("ascii")
        ):
            raise HTTPException(403, "Valid CSRF token required")

    def authenticate(self, request: Request, credential: str) -> AccessIdentity:
        unsafe = request.method not in ("GET", "HEAD", "OPTIONS")
        self.check_origin(request, required=unsafe)
        user = self.sessions.resolve(credential)
        if unsafe:
            self.check_csrf(request, credential)
        return user

    def routes(self, bearer_identity) -> APIRouter:
        router = APIRouter()

        @router.post("/api/v2/session", status_code=201)
        def create(
            request: Request,
            response: Response,
            user: Annotated[AccessIdentity, Depends(bearer_identity)],
        ):
            self.check_origin(request, required=True)
            if "flowpilot:read" not in user.scopes:
                raise HTTPException(403, "Missing API read scope")
            credential = self.sessions.issue(user)
            response.set_cookie(
                COOKIE_NAME,
                credential,
                max_age=max(0, user.expires_at - int(time.time())),
                httponly=True,
                secure=self.sessions.browser.secure,
                samesite="strict",
                path=COOKIE_PATH,
            )
            return {"expires_at": user.expires_at, "csrf_token": csrf_token(credential)}

        @router.get("/api/v2/session")
        def current(request: Request):
            credential = session_cookie(request)
            if credential is None:
                raise InvalidSession
            user = self.authenticate(request, credential)
            return {"expires_at": user.expires_at, "csrf_token": csrf_token(credential)}

        @router.delete("/api/v2/session", status_code=204)
        def logout(request: Request):
            credential = session_cookie(request)
            if "authorization" in request.headers:
                raise HTTPException(401, "Cookie session required")
            self.check_origin(request, required=True)
            if credential is not None:
                try:
                    self.sessions.resolve(credential)
                except InvalidSession:
                    # Stale/malformed cookies cannot authenticate. Clear them so exchange
                    # is not permanently blocked; never revoke active state without CSRF.
                    pass
                else:
                    self.check_csrf(request, credential)
                    self.sessions.revoke(credential)
            response = Response(status_code=204)
            response.delete_cookie(
                COOKIE_NAME,
                path=COOKIE_PATH,
                httponly=True,
                secure=self.sessions.browser.secure,
                samesite="strict",
            )
            return response

        return router
