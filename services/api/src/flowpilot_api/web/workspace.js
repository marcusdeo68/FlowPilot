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
const openBlockedTasks = document.querySelector("#open-blocked-tasks");
const openSchedule = document.querySelector("#open-schedule");
const scheduleDeadlines = document.querySelector("#schedule-deadlines");
const scheduleDeadlinesStatus = document.querySelector("#schedule-deadlines-status");
const scheduleDeadlineItems = document.querySelector("#schedule-deadline-items");
const retryScheduleDeadlines = document.querySelector("#retry-schedule-deadlines");
const moreScheduleDeadlines = document.querySelector("#more-schedule-deadlines");
const deadlineFilter = document.querySelector("#schedule-deadline-filter");
const deadlineFromDate = document.querySelector("#deadline-from-date");
const openDueTasks = document.querySelector("#open-due-tasks");
const scheduleEventsHeading = document.querySelector("#schedule-events-heading");
const reviewsStatus = document.querySelector("#today-reviews-status");
const reviewItems = document.querySelector("#today-review-items");
const retryReviews = document.querySelector("#retry-today-reviews");
const reviewInInbox = document.querySelector("#review-in-inbox");
const workViewLabel = document.querySelector("#work-view-label");
const workView = document.querySelector("#work-view");
const taskStatusFilter = document.querySelector("#task-status-filter");
const workTaskStatus = document.querySelector("#work-task-status");
const workPriority = document.querySelector("#work-priority");
const projectFilter = document.querySelector("#project-filter");
const workProject = document.querySelector("#work-project");
const createProject = document.querySelector("#create-project");
const projectName = document.querySelector("#project-name");
const saveProject = document.querySelector("#save-project");
const projectFeedback = document.querySelector("#project-feedback");
const workSearch = document.querySelector("#work-search");
const workSearchTitle = document.querySelector("#work-search-title");
const submitWorkSearch = document.querySelector("#submit-work-search");
const clearWorkSearch = document.querySelector("#clear-work-search");
const dueDateFilter = document.querySelector("#due-date-filter");
const dueFromDate = document.querySelector("#due-from-date");
const applyDueDate = document.querySelector("#apply-due-date");
const clearDueDate = document.querySelector("#clear-due-date");
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
const taskProject = document.querySelector("#task-project");
const taskPriority = document.querySelector("#task-priority");
const saveTask = document.querySelector("#save-task");
const cancelTask = document.querySelector("#cancel-task");
const taskFeedback = document.querySelector("#task-feedback");
const loginEnabled = document.body.dataset.loginEnabled === "true";
const taskTransitions = JSON.parse(document.body.dataset.taskTransitions);
const deadlineDateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeZone: "UTC" });

let session;
let sessionVersion = 0;
let workVersion = 0;
let reviewVersion = 0;
let eventVersion = 0;
let scheduleDeadlineVersion = 0;
let scheduleDeadlineDate = "";
let nextDeadlineCursor;
let expiresTimer;
let nextCursor;
let loadingDueMore = false;
let workQuery = "";
let dueFilterDate = "";
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
let projects = [];
let projectsWorkspace = "";
let projectVersion = 0;
let projectSaving = false;

