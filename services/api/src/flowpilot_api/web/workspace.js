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
const showToday = document.querySelector("#show-today");
const showWork = document.querySelector("#show-work");
const showInbox = document.querySelector("#show-inbox");
const showNotes = document.querySelector("#show-notes");
const showAccess = document.querySelector("#show-access");
const inboxPanel = document.querySelector("#inbox-panel");
const notesPanel = document.querySelector("#notes-panel");
const accessPanel = document.querySelector("#access-panel");
const invitationsPanel = document.querySelector("#invitations-panel");
const workPanel = document.querySelector("#work-panel");
const workHeading = document.querySelector("#work-heading");
const todayReviews = document.querySelector("#today-reviews");
const todayEvents = document.querySelector("#today-events");
const eventsStatus = document.querySelector("#today-events-status");
const eventItems = document.querySelector("#today-event-items");
const retryEvents = document.querySelector("#retry-today-events");
const openEvents = document.querySelector("#open-events");
const reviewsStatus = document.querySelector("#today-reviews-status");
const reviewItems = document.querySelector("#today-review-items");
const retryReviews = document.querySelector("#retry-today-reviews");
const reviewInInbox = document.querySelector("#review-in-inbox");
const workViewLabel = document.querySelector("#work-view-label");
const workView = document.querySelector("#work-view");
const workStatus = document.querySelector("#work-status");
const items = document.querySelector("#work-items");
const more = document.querySelector("#more-work");
const retryWork = document.querySelector("#retry-work");
const newTask = document.querySelector("#new-task");
const taskEditor = document.querySelector("#task-editor");
const taskHeading = document.querySelector("#task-editor-heading");
const taskTitle = document.querySelector("#task-title");
const taskDescription = document.querySelector("#task-description");
const taskDueDate = document.querySelector("#task-due-date");
const saveTask = document.querySelector("#save-task");
const cancelTask = document.querySelector("#cancel-task");
const taskFeedback = document.querySelector("#task-feedback");
const loginEnabled = document.body.dataset.loginEnabled === "true";
const taskTransitions = JSON.parse(document.body.dataset.taskTransitions);

let session;
let sessionVersion = 0;
let workVersion = 0;
let reviewVersion = 0;
let eventVersion = 0;
let expiresTimer;
let nextCursor;
let ownId;
let editingTask;
let taskOpener;
let loadedTitle;
let loadedDescription;
let editorVersion = 0;
let taskUpdate;
let workspaceView = "work";
let inboxSaving = false;
let notesBusy = false;
let accessSaving = false;
let invitationSaving = false;
let workspaceSelectionBusy = false;

const inbox = createWorkspaceInbox({
  request,
  expired,
  lockWorkNavigation(locked) {
    inboxSaving = locked;
    syncWorkControls();
  },
  denyWrites: clearWorkspaceWriteHint,
  openWork() {
    workView.value = "all";
    switchWorkspaceView("work");
    showWork.focus();
  },
});

const notes = createWorkspaceNotes({
  request,
  expired,
  lockNavigation(locked) {
    notesBusy = locked;
    syncWorkControls();
  },
  denyWrites: clearWorkspaceWriteHint,
});

const events = createWorkspaceEvents({
  request,
  expired,
  context() {
    if (!canWriteWork() || workspaceSelectionBusy) return;
    return { path: "workspaces/" + encodeURIComponent(select.value), csrf: session.csrf_token };
  },
  reload(message) { void loadWork(false, "", message); },
  offerReload() { retryWork.hidden = false; },
  deny(status) {
    if (status === 403) clearWorkspaceWriteHint();
    clearWork();
    events.showFeedback("You no longer have permission to save this event.");
    retryWork.hidden = false;
  },
  syncControls: syncWorkControls,
});

const reminders = createWorkspaceReminders({ request, expired, localDate });

