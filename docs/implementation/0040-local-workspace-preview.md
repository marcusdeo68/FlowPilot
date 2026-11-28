# Implementation 0040 — Local workspace preview

Open the signed-in FlowPilot workspace in a desktop browser with sample
data. On the FlowPilot workstation, start Docker Desktop, open PowerShell
in the project folder, then run:

```powershell
docker compose -f compose.test.yaml up -d --wait
if (Test-Path .tools\playwright) {
    $env:PLAYWRIGHT_BROWSERS_PATH = (Resolve-Path .tools\playwright).Path
}
.venv\Scripts\python.exe -m playwright install chromium --no-shell
$env:FLOWPILOT_INTERACTIVE_PREVIEW = '1'
New-Item -ItemType Directory -Force -Path .tools | Out-Null
.venv\Scripts\python.exe -m pytest -s --basetemp .tools\workspace-preview-temp tests/workspace_preview.py
```

Install desktop Chromium on first use. On a fresh machine, first install the
locked development and browser dependencies from the
[test environment guide](0013-local-postgres-tests.md). Use the default
Playwright browser path if you did not install browsers under `.tools/playwright`.
If PowerShell cannot find `docker` on this workstation, start the test
database with the Docker Desktop executable:

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" compose -f compose.test.yaml up -d --wait
```

The browser opens on **Today** with **Confirm workshop agenda** due today
and **Workshop planning session** starting in about ten minutes. A pending
room request opens a [three-step review walkthrough](0049-workspace-demo.md).
Turn on **In-app reminders**, find the High task in **Work items**, and
open **Notes** to edit the sample sticky note. Press **Enter** in
PowerShell to close the browser and discard the preview records. The
synthetic sign-in session lasts up to five minutes. Rerun for a fresh session.

The explicit pytest entry point starts the same local workspace and synthetic
sign-in servers as the Chromium suite. It signs in, creates a workspace,
and submits sample data over the authenticated API with its CSRF token.
The PostgreSQL fixture applies migrations in a unique schema on the dedicated
loopback test database and drops that schema at teardown. The preview cannot
use an environment-supplied database URL. Normal test discovery and the
deployed application do not include the preview entry point.

For a noninteractive check, set `FLOWPILOT_INTERACTIVE_PREVIEW` to `0` and run
the same test with the Chromium headless shell installed. The test asserts
that Today renders the sample task and event, then reviews the room request
and verifies the resulting private task. Live sign-in and external
accounts remain outside the preview. The next hosted milestone is synthetic
staging verification through Railway's public ingress.
