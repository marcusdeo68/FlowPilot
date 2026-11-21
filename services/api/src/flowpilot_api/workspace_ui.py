"""Serve the same-origin workspace shell and its fixed assets."""

import json
from html import escape
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from flowpilot_api.session_routes import BrowserAuth
from flowpilot_api.work import TASK_TRANSITIONS

WORKSPACE_URL = "/api/v2/workspace"
ASSETS = Path(__file__).with_name("web")


def workspace_ui(browser: BrowserAuth, *, login_enabled: bool) -> APIRouter:
    router = APIRouter()
    shell = (ASSETS / "workspace.html").read_text(encoding="utf-8")
    transitions = escape(json.dumps(TASK_TRANSITIONS), quote=True)
    shell = shell.replace(
        "<body>",
        f'<body data-login-enabled="{str(login_enabled).lower()}" '
        f'data-task-transitions="{transitions}">',
        1,
    )

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

    @router.get(WORKSPACE_URL + "-inbox.js", include_in_schema=False)
    def inbox_script():
        return FileResponse(ASSETS / "workspace-inbox.js", media_type="text/javascript")

    @router.get(WORKSPACE_URL + "-notes.js", include_in_schema=False)
    def notes_script():
        return FileResponse(ASSETS / "workspace-notes.js", media_type="text/javascript")

    @router.get(WORKSPACE_URL + "-events.js", include_in_schema=False)
    def events_script():
        return FileResponse(ASSETS / "workspace-events.js", media_type="text/javascript")

    @router.get(WORKSPACE_URL + "-reminders.js", include_in_schema=False)
    def reminders_script():
        return FileResponse(ASSETS / "workspace-reminders.js", media_type="text/javascript")

    @router.get(WORKSPACE_URL + "-access.js", include_in_schema=False)
    def access_script():
        return FileResponse(ASSETS / "workspace-access.js", media_type="text/javascript")

    @router.get(WORKSPACE_URL + "-invitations.js", include_in_schema=False)
    def invitations_script():
        return FileResponse(ASSETS / "workspace-invitations.js", media_type="text/javascript")

    @router.get(WORKSPACE_URL + ".css", include_in_schema=False)
    def styles():
        return FileResponse(ASSETS / "workspace.css", media_type="text/css")

    return router