const sharing = createWorkspaceSharing({
  request,
  expired,
  context() {
    const option = select.selectedOptions[0];
    if (!canWriteWork() || workspaceSelectionBusy || workspaceView !== "work") return;
    return { path: "workspaces/" + encodeURIComponent(option.value), name: option.textContent };
  },
  syncControls: syncWorkControls,
  reload(message) { void loadWork(false, "", "", message); },
  offerReload() { retryWork.hidden = false; },
  deny(status) {
    if (status === 403) clearWorkspaceWriteHint();
    clearWork();
    sharing.showFeedback("You no longer have permission to share this item.");
    retryWork.hidden = false;
  },
});

const access = createWorkspaceAccess({
  request,
  expired,
  lockNavigation(locked) {
    accessSaving = locked;
    syncWorkControls();
  },
  deny: clearWorkspaceWriteHint,
  async refreshContext(message, member) {
    const option = select.selectedOptions[0];
    if (member?.active) {
      option.dataset.role = member.role;
      loadSelectedWorkspaceView();
      access.showFeedback(message);
      return;
    }
    if (member) option.remove();
    else clearWorkspaceWriteHint();
    const version = sessionVersion;
    const loading = loadWorkspaces();
    access.showFeedback(message);
    await loading;
    if (version === sessionVersion) access.showFeedback(message);
  },
});

const invitations = createWorkspaceInvitations({
  request,
  expired,
  lockNavigation(locked) {
    invitationSaving = locked;
    syncWorkControls();
  },
  registered(id) {
    ownId = id;
    invitations.show(id, session.can_write);
    loadSelectedWorkspaceView();
  },
  async refreshWorkspace(preferred, message) {
    const version = sessionVersion;
    const loading = loadWorkspaces(undefined, preferred);
    invitations.showFeedback(message);
    await loading;
    if (version === sessionVersion) invitations.showFeedback(message);
  },
});

function clearWorkspaceWriteHint() {
  const option = select.selectedOptions[0];
  if (option) delete option.dataset.role;
}

async function request(path, options, onProblem) {
  const headers = new Headers(options?.headers);
  if (session && !headers.has("X-CSRF-Token")) headers.set("X-CSRF-Token", session.csrf_token);
  const response = await fetch("/api/v2/" + path, {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
    headers,
  });
  if ((response.status === 409 || response.status === 422) && onProblem) {
    const error = await response.json().catch(() => null);
    onProblem(error?.detail);
  }
  if (!response.ok) throw response.status;
  if (response.status !== 204) return response.json();
}

function closeTaskEditor() {
  editorVersion += 1;
  editingTask = undefined;
  taskOpener = undefined;
  loadedTitle = loadedDescription = undefined;
  taskEditor.reset();
  taskEditor.hidden = true;
  saveTask.disabled = false;
  cancelTask.disabled = false;
  taskTitle.readOnly = taskDescription.readOnly = taskDueDate.readOnly = false;
  taskFeedback.textContent = "";
  syncWorkControls();
}

function clearWork() {
  workVersion += 1;
  nextCursor = undefined;
  items.replaceChildren();
  workStatus.textContent = "";
  more.hidden = retryWork.hidden = true;
  more.disabled = false;
  newTask.hidden = true;
  taskUpdate = undefined;
  events.clear();
  sharing.clear();
  closeTaskEditor();
}

