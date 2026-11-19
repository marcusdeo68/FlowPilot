"""Serve the same-origin workspace shell and its fixed assets."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from flowpilot_api.session_routes import BrowserAuth

WORKSPACE_URL = "/api/v2/workspace"
ASSETS = Path(__file__).with_name("web")


def workspace_ui(browser: BrowserAuth, *, login_enabled: bool) -> APIRouter:
    router = APIRouter()
    shell = (ASSETS / "workspace.html").read_text(encoding="utf-8")
    if login_enabled:
        shell = shell.replace("<body>", '<body data-login-enabled="true">', 1)

    @router.get(WORKSPACE_URL, include_in_schema=False)
    def workspace(request: Request):
        browser.check_origin(request, required=False)
        return HTMLResponse(
            shell,
            headers={
                "Content-Security-Policy": (
                    "default-src 'none'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
                )
            },
        )

    @router.get(WORKSPACE_URL + ".js", include_in_schema=False)
    def script():
        return FileResponse(ASSETS / "workspace.js", media_type="text/javascript")

    @router.get(WORKSPACE_URL + ".css", include_in_schema=False)
    def styles():
        return FileResponse(ASSETS / "workspace.css", media_type="text/css")

    return router