const inbox = createWorkspaceInbox({
  request,
  expired,
  lockWorkNavigation(locked) {
    inboxSaving = locked;
    syncWorkControls();
  },
  denyWrites: clearWorkspaceWriteHint,
  openWork() {
    openAllWork("");
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
    clearDeniedWork(status);
    events.showFeedback("You no longer have permission to save this event.");
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
    clearDeniedWork(status);
    sharing.showFeedback("You no longer have permission to share this item.");
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
  loadingDueMore = false;
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
  clearScheduleDeadlines();
  workspaceView = "work";
  resetWorkFilters();
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
  openBlockedTasks.hidden = !today;
  todayEvents.hidden = !today;
  workViewLabel.hidden = workView.hidden = today;
  showToday.setAttribute("aria-pressed", String(today));
  showWork.setAttribute("aria-pressed", String(workspaceView === "work"));
  showInbox.setAttribute("aria-pressed", String(workspaceView === "inbox"));
  showNotes.setAttribute("aria-pressed", String(workspaceView === "notes"));
  showAccess.setAttribute("aria-pressed", String(workspaceView === "access"));
}

function loadSelectedWorkspaceView(review) {
  reminders.select(session ? select.value || undefined : undefined, session);
  inbox.clear();
  notes.clear();
  access.clear();
  clearTodayLists();
  clearScheduleDeadlines();
  if (workspaceView === "inbox") {
    clearWork();
    if (session && select.value) inbox.show(select.value, session.csrf_token, canWriteWork(), review);
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
    loadWorkView();
    if (workspaceView === "today") {
      void loadTodayReviews();
      void loadTodayEvents();
    }
  }
}

function switchWorkspaceView(view, review) {
  if (workspaceView === view) return;
  workspaceView = view;
  syncWorkspaceNavigation();
  loadSelectedWorkspaceView(review);
}

function syncWorkControls() {
  const eventLocked = events.locked();
  const sharingLocked = sharing.locked();
  const editorOpen = !taskEditor.hidden || eventLocked || sharingLocked;
  const workspaceLocked = workspaceSelectionBusy || projectSaving || notesBusy || eventLocked || sharingLocked
    || accessSaving || invitationSaving;
  select.disabled = workspaceLocked || !select.options.length;
  createButton.disabled = refreshWorkspaces.disabled = workspaceLocked;
  nameInput.disabled = notesBusy || eventLocked || sharingLocked || accessSaving || invitationSaving;
  notesPanel.inert = accessPanel.inert = workspaceSelectionBusy || invitationSaving;
  inboxPanel.inert = workPanel.inert = invitationSaving;
  invitationsPanel.inert = workspaceSelectionBusy || accessSaving || notesBusy || editorOpen
    || inboxSaving || taskUpdate === "pending";
  workView.disabled = editorOpen || projectSaving || taskUpdate === "pending" || !select.value;
  workSearch.hidden = workspaceView !== "work" || isDueView() || isScheduleView();
  scheduleEventsHeading.hidden = !isScheduleView();
  workSearchTitle.disabled = submitWorkSearch.disabled = clearWorkSearch.disabled =
    workView.disabled || workspaceSelectionBusy;
  dueDateFilter.hidden = workspaceView !== "work" || workView.value !== "due";
  dueFromDate.disabled = applyDueDate.disabled = clearDueDate.disabled =
    workView.disabled || workspaceSelectionBusy;
  taskStatusFilter.hidden = !supportsTaskStatus();
  workTaskStatus.disabled = workPriority.disabled = submitWorkSearch.disabled;
  projectFilter.hidden = !supportsTaskStatus();
  createProject.hidden = !canWriteWork();
  workProject.disabled = saveProject.disabled = projectName.disabled =
    submitWorkSearch.disabled || !projectsWorkspace;
  taskProject.disabled = taskEditor.hidden || saveTask.disabled || !projectsWorkspace;
  taskPriority.disabled = taskEditor.hidden || saveTask.disabled;
  const navigationLocked = workView.disabled || inboxSaving || notesBusy || accessSaving || invitationSaving;
  showToday.disabled = showWork.disabled = showInbox.disabled = showNotes.disabled = navigationLocked;
  showAccess.disabled = navigationLocked;
  reviewInInbox.disabled = showInbox.disabled;
  for (const button of reviewItems.querySelectorAll("button")) button.disabled = navigationLocked;
  openEvents.disabled = openSchedule.disabled = navigationLocked;
  openDueTasks.disabled = navigationLocked || workspaceSelectionBusy;
  openBlockedTasks.disabled = navigationLocked || workspaceSelectionBusy;
  newTask.disabled = Boolean(taskUpdate) || editorOpen || projectSaving || loadingDueMore;
  events.disableCreate(newTask.disabled || workspaceSelectionBusy);
  retryWork.inert = eventLocked || sharingLocked;
  more.inert = retryWork.inert || (isDueTasksView() && (editorOpen || Boolean(taskUpdate)));
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
  selectTaskProject(task ? task.project_id ?? "" : selectedProject());
  taskPriority.value = task ? task.priority ?? "normal" : (selectedPriority() || "normal");
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
    if (isDueView() || selectedTaskStatus()) {
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
      clearDeniedWork(status);
      taskFeedback.textContent = "You no longer have permission to update this task.";
      return;
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
  row.dataset.workId = item.id;
  const title = document.createElement("strong");
  const detail = document.createElement("span");
  title.textContent = item.data.title;
  const metadata = [item.data.kind, item.data.status];
  if (item.priority === "high") metadata.push("High priority");
  if (item.priority === "low") metadata.push("Low priority");
  const project = projects.find(({ id }) => id === item.project_id);
  if (project) metadata.push(project.name);
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
  return workspaceView === "today" || isDueTasksView();
}

function isDueTasksView() {
  return workspaceView === "work" && workView.value === "due";
}

function isScheduleView() {
  return workspaceView === "work" && workView.value === "schedule";
}

function supportsTaskStatus() {
  return workspaceView === "work" && !["due", "events", "schedule"].includes(workView.value);
}

function selectedTaskStatus() {
  return supportsTaskStatus() ? workTaskStatus.value : "";
}

function selectedProject() {
  return supportsTaskStatus() ? workProject.value : "";
}

function selectedPriority() {
  return supportsTaskStatus() ? workPriority.value : "";
}

function selectTaskProject(id) {
  taskProject.querySelector("[data-current-project]")?.remove();
  if (id && !projects.some(project => project.id === id)) {
    const current = new Option("Current project", id);
    current.dataset.currentProject = "";
    taskProject.add(current);
  }
  taskProject.value = id;
}

function showProjects(list) {
  const selected = workProject.value;
  projects = list;
  workProject.replaceChildren(new Option("All projects", ""), ...list.map(p => new Option(p.name, p.id)));
  taskProject.replaceChildren(new Option("No project", ""), ...list.map(p => new Option(p.name, p.id)));
  if (list.some(p => p.id === selected)) workProject.value = selected;
  if (editingTask?.project_id) selectTaskProject(editingTask.project_id);
}

function clearProjectCatalog() {
  projectVersion += 1;
  projectsWorkspace = "";
  showProjects([]);
  projectFeedback.textContent = "";
}

async function loadProjects() {
  const id = select.value;
  if (projectsWorkspace === id) return;
  const version = ++projectVersion;
  try {
    const list = await request("workspaces/" + encodeURIComponent(id) + "/projects");
    if (version !== projectVersion || select.value !== id) return;
    projectsWorkspace = id;
    showProjects(list);
    projectFeedback.textContent = "";
  } catch (status) {
    if (version !== projectVersion || select.value !== id || expired(status)) return;
    if (status === 403) throw status;
    projectFeedback.textContent = "Could not load projects. Refresh workspaces to retry.";
  }
}

function resetWorkSearch() {
  workQuery = workSearchTitle.value = "";
}

function resetWorkFilters() {
  resetWorkSearch();
  dueFilterDate = dueFromDate.value = "";
  workTaskStatus.value = "";
  workPriority.value = "";
  clearProjectCatalog();
  projectSaving = false;
  createProject.reset();
}

function localDate() {
  const now = new Date();
  const parts = [now.getFullYear(), now.getMonth() + 1, now.getDate()];
  return parts.map((value, index) => String(value).padStart(index === 0 ? 4 : 2, "0")).join("-");
}

function loadWorkView() {
  void loadWork();
  void loadScheduleDeadlines();
}

function overlapsLoadedRows(list, incoming) {
  const loadedIds = new Set(Array.from(list.children, row => row.dataset.workId));
  return incoming.some(item => loadedIds.has(item.id));
}

function restartWorkList(schedule) {
  clearWork();
  workStatus.textContent = (schedule ? "The schedule" : "The due task list")
    + " changed. Retry to start from the first page.";
  retryWork.hidden = false;
}

async function loadWork(append = false, savedMessage = "", eventMessage = "", shareMessage = "") {
  if (append && (!nextCursor || more.inert || more.disabled)) return;
  if (!append) {
    clearWork();
    taskFeedback.textContent = savedMessage;
    events.showFeedback(eventMessage);
    sharing.showFeedback(shareMessage);
  }
  if (!session || !select.value) return;
  const today = workspaceView === "today" ? localDate() : undefined;
  const dueOnly = isDueView();
  const dueTasks = isDueTasksView();
  const dueFrom = dueTasks ? dueFilterDate : "";
  const schedule = isScheduleView();
  const eventsOnly = schedule || (!dueOnly && workView.value === "events");
  const visibility = !dueOnly && ["private", "workspace"].includes(workView.value) ? workView.value : undefined;
  const sharedOnly = visibility === "workspace";
  const titleQuery = dueOnly || schedule ? "" : workQuery;
  const taskStatus = selectedTaskStatus();
  const projectId = selectedProject();
  const priority = selectedPriority();
  const version = ++workVersion;
  const active = sessionVersion;
  const path = "workspaces/" + encodeURIComponent(select.value)
    + (schedule ? "/work-schedule" : dueTasks ? "/work-due-page" : today ? "/work-due" : "/work-page");
  const query = { limit: today ? 21 : 20 };
  if (dueFrom) query.from_date = dueFrom;
  if (eventsOnly && !schedule) query.kind = "event";
  if (visibility) query.visibility = visibility;
  if (taskStatus) query.task_status = taskStatus;
  if (projectId) query.project_id = projectId;
  if (priority) query.priority = priority;
  if (append && nextCursor) Object.assign(query, nextCursor);
  workStatus.textContent = "Loading work items…";
  more.disabled = true;
  if (append && dueTasks) {
    loadingDueMore = true;
    syncWorkControls();
  }
  try {
    const listing = titleQuery
      ? request(path + "/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...query, q: titleQuery }),
      })
      : request(path + "?" + new URLSearchParams(query));
    const [page] = await Promise.all([listing, !eventsOnly && loadProjects()]);
    if (version !== workVersion || !session) return;
    if (append && (dueTasks || schedule) && overlapsLoadedRows(items, page.items)) {
      restartWorkList(schedule);
      return;
    }
    // The due endpoint sorts by date, so later rows cannot qualify after a future date.
    const visible = today ? page.items.filter(item => item.data.due_date <= today) : page.items;
    items.append(...visible.slice(0, 20).map(item => renderItem(item, today)));
    newTask.hidden = !canWriteWork() || eventsOnly || sharedOnly;
    events.showCreate(!dueOnly && !sharedOnly && !taskStatus && !projectId && !priority && canWriteWork());
    loadingDueMore = false;
    syncWorkControls();
    nextCursor = page.next_after ? { after: page.next_after } : undefined;
    if ((schedule || dueTasks) && nextCursor) nextCursor.after_version = page.items.at(-1).version;
    more.hidden = !nextCursor;
    more.disabled = false;
    if (today) {
      workStatus.textContent = visible.length > 20
        ? "Showing the 20 earliest tasks due by today. Open Work items to see more."
        : visible.length ? "" : "No tasks due today or overdue.";
    } else if (dueTasks) {
      const empty = dueFrom ? "No unfinished tasks due from this date." : "No unfinished tasks with due dates.";
      workStatus.textContent = items.childElementCount ? "" : empty;
    } else if (schedule) {
      workStatus.textContent = items.childElementCount ? "" : "No ongoing or upcoming events.";
    } else {
      workStatus.textContent = items.childElementCount ? ""
        : taskStatus || projectId || priority ? "No tasks match the current filters."
        : titleQuery ? "No work titles match your search."
        : eventsOnly ? "No events yet." : sharedOnly ? "No shared work yet." : "No work items yet.";
    }
  } catch (status) {
    if (active !== sessionVersion || version !== workVersion || expired(status)) return;
    if (clearDeniedFocus(status)) {
      taskFeedback.textContent = savedMessage;
      return;
    }
    if (status === 403) clearProjectCatalog();
    if (append && status !== 403 && status !== 404) {
      workStatus.textContent = "Could not load more work items. Try again.";
      more.disabled = false;
      loadingDueMore = false;
      syncWorkControls();
      return;
    }
    if ((schedule || dueTasks) && append && status === 404) {
      restartWorkList(schedule);
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

function clearDeniedFocus(status) {
  const today = workspaceView === "today";
  if (status !== 403 || (!today && !isScheduleView())) return false;
  clearWork();
  clearProjectCatalog();
  if (today) clearTodayLists();
  else clearScheduleDeadlines();
  workStatus.textContent = (today ? "Today" : "Schedule") + " is unavailable. Refresh your workspaces to try again.";
  return true;
}

function clearDeniedWork(status) {
  if (status === 403) clearWorkspaceWriteHint();
  if (!clearDeniedFocus(status)) {
    if (status === 403) clearProjectCatalog();
    clearWork();
    retryWork.hidden = false;
  }
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
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = proposal.title;
      button.disabled = showInbox.disabled;
      button.addEventListener("click", () => switchWorkspaceView("inbox", proposal));
      item.append(button);
      reviewItems.append(item);
    }
    reviewsStatus.textContent = proposals.length ? "" : "No pending reviews.";
  } catch (status) {
    if (version !== reviewVersion || expired(status) || clearDeniedFocus(status)) return;
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
    if (version !== eventVersion || expired(status) || clearDeniedFocus(status)) return;
    eventsStatus.textContent = status === 404
      ? "Upcoming events are unavailable."
      : "Could not load upcoming events.";
    retryEvents.hidden = false;
  }
}

function resetDeadlinePage() {
  scheduleDeadlineVersion += 1;
  nextDeadlineCursor = undefined;
  retryScheduleDeadlines.hidden = moreScheduleDeadlines.hidden = true;
  scheduleDeadlineItems.replaceChildren();
  scheduleDeadlinesStatus.textContent = "";
}

function clearScheduleDeadlines() {
  resetDeadlinePage();
  scheduleDeadlineDate = deadlineFromDate.value = "";
  scheduleDeadlines.hidden = true;
}

function showDeadlineRetry(message) {
  resetDeadlinePage();
  scheduleDeadlinesStatus.textContent = message;
  retryScheduleDeadlines.hidden = false;
}

async function loadScheduleDeadlines(append = false) {
  if (!isScheduleView() || !session || !select.value) {
    clearScheduleDeadlines();
    return;
  }
  if (append && !nextDeadlineCursor) return;
  if (!append) resetDeadlinePage();
  const version = ++scheduleDeadlineVersion;
  if (!scheduleDeadlineDate) scheduleDeadlineDate = deadlineFromDate.value = localDate();
  scheduleDeadlines.hidden = false;
  scheduleDeadlinesStatus.textContent = "Loading deadlines…";
  moreScheduleDeadlines.disabled = true;
  const changedMessage = "The deadline list changed. Retry to start from the first page.";
  try {
    const query = new URLSearchParams({
      limit: 5, from_date: scheduleDeadlineDate, ...(append ? nextDeadlineCursor : {}),
    });
    const path = "workspaces/" + encodeURIComponent(select.value) + "/work-due-page?" + query;
    const page = await request(path);
    if (version !== scheduleDeadlineVersion) return;
    if (append && overlapsLoadedRows(scheduleDeadlineItems, page.items)) {
      showDeadlineRetry(changedMessage);
      return;
    }
    for (const { id, data: task } of page.items) {
      const row = document.createElement("li");
      row.dataset.workId = id;
      const title = document.createElement("strong");
      const due = document.createElement("time");
      title.textContent = task.title;
      due.dateTime = task.due_date;
      due.textContent = deadlineDateFormat.format(new Date(task.due_date + "T00:00:00Z"));
      row.append(title, " · Due ", due);
      scheduleDeadlineItems.append(row);
    }
    nextDeadlineCursor = page.next_after
      ? { after: page.next_after, after_version: page.items.at(-1).version }
      : undefined;
    moreScheduleDeadlines.hidden = !nextDeadlineCursor;
    moreScheduleDeadlines.disabled = false;
    scheduleDeadlinesStatus.textContent = scheduleDeadlineItems.childElementCount
      ? "" : "No task deadlines from this date.";
  } catch (status) {
    if (version !== scheduleDeadlineVersion || expired(status) || clearDeniedFocus(status)) return;
    if (append && status !== 404) {
      scheduleDeadlinesStatus.textContent = "Could not load more deadlines. Try again.";
      moreScheduleDeadlines.disabled = false;
      return;
    }
    showDeadlineRetry(append ? changedMessage : "Could not load deadlines.");
  }
}

async function loadWorkspaces(created, preferredId) {
  if (!session) return;
  const version = sessionVersion;
  const previous = select.value;
  const preferred = created?.id ?? preferredId ?? previous;
  workspaceSelectionBusy = true;
  reminders.select(undefined, session);
  inbox.clear();
  notes.clear();
  access.clear();
  invitations.clear();
  clearTodayLists();
  clearScheduleDeadlines();
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
    if (select.value !== previous) resetWorkFilters();
    else {
      projectVersion += 1;
      projectsWorkspace = "";
    }
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
  const projectId = taskProject.disabled ? null : taskProject.value || null;
  if (task && !taskProject.disabled && projectId !== (task.project_id ?? null)) {
    details.project_id = projectId;
  }
  const priority = taskPriority.value;
  if (task && priority !== (task.priority ?? "normal")) details.priority = priority;
  saveTask.disabled = cancelTask.disabled = true;
  taskProject.disabled = taskPriority.disabled = true;
  taskTitle.readOnly = taskDescription.readOnly = taskDueDate.readOnly = true;
  taskFeedback.textContent = "Saving task…";
  try {
    await request(task ? path + "/" + encodeURIComponent(task.id) + "/task-details" : path, {
      method: task ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token },
      body: JSON.stringify(task
        ? { expected_version: task.version, details }
        : { item: { kind: "task", ...details }, priority, ...(projectId ? { project_id: projectId } : {}) }),
    });
    if (version !== editorVersion) return;
    void loadWork(false, task ? "Task updated." : "Task created.");
  } catch (status) {
    if (version !== editorVersion || expired(status)) return;
    if (status === 409 && task) {
      taskFeedback.textContent = "This task changed. Close the editor, refresh the work list, and reopen the task.";
      retryWork.hidden = false;
    } else if (status === 403 || status === 404) {
      clearDeniedWork(status);
      taskFeedback.textContent = "You no longer have permission to save this task.";
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
      syncWorkControls();
    }
  }
});

newTask.addEventListener("click", () => openTaskEditor());
cancelTask.addEventListener("click", () => {
  const opener = taskOpener;
  closeTaskEditor();
  if (opener?.isConnected) opener.focus();
});
select.addEventListener("change", () => {
  resetWorkFilters();
  loadSelectedWorkspaceView();
});
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
function openAllWork(status) {
  workView.value = "all";
  resetWorkSearch();
  workPriority.value = workProject.value = "";
  workTaskStatus.value = status;
  switchWorkspaceView("work");
  showWork.focus();
}
openBlockedTasks.addEventListener("click", () => openAllWork("blocked"));
function openEventView(view) {
  workView.value = view;
  resetWorkSearch();
  switchWorkspaceView("work");
  showWork.focus();
}
openEvents.addEventListener("click", () => openEventView("events"));
openSchedule.addEventListener("click", () => openEventView("schedule"));
retryScheduleDeadlines.addEventListener("click", () => loadScheduleDeadlines());
moreScheduleDeadlines.addEventListener("click", () => loadScheduleDeadlines(true));
deadlineFilter.addEventListener("submit", event => {
  event.preventDefault();
  scheduleDeadlineDate = deadlineFromDate.value;
  void loadScheduleDeadlines();
});
openDueTasks.addEventListener("click", () => {
  dueFilterDate = dueFromDate.value = scheduleDeadlineDate;
  workView.value = "due";
  loadWorkView();
  workView.focus();
});
workView.addEventListener("change", () => {
  dueFilterDate = dueFromDate.value = "";
  loadWorkView();
});
dueDateFilter.addEventListener("submit", event => {
  event.preventDefault();
  if (dueDateFilter.hidden || applyDueDate.disabled) return;
  dueFilterDate = dueFromDate.value;
  void loadWork();
});
clearDueDate.addEventListener("click", () => {
  if (dueDateFilter.hidden || clearDueDate.disabled) return;
  dueFilterDate = dueFromDate.value = "";
  dueFromDate.focus();
  void loadWork();
});
workTaskStatus.addEventListener("change", () => loadWork());
workPriority.addEventListener("change", () => loadWork());
workProject.addEventListener("change", () => loadWork());
createProject.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (saveProject.disabled || !session || !select.value) return;
  const name = projectName.value.trim();
  if (!name) {
    projectFeedback.textContent = "Enter a project name.";
    return;
  }
  const id = select.value;
  const version = sessionVersion;
  projectSaving = true;
  syncWorkControls();
  projectFeedback.textContent = "Creating project…";
  try {
    const project = await request("workspaces/" + encodeURIComponent(id) + "/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (version !== sessionVersion || id !== select.value) return;
    showProjects([...projects, project].sort((a, b) => a.name.localeCompare(b.name)));
    workProject.value = project.id;
    createProject.reset();
    projectFeedback.textContent = "Project created.";
    void loadWork();
  } catch (status) {
    if (version !== sessionVersion || id !== select.value || expired(status)) return;
    if (status === 403) {
      clearDeniedWork(status);
      createProject.reset();
      projectFeedback.textContent = "You no longer have permission to create projects. Refresh your workspaces.";
      return;
    }
    projectFeedback.textContent = status === 409
      ? "A project with that name already exists."
      : "Could not confirm project creation. Refresh workspaces before retrying.";
  } finally {
    if (version === sessionVersion && id === select.value) {
      projectSaving = false;
      syncWorkControls();
    }
  }
});
workSearch.addEventListener("submit", (event) => {
  event.preventDefault();
  if (workSearch.hidden || submitWorkSearch.disabled) return;
  workQuery = workSearchTitle.value = workSearchTitle.value.trim();
  void loadWork();
});
clearWorkSearch.addEventListener("click", () => {
  if (workSearch.hidden || clearWorkSearch.disabled) return;
  resetWorkSearch();
  workSearchTitle.focus();
  void loadWork();
});
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