function clearSession() {
  sessionVersion += 1;
  reminders.clear();
  session = undefined;
  ownId = undefined;
  workspaceSelectionBusy = false;
  clearTimeout(expiresTimer);
  inbox.clear();
  notes.clear();
  access.clear();
  invitations.clear();
  clearTodayLists();
  workspaceView = "work";
  syncWorkspaceNavigation();
  clearWork();
  select.replaceChildren();
  syncWorkControls();
  workView.value = "all";
  workView.disabled = true;
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

function canWriteWork() {
  const role = select.selectedOptions[0]?.dataset.role;
  return Boolean(session?.can_write && ownId && (role === "owner" || role === "member"));
}

function syncWorkspaceNavigation() {
  const today = workspaceView === "today";
  workPanel.hidden = !today && workspaceView !== "work";
  inboxPanel.hidden = workspaceView !== "inbox";
  notesPanel.hidden = workspaceView !== "notes";
  accessPanel.hidden = workspaceView !== "access";
  workHeading.textContent = today ? "Today" : "Work items";
  todayReviews.hidden = !today;
  todayEvents.hidden = !today;
  workViewLabel.hidden = workView.hidden = today;
  showToday.setAttribute("aria-pressed", String(today));
  showWork.setAttribute("aria-pressed", String(workspaceView === "work"));
  showInbox.setAttribute("aria-pressed", String(workspaceView === "inbox"));
  showNotes.setAttribute("aria-pressed", String(workspaceView === "notes"));
  showAccess.setAttribute("aria-pressed", String(workspaceView === "access"));
}

function loadSelectedWorkspaceView() {
  reminders.select(session ? select.value || undefined : undefined, session);
  inbox.clear();
  notes.clear();
  access.clear();
  clearTodayLists();
  if (workspaceView === "inbox") {
    clearWork();
    if (session && select.value) inbox.show(select.value, session.csrf_token, canWriteWork());
  } else if (workspaceView === "notes") {
    clearWork();
    if (session && select.value) notes.show(select.value, session.csrf_token, canWriteWork());
  } else if (workspaceView === "access") {
    clearWork();
    if (session && select.value) {
      access.show({
        id: ownId,
        role: select.selectedOptions[0]?.dataset.role,
        canWrite: session.can_write,
        path: "workspaces/" + encodeURIComponent(select.value),
      });
    }
  } else {
    void loadWork();
    if (workspaceView === "today") {
      void loadTodayReviews();
      void loadTodayEvents();
    }
  }
}

function switchWorkspaceView(view) {
  if (workspaceView === view) return;
  workspaceView = view;
  syncWorkspaceNavigation();
  loadSelectedWorkspaceView();
}

function syncWorkControls() {
  const eventLocked = events.locked();
  const sharingLocked = sharing.locked();
  const editorOpen = !taskEditor.hidden || eventLocked || sharingLocked;
  const workspaceLocked = workspaceSelectionBusy || notesBusy || eventLocked || sharingLocked
    || accessSaving || invitationSaving;
  select.disabled = workspaceLocked || !select.options.length;
  createButton.disabled = refreshWorkspaces.disabled = workspaceLocked;
  nameInput.disabled = notesBusy || eventLocked || sharingLocked || accessSaving || invitationSaving;
  notesPanel.inert = accessPanel.inert = workspaceSelectionBusy || invitationSaving;
  inboxPanel.inert = workPanel.inert = invitationSaving;
  invitationsPanel.inert = workspaceSelectionBusy || accessSaving || notesBusy || editorOpen
    || inboxSaving || taskUpdate === "pending";
  workView.disabled = editorOpen || taskUpdate === "pending" || !select.value;
  const navigationLocked = workView.disabled || inboxSaving || notesBusy || accessSaving || invitationSaving;
  showToday.disabled = showWork.disabled = showInbox.disabled = showNotes.disabled = navigationLocked;
  showAccess.disabled = navigationLocked;
  reviewInInbox.disabled = showInbox.disabled;
  openEvents.disabled = navigationLocked;
  newTask.disabled = Boolean(taskUpdate) || editorOpen;
  events.disableCreate(newTask.disabled || workspaceSelectionBusy);
  more.inert = retryWork.inert = eventLocked || sharingLocked;
  for (const button of items.querySelectorAll("button")) {
    button.disabled = newTask.disabled || Boolean(button.closest(".event-actions") && events.paused())
      || Boolean(button.closest(".sharing-actions") && sharing.paused());
  }
}

function openTaskEditor(task, opener = newTask) {
  if (!canWriteWork() || newTask.disabled || (!task && newTask.hidden)) return;
  closeTaskEditor();
  editingTask = task;
  taskOpener = opener;
  taskHeading.textContent = task ? "Edit task" : "New task";
  saveTask.textContent = task ? "Save changes" : "Create task";
  taskTitle.value = task?.data.title ?? "";
  taskDescription.value = task?.data.description ?? "";
  taskDueDate.value = task?.data.due_date ?? "";
  // Textareas normalize line endings. Keep the saved text when it was left alone.
  loadedTitle = taskTitle.value;
  loadedDescription = taskDescription.value;
  taskEditor.hidden = false;
  syncWorkControls();
  taskTitle.focus();
}

async function changeTaskStatus(item, target, row) {
  if (!canWriteWork() || taskUpdate || !taskEditor.hidden || !row.isConnected) return;
  if (target === "canceled" && !window.confirm("Cancel this task? It cannot be reopened.")) return;
  taskUpdate = "pending";
  syncWorkControls();
  taskFeedback.textContent = "Updating task…";
  const path = "workspaces/" + encodeURIComponent(select.value) + "/work/"
    + encodeURIComponent(item.id) + "/transitions";
  try {
    const updated = await request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token },
      body: JSON.stringify({ expected_version: item.version, target }),
    });
    if (!row.isConnected) return;
    const message = "Task status updated.";
    if (isDueView()) {
      void loadWork(false, message);
    } else {
      row.replaceWith(renderItem(updated));
      taskUpdate = undefined;
      syncWorkControls();
      taskFeedback.textContent = message;
    }
  } catch (status) {
    if (!row.isConnected || expired(status)) return;
    if (status === 403 || status === 404) {
      clearWork();
      taskFeedback.textContent = "You no longer have permission to update this task.";
    } else {
      taskUpdate = "refresh";
      syncWorkControls();
      taskFeedback.textContent = status === 409
        ? "This task changed. Refresh the work list to see its current status."
        : "Could not confirm the update. Refresh the work list before trying again.";
    }
    retryWork.hidden = false;
  }
}

