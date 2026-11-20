"use strict";

function createWorkspaceReminders({ request, expired, localDate }) {
  const toggle = document.querySelector("#toggle-reminders");
  const status = document.querySelector("#reminders-status");
  const popup = document.querySelector("#reminder-popup");
  const settings = document.querySelector("#reminder-settings");
  const category = document.querySelector("#reminder-category");
  const lead = document.querySelector("#reminder-lead");
  const duration = document.querySelector("#reminder-snooze");
  const list = document.querySelector("#reminder-items");
  const overflow = document.querySelector("#reminder-overflow");
  const snooze = document.querySelector("#snooze-reminders");
  const dismiss = document.querySelector("#dismiss-reminders");
  const workspaces = new Map();
  const defaults = { category: "both", lead: "15", duration: "5" };
  let workspace;
  let session;
  let state;
  let generation = 0;
  let timer;
  let expiryTimer;
  let pending;
  let shown = [];

  function clearPopup() {
    clearTimeout(expiryTimer);
    popup.hidden = true;
    list.replaceChildren();
    overflow.hidden = true;
    shown = [];
  }

  function stop() {
    generation += 1;
    clearTimeout(timer);
    pending?.abort();
    pending = undefined;
    clearPopup();
  }

  function render(page) {
    const now = Date.now();
    const upcoming = page.events.filter(event => Date.parse(event.starts_at) > now);
    const items = [
      ...page.tasks.map(task => ({ ...task, key: `task:${task.id}:${task.due_date}`, label: "Due today" })),
      ...upcoming.map(event => ({
        ...event,
        key: `event:${event.id}:${event.starts_at}`,
        label: "Starts " + new Intl.DateTimeFormat(undefined, {
          hour: "numeric", minute: "2-digit", timeZoneName: "short",
        }).format(new Date(event.starts_at)),
      })),
    ];
    for (const [key, until] of state.snoozed) {
      if (until <= now) state.snoozed.delete(key);
    }
    display(
      items.filter(item => !state.dismissed.has(item.key) && !state.snoozed.has(item.key)),
      page.has_more,
    );
  }

  function display(next, hasMore) {
    // Leave the live region alone on polls that didn't change the visible items.
    if (next.length !== shown.length || next.some((item, index) =>
      item.key !== shown[index].key || item.title !== shown[index].title || item.label !== shown[index].label
    )) {
      list.replaceChildren(...next.map(item => {
        const row = document.createElement("li");
        const title = document.createElement("strong");
        const label = document.createElement("span");
        title.textContent = item.title;
        label.textContent = item.label;
        row.append(title, label);
        return row;
      }));
    }
    shown = next;
    overflow.hidden = !hasMore;
    popup.hidden = !shown.length;
    scheduleExpiry();
  }

  function scheduleExpiry() {
    clearTimeout(expiryTimer);
    const now = new Date();
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime();
    const cutoffs = shown.map(item => item.starts_at ? Date.parse(item.starts_at) : midnight);
    if (!cutoffs.length) return;
    // End an occurrence on time even when the network request takes longer.
    expiryTimer = setTimeout(() => {
      const day = localDate();
      const instant = Date.now();
      display(shown.filter(item => item.starts_at
        ? Date.parse(item.starts_at) > instant : item.due_date === day), !overflow.hidden);
      if (!pending) {
        clearTimeout(timer);
        void poll();
      }
    }, Math.max(1, Math.min(...cutoffs) - now.getTime()));
  }

  function syncSettings() {
    const preferences = state?.preferences ?? defaults;
    toggle.hidden = settings.hidden = !workspace;
    toggle.setAttribute("aria-pressed", String(Boolean(state?.enabled)));
    category.value = preferences.category;
    lead.value = preferences.lead;
    lead.disabled = preferences.category === "tasks";
    duration.value = preferences.duration;
    snooze.textContent = `Snooze ${preferences.duration} minutes`;
  }

  async function poll() {
    if (!workspace || !state?.enabled || document.hidden || pending) return;
    if (session.expires_at * 1000 <= Date.now()) {
      expired(401);
      return;
    }
    const version = generation;
    const controller = new AbortController();
    pending = controller;
    const timeout = setTimeout(() => controller.abort(), 20_000);
    const day = localDate();
    const preferences = state.preferences;
    const query = new URLSearchParams({ local_date: day });
    if (preferences.category !== defaults.category) query.set("category", preferences.category);
    if (preferences.category !== "tasks" && preferences.lead !== defaults.lead) {
      query.set("event_lead_minutes", preferences.lead);
    }
    let delay = 30_000;
    try {
      const page = await request("workspaces/" + encodeURIComponent(workspace)
        + "/reminders?" + query, {
        headers: { "X-CSRF-Token": session.csrf_token }, signal: controller.signal,
      });
      if (version !== generation || document.hidden) return;
      if (session.expires_at * 1000 <= Date.now()) {
        expired(401);
        return;
      }
      if (day === localDate()) {
        render(page);
        status.textContent = "";
      } else {
        clearPopup();
        delay = 1;
      }
    } catch (failure) {
      if (version !== generation || expired(failure)) return;
      clearPopup();
      if (failure === 403 || failure === 404) {
        state.enabled = false;
        syncSettings();
        status.textContent = "Reminders are unavailable for this workspace.";
      } else {
        status.textContent = "Reminders could not refresh. Retrying shortly.";
      }
    } finally {
      clearTimeout(timeout);
      if (version === generation) {
        pending = undefined;
        if (state.enabled && !document.hidden) timer = setTimeout(poll, delay);
      }
    }
  }

  function select(id, currentSession) {
    if (id === workspace && currentSession === session) return;
    stop();
    workspace = id;
    session = currentSession;
    state = workspaces.get(id);
    settings.open = false;
    syncSettings();
    status.textContent = "";
    void poll();
  }

  function ensureState() {
    if (!state) {
      state = { enabled: false, preferences: { ...defaults }, dismissed: new Set(), snoozed: new Map() };
      workspaces.set(workspace, state);
    }
  }

  toggle.addEventListener("click", () => {
    if (!workspace) return;
    ensureState();
    state.enabled = !state.enabled;
    syncSettings();
    status.textContent = state.enabled ? "Checking for reminders…" : "Reminders off.";
    if (state.enabled) void poll();
    else stop();
  });

  settings.addEventListener("change", () => {
    if (!workspace) return;
    ensureState();
    const previous = state.preferences;
    state.preferences = { category: category.value, lead: lead.value, duration: duration.value };
    syncSettings();
    if (previous.category === category.value && previous.lead === lead.value) return;
    stop();
    status.textContent = state.enabled ? "Checking for reminders…" : "";
    void poll();
  });

  snooze.addEventListener("click", () => {
    const minutes = state.preferences.duration;
    const until = Date.now() + Number(minutes) * 60_000;
    for (const { key } of shown) state.snoozed.set(key, until);
    clearPopup();
    status.textContent = `Reminders snoozed for ${minutes} minutes.`;
    toggle.focus();
  });

  dismiss.addEventListener("click", () => {
    for (const { key } of shown) state.dismissed.add(key);
    clearPopup();
    status.textContent = "Reminders dismissed.";
    toggle.focus();
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stop();
      status.textContent = "";
    } else void poll();
  });

  return {
    select,
    clear() {
      workspaces.clear();
      select(undefined, undefined);
    },
  };
}
