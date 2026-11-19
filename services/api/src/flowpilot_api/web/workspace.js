"use strict";

const sessionStatus = document.querySelector("#session-status");
const signIn = document.querySelector("#sign-in");
const signOut = document.querySelector("#sign-out");
const resetSession = document.querySelector("#reset-session");
const retrySession = document.querySelector("#retry-session");
const workspace = document.querySelector("#workspace");
const select = document.querySelector("#workspace-select");
const workspaceStatus = document.querySelector("#workspace-status");
const refreshWorkspaces = document.querySelector("#refresh-workspaces");
const form = document.querySelector("#create-workspace");
const nameInput = document.querySelector("#workspace-name");
const createButton = form.querySelector("button");
const createStatus = document.querySelector("#create-status");
const workStatus = document.querySelector("#work-status");
const items = document.querySelector("#work-items");
const more = document.querySelector("#more-work");
const retryWork = document.querySelector("#retry-work");
const loginEnabled = document.body.dataset.loginEnabled === "true";

let session;
let sessionVersion = 0;
let workVersion = 0;
let expiresTimer;
let nextCursor;

async function request(path, options) {
  const response = await fetch("/api/v2/" + path, {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
  });
  if (!response.ok) throw response.status;
  if (response.status !== 204) return response.json();
}

function clearWork() {
  workVersion += 1;
  nextCursor = undefined;
  items.replaceChildren();
  workStatus.textContent = "";
  more.hidden = retryWork.hidden = true;
  more.disabled = false;
}

function clearSession() {
  sessionVersion += 1;
  session = undefined;
  clearTimeout(expiresTimer);
  clearWork();
  select.replaceChildren();
  select.disabled = true;
  workspaceStatus.textContent = createStatus.textContent = "";
  form.reset();
  workspace.hidden = signOut.hidden = signIn.hidden = true;
  retrySession.hidden = resetSession.hidden = true;
}

function signedOut(message) {
  clearSession();
  sessionStatus.textContent = message;
  signIn.hidden = !loginEnabled;
  resetSession.hidden = false;
}

function expired(status) {
  if (status !== 401) return false;
  signedOut("Your session is unavailable. Sign in to open a workspace.");
  return true;
}

function renderItem(item) {
  const row = document.createElement("li");
  const title = document.createElement("strong");
  const detail = document.createElement("span");
  title.textContent = item.data.title;
  detail.textContent = [item.data.kind, item.data.status].join(" · ");
  row.append(title, detail);
  return row;
}

async function loadWork(append = false) {
  if (!append) clearWork();
  if (!session || !select.value) return;
  const version = ++workVersion;
  const active = sessionVersion;
  const path = "workspaces/" + encodeURIComponent(select.value) + "/work-page";
  const query = new URLSearchParams({ limit: "20" });
  if (append && nextCursor) query.set("after", nextCursor);
  workStatus.textContent = "Loading work items…";
  more.disabled = true;
  try {
    const page = await request(path + "?" + query);
    if (version !== workVersion || !session) return;
    items.append(...page.items.map(renderItem));
    nextCursor = page.next_after;
    more.hidden = !nextCursor;
    more.disabled = false;
    workStatus.textContent = items.childElementCount ? "" : "No work items yet.";
  } catch (status) {
    if (active !== sessionVersion || version !== workVersion || expired(status)) return;
    clearWork();
    workStatus.textContent = status === 403 || status === 404
      ? "This work list is unavailable. Refresh your workspaces or retry."
      : "Could not load work items.";
    retryWork.hidden = false;
  }
}

async function loadWorkspaces(created) {
  if (!session) return;
  const version = sessionVersion;
  const preferred = created?.id ?? select.value;
  clearWork();
  select.replaceChildren();
  select.disabled = createButton.disabled = refreshWorkspaces.disabled = true;
  workspaceStatus.textContent = "Loading workspaces…";
  try {
    const workspaces = await request("workspaces?limit=100");
    if (version !== sessionVersion) return;
    const listed = workspaces.some(({ id }) => id === preferred);
    select.append(...workspaces.map(({ id, name }) => new Option(name, id)));
    if (created && !listed) select.append(new Option(created.name, created.id));
    if (listed || created) select.value = preferred;
    select.disabled = workspaces.length === 0;
    if (workspaces.length === 100) {
      workspaceStatus.textContent = "Showing the first 100 workspaces.";
    } else {
      workspaceStatus.textContent = workspaces.length ? "" : "Create your first workspace to get started.";
    }
    void loadWork();
  } catch (status) {
    if (version !== sessionVersion || expired(status)) return;
    workspaceStatus.textContent = "Could not load workspaces.";
  } finally {
    if (version === sessionVersion) {
      createButton.disabled = refreshWorkspaces.disabled = false;
      refreshWorkspaces.hidden = false;
    }
  }
}

async function start() {
  clearSession();
  const version = sessionVersion;
  sessionStatus.textContent = "Checking your session…";
  try {
    const current = await request("session");
    if (version !== sessionVersion) return;
    const remaining = current.expires_at * 1000 - Date.now();
    if (remaining <= 0) {
      signedOut("Your session expired.");
      return;
    }
    session = current;
    expiresTimer = setTimeout(() => signedOut("Your session expired."), remaining);
    sessionStatus.textContent = "";
    workspace.hidden = signOut.hidden = false;
    await loadWorkspaces();
  } catch (status) {
    if (version !== sessionVersion || expired(status)) return;
    sessionStatus.textContent = "Could not check your session.";
    retrySession.hidden = false;
  }
}

async function endSession() {
  const token = session?.csrf_token;
  clearSession();
  const version = sessionVersion;
  sessionStatus.textContent = token ? "Signing out…" : "Clearing your session…";
  try {
    await request("session", {
      method: "DELETE",
      headers: token ? { "X-CSRF-Token": token } : {},
    });
    if (version !== sessionVersion) return;
    signedOut("You are signed out.");
    resetSession.hidden = true;
  } catch {
    if (version !== sessionVersion) return;
    sessionStatus.textContent = "Could not end your session. Retry to check its status.";
    retrySession.hidden = false;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!session || createButton.disabled) return;
  const name = nameInput.value.trim();
  if (!name) {
    createStatus.textContent = "Enter a workspace name.";
    return;
  }
  const version = sessionVersion;
  createButton.disabled = refreshWorkspaces.disabled = true;
  createStatus.textContent = "Creating workspace…";
  try {
    const created = await request("workspaces", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token },
      body: JSON.stringify({ name }),
    });
    if (version !== sessionVersion) return;
    form.reset();
    createStatus.textContent = "Workspace created.";
    await loadWorkspaces(created);
  } catch (status) {
    if (version !== sessionVersion || expired(status)) return;
    createStatus.textContent = status === 403
      ? "You do not have permission to create a workspace."
      : "Could not confirm creation. Refresh workspaces before trying again.";
    createButton.disabled = refreshWorkspaces.disabled = false;
  }
});

select.addEventListener("change", () => loadWork());
more.addEventListener("click", () => loadWork(true));
retryWork.addEventListener("click", () => loadWork());
refreshWorkspaces.addEventListener("click", () => loadWorkspaces());
retrySession.addEventListener("click", start);
signOut.addEventListener("click", endSession);
resetSession.addEventListener("click", endSession);
window.addEventListener("pagehide", clearSession);
window.addEventListener("pageshow", (event) => {
  if (event.persisted) void start();
});
void start();