function renderItem(item, today) {
  const row = document.createElement("li");
  const title = document.createElement("strong");
  const detail = document.createElement("span");
  title.textContent = item.data.title;
  const metadata = [item.data.kind, item.data.status];
  if (item.data.kind === "task" && item.data.due_date) {
    if (today) metadata.push(item.data.due_date < today ? "Overdue" : "Due today");
    metadata.push("Due " + item.data.due_date);
  }
  metadata.push(item.visibility === "private" ? "Private" : "Shared with workspace");
  detail.textContent = metadata.join(" · ");
  row.append(title, detail);
  if (item.data.kind === "event") renderEventTimes(row, item.data);
  if ((item.data.kind === "task" || item.data.kind === "event") && item.data.description) {
    const description = document.createElement("p");
    description.textContent = item.data.description;
    row.append(description);
  }
  if (item.data.kind === "event" && canWriteWork()) {
    events.renderActions(row, item, item.creator_id === ownId);
  }
  if (item.data.kind === "task" && canWriteWork()) {
    const actions = document.createElement("div");
    actions.className = "actions task-actions";
    if (item.creator_id === ownId) {
      const edit = document.createElement("button");
      edit.type = "button";
      edit.textContent = "Edit task";
      edit.addEventListener("click", () => openTaskEditor(item, edit));
      actions.append(edit);
    }
    const labels = {
      active: item.data.status === "blocked" ? "Resume task" : "Start task",
      blocked: "Block task",
      completed: "Complete task",
      canceled: "Cancel task",
    };
    for (const target of taskTransitions[item.data.status] ?? []) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = labels[target];
      button.addEventListener("click", () => changeTaskStatus(item, target, row));
      actions.append(button);
    }
    if (actions.childElementCount) row.append(actions);
  }
  if (workspaceView === "work" && canWriteWork() && item.creator_id === ownId
    && item.visibility === "private"
    && (item.data.kind === "task" || (item.data.kind === "event" && item.data.status === "scheduled"))) {
    const actions = document.createElement("div");
    actions.className = "actions task-actions sharing-actions";
    const share = document.createElement("button");
    share.type = "button";
    share.textContent = "Share with workspace";
    share.addEventListener("click", () => {
      if (row.isConnected) void sharing.open(item.id, share);
    });
    actions.append(share);
    row.append(actions);
  }
  return row;
}

function isDueView() {
  return workspaceView === "today" || workView.value === "due";
}

function localDate() {
  const now = new Date();
  const parts = [now.getFullYear(), now.getMonth() + 1, now.getDate()];
  return parts.map((value, index) => String(value).padStart(index === 0 ? 4 : 2, "0")).join("-");
}

async function loadWork(append = false, savedMessage = "", eventMessage = "", shareMessage = "") {
  if (!append) {
    clearWork();
    taskFeedback.textContent = savedMessage;
    events.showFeedback(eventMessage);
    sharing.showFeedback(shareMessage);
  }
  if (!session || !select.value) return;
  const today = workspaceView === "today" ? localDate() : undefined;
  const dueOnly = isDueView();
  const eventsOnly = !dueOnly && workView.value === "events";
  const visibility = !dueOnly && ["private", "workspace"].includes(workView.value) ? workView.value : undefined;
  const sharedOnly = visibility === "workspace";
  const version = ++workVersion;
  const active = sessionVersion;
  const path = "workspaces/" + encodeURIComponent(select.value) + (dueOnly ? "/work-due" : "/work-page");
  const query = new URLSearchParams({ limit: today ? "21" : "20" });
  if (eventsOnly) query.set("kind", "event");
  if (visibility) query.set("visibility", visibility);
  if (append && nextCursor) query.set("after", nextCursor);
  workStatus.textContent = "Loading work items…";
  more.disabled = true;
  try {
    const page = await request(path + "?" + query);
    if (version !== workVersion || !session) return;
    // The due endpoint sorts by date, so later rows cannot qualify after a future date.
    const visible = today ? page.items.filter(item => item.data.due_date <= today) : page.items;
    items.append(...visible.slice(0, 20).map(item => renderItem(item, today)));
    newTask.hidden = !canWriteWork() || eventsOnly || sharedOnly;
    events.showCreate(!dueOnly && !sharedOnly && canWriteWork());
    syncWorkControls();
    nextCursor = page.next_after;
    more.hidden = !nextCursor;
    more.disabled = false;
    if (today) {
      workStatus.textContent = visible.length > 20
        ? "Showing the 20 earliest tasks due by today. Open Work items to see more."
        : visible.length ? "" : "No tasks due today or overdue.";
    } else if (dueOnly) {
      workStatus.textContent = page.has_more
        ? "Showing the 20 earliest deadlines. Switch to All work for the full list."
        : items.childElementCount ? "" : "No unfinished tasks with due dates.";
    } else {
      workStatus.textContent = items.childElementCount ? ""
        : eventsOnly ? "No events yet." : sharedOnly ? "No shared work yet." : "No work items yet.";
    }
  } catch (status) {
    if (active !== sessionVersion || version !== workVersion || expired(status)) return;
    if (clearDeniedToday(status)) {
      taskFeedback.textContent = savedMessage;
      return;
    }
    if (append && status !== 403 && status !== 404) {
      workStatus.textContent = "Could not load more work items. Try again.";
      more.disabled = false;
      return;
    }
    clearWork();
    taskFeedback.textContent = savedMessage;
    events.showFeedback(eventMessage);
    sharing.showFeedback(shareMessage);
    workStatus.textContent = status === 403 || status === 404
      ? "This work list is unavailable. Refresh your workspaces or retry."
      : "Could not load work items.";
    retryWork.hidden = false;
  }
}

function clearTodayReviews() {
  reviewVersion += 1;
  reviewItems.replaceChildren();
  reviewsStatus.textContent = "";
  retryReviews.hidden = true;
}

function clearTodayEvents() {
  eventVersion += 1;
  eventItems.replaceChildren();
  eventsStatus.textContent = "";
  retryEvents.hidden = true;
}

function clearTodayLists() {
  clearTodayReviews();
  clearTodayEvents();
}

function clearDeniedToday(status) {
  if (status !== 403 || workspaceView !== "today") return false;
  clearWork();
  clearTodayLists();
  workStatus.textContent = "Today is unavailable. Refresh your workspaces to try again.";
  return true;
}

async function loadTodayReviews() {
  if (workspaceView !== "today" || !session || !select.value) return;
  clearTodayReviews();
  const version = reviewVersion;
  reviewsStatus.textContent = "Loading pending reviews…";
  try {
    const path = "workspaces/" + encodeURIComponent(select.value) + "/proposals?limit=5";
    const proposals = await request(path);
    if (version !== reviewVersion) return;
    for (const proposal of proposals) {
      const item = document.createElement("li");
      item.textContent = proposal.title;
      reviewItems.append(item);
    }
    reviewsStatus.textContent = proposals.length ? "" : "No pending reviews.";
  } catch (status) {
    if (version !== reviewVersion || expired(status) || clearDeniedToday(status)) return;
    reviewsStatus.textContent = status === 404
      ? "Pending reviews are unavailable."
      : "Could not load pending reviews.";
    retryReviews.hidden = false;
  }
}

function renderTodayEvent({ data: event }) {
  const row = document.createElement("li");
  const title = document.createElement("strong");
  title.textContent = event.title;
  row.append(title);
  renderEventTimes(row, event);
  return row;
}

async function loadTodayEvents() {
  if (workspaceView !== "today" || !session || !select.value) return;
  clearTodayEvents();
  const version = eventVersion;
  eventsStatus.textContent = "Loading upcoming events…";
  try {
    const path = "workspaces/" + encodeURIComponent(select.value) + "/work-events?limit=5";
    const page = await request(path);
    if (version !== eventVersion) return;
    eventItems.append(...page.items.map(renderTodayEvent));
    eventsStatus.textContent = page.has_more
      ? "Showing the five earliest events."
      : page.items.length ? "" : "No events in the next seven days.";
  } catch (status) {
    if (version !== eventVersion || expired(status) || clearDeniedToday(status)) return;
    eventsStatus.textContent = status === 404
      ? "Upcoming events are unavailable."
      : "Could not load upcoming events.";
    retryEvents.hidden = false;
  }
}

async function loadWorkspaces(created, preferredId) {
  if (!session) return;
  const version = sessionVersion;
  const preferred = created?.id ?? preferredId ?? select.value;
  workspaceSelectionBusy = true;
  reminders.select(undefined, session);
  inbox.clear();
  notes.clear();
  access.clear();
  invitations.clear();
  clearTodayLists();
  clearWork();
  select.replaceChildren();
  syncWorkControls();
  workspaceStatus.textContent = "Loading workspaces…";
  try {
    const workspaces = await request("workspaces?limit=100");
    if (version !== sessionVersion) return;
    let unregistered = false;
    if (!ownId) {
      try {
        const profile = await request("me");
        if (version !== sessionVersion) return;
        ownId = profile.id;
      } catch (status) {
        if (version !== sessionVersion || expired(status)) return;
        unregistered = status === 404;
      }
    }
    const listed = workspaces.some(({ id }) => id === preferred);
    let extra = created;
    if (!listed && !extra && preferred) {
      try {
        extra = await request("workspaces/" + encodeURIComponent(preferred));
        if (version !== sessionVersion) return;
      } catch (status) {
        if (version !== sessionVersion || expired(status)) return;
      }
    }
    const options = extra && !listed ? [...workspaces, extra] : workspaces;
    select.append(...options.map(({ id, name, role }) => {
      const option = new Option(name, id);
      option.dataset.role = role;
      return option;
    }));
    if (listed || extra) select.value = preferred;
    if (workspaces.length === 100) {
      workspaceStatus.textContent = "Showing the first 100 workspaces.";
    } else {
      workspaceStatus.textContent = options.length ? "" : "Create your first workspace to get started.";
    }
    if (options.length && !ownId) {
      workspaceStatus.textContent += " Could not load your profile. Refresh workspaces to edit tasks.";
    }
    invitations.show(ownId, session.can_write, unregistered);
    loadSelectedWorkspaceView();
  } catch (status) {
    if (version !== sessionVersion || expired(status)) return;
    workspaceStatus.textContent = "Could not load workspaces.";
  } finally {
    if (version === sessionVersion) {
      workspaceSelectionBusy = false;
      syncWorkControls();
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
  workspaceSelectionBusy = true;
  syncWorkControls();
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
    workspaceSelectionBusy = false;
    syncWorkControls();
  }
});

taskEditor.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!session || taskEditor.hidden || saveTask.disabled || !canWriteWork()) return;
  const task = editingTask;
  const title = task && taskTitle.value === loadedTitle ? task.data.title : taskTitle.value.trim();
  if (!title) {
    taskFeedback.textContent = "Enter a task title.";
    return;
  }
  const version = editorVersion;
  const path = "workspaces/" + encodeURIComponent(select.value) + "/work";
  const details = {
    title,
    description: task && taskDescription.value === loadedDescription
      ? task.data.description
      : taskDescription.value.trim() || null,
    due_date: taskDueDate.value || null,
  };
  saveTask.disabled = cancelTask.disabled = true;
  taskTitle.readOnly = taskDescription.readOnly = taskDueDate.readOnly = true;
  taskFeedback.textContent = "Saving task…";
  try {
    await request(task ? path + "/" + encodeURIComponent(task.id) + "/task-details" : path, {
      method: task ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token },
      body: JSON.stringify(task
        ? { expected_version: task.version, details }
        : { item: { kind: "task", ...details } }),
    });
    if (version !== editorVersion) return;
    void loadWork(false, task ? "Task updated." : "Task created.");
  } catch (status) {
    if (version !== editorVersion || expired(status)) return;
    if (status === 409 && task) {
      taskFeedback.textContent = "This task changed. Close the editor, refresh the work list, and reopen the task.";
      retryWork.hidden = false;
    } else if (status === 403 || status === 404) {
      clearWork();
      taskFeedback.textContent = "You no longer have permission to save this task.";
      retryWork.hidden = false;
    } else {
      taskFeedback.textContent = status === 422
        ? "Check the title, description, and due date."
        : "Could not confirm the save. Refresh the work list before trying again.";
      if (status !== 422) retryWork.hidden = false;
      saveTask.disabled = status !== 422;
    }
  } finally {
    if (version === editorVersion) {
      cancelTask.disabled = false;
      taskTitle.readOnly = taskDescription.readOnly = taskDueDate.readOnly = false;
    }
  }
});

newTask.addEventListener("click", () => openTaskEditor());
cancelTask.addEventListener("click", () => {
  const opener = taskOpener;
  closeTaskEditor();
  if (opener?.isConnected) opener.focus();
});
select.addEventListener("change", loadSelectedWorkspaceView);
showToday.addEventListener("click", () => switchWorkspaceView("today"));
showWork.addEventListener("click", () => switchWorkspaceView("work"));
showInbox.addEventListener("click", () => switchWorkspaceView("inbox"));
showNotes.addEventListener("click", () => switchWorkspaceView("notes"));
showAccess.addEventListener("click", () => switchWorkspaceView("access"));
reviewInInbox.addEventListener("click", () => {
  switchWorkspaceView("inbox");
  showInbox.focus();
});
retryReviews.addEventListener("click", loadTodayReviews);
retryEvents.addEventListener("click", loadTodayEvents);
openEvents.addEventListener("click", () => {
  workView.value = "events";
  switchWorkspaceView("work");
  showWork.focus();
});
workView.addEventListener("change", () => loadWork());
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
