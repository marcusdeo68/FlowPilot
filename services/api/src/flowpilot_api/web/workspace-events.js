"use strict";

function renderEventTimes(row, event) {
  const options = {
    year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    timeZoneName: "short", timeZone: event.time_zone,
  };
  let formatter;
  try {
    formatter = new Intl.DateTimeFormat(undefined, options);
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
    // The API may know a time zone identifier that this browser does not.
    formatter = new Intl.DateTimeFormat(undefined, { ...options, timeZone: "UTC" });
  }
  for (const [label, value] of [["Starts ", event.starts_at], ["Ends ", event.ends_at]]) {
    const line = document.createElement("span");
    const timestamp = document.createElement("time");
    timestamp.dateTime = value;
    timestamp.textContent = formatter.format(new Date(value));
    line.append(label, timestamp);
    row.append(line);
  }
}

function eventScheduleForEditor(event) {
  const options = {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    second: "2-digit", hourCycle: "h23", timeZone: event.time_zone,
  };
  const locale = "en-GB-u-ca-iso8601-nu-latn";
  let zone = event.time_zone;
  let formatter;
  try {
    formatter = new Intl.DateTimeFormat(locale, options);
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
    zone = "UTC";
    formatter = new Intl.DateTimeFormat(locale, { ...options, timeZone: zone });
  }
  const local = value => {
    const parts = Object.fromEntries(formatter.formatToParts(new Date(value))
      .map(({ type, value }) => [type, value]));
    const fraction = value.match(/:\d{2}(\.\d+)(?:Z|[+-]\d{2}:\d{2})$/)?.[1] ?? "";
    return `${parts.year.padStart(4, "0")}-${parts.month}-${parts.day}T`
      + `${parts.hour}:${parts.minute}:${parts.second}${fraction}`;
  };
  return { time_zone: zone, starts_at: local(event.starts_at), ends_at: local(event.ends_at) };
}

function createWorkspaceEvents({ request, context, expired, reload, offerReload, deny, syncControls }) {
  const editor = document.querySelector("#event-editor");
  const heading = document.querySelector("#event-editor-heading");
  const fields = document.querySelector("#event-fields");
  const title = document.querySelector("#event-title");
  const description = document.querySelector("#event-description");
  const zone = document.querySelector("#event-zone");
  const start = document.querySelector("#event-start");
  const end = document.querySelector("#event-end");
  const create = document.querySelector("#new-event");
  const save = document.querySelector("#save-event");
  const close = document.querySelector("#close-event-editor");
  const feedback = document.querySelector("#event-feedback");

  let generation = 0;
  let item;
  let initial;
  let pending = false;
  let paused = false;

  function readSchedule() {
    return { time_zone: zone.value.trim(), starts_at: start.value, ends_at: end.value };
  }

  function closeEditor() {
    editor.reset();
    editor.hidden = true;
    item = initial = undefined;
  }

  function clear() {
    generation += 1;
    pending = paused = false;
    save.disabled = close.disabled = fields.disabled = false;
    create.hidden = true;
    feedback.textContent = "";
    closeEditor();
  }

  function open(record) {
    if (create.hidden || create.disabled) return;
    item = record;
    title.value = item?.data.title ?? "";
    description.value = item?.data.description ?? "";
    const schedule = item ? eventScheduleForEditor(item.data) : undefined;
    if (schedule) {
      zone.value = schedule.time_zone;
      // Native controls support milliseconds. Keep the full stored values for unchanged fields.
      start.value = schedule.starts_at.replace(/(\.\d{3})\d+$/, "$1");
      end.value = schedule.ends_at.replace(/(\.\d{3})\d+$/, "$1");
    } else {
      zone.value = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    }
    initial = { title: title.value, description: description.value, shown: readSchedule(), schedule };
    heading.textContent = item ? "Edit event" : "New private event";
    save.textContent = item ? "Save event changes" : "Create event";
    feedback.textContent = "";
    editor.hidden = false;
    syncControls();
    title.focus();
  }

  async function mutate(path, method, body, success) {
    const current = context();
    if (!current || pending || paused) return;
    const version = generation;
    pending = true;
    save.disabled = close.disabled = fields.disabled = true;
    syncControls();
    feedback.textContent = "Saving event…";
    let validationError;
    try {
      await request(current.path + path, {
        method,
        headers: { "Content-Type": "application/json", "X-CSRF-Token": current.csrf },
        body: JSON.stringify(body),
      }, errors => {
        const fields = { starts_at: "Start", ends_at: "End", time_zone: "Time zone" };
        const known = errors?.find?.(error => Object.hasOwn(fields, error.loc?.at(-1)));
        if (known && typeof known.msg === "string") {
          validationError = fields[known.loc.at(-1)] + ": " + known.msg.replace(/^Value error, /, "");
        } else if (errors?.some?.(error => error.msg === "Value error, Event end must follow start")) {
          validationError = "Event end must follow start.";
        }
      });
      if (version === generation) reload(success);
    } catch (status) {
      if (version !== generation || expired(status)) return;
      if (status === 403 || status === 404) {
        deny(status);
        return;
      }
      paused = status !== 422;
      if (paused) offerReload();
      feedback.textContent = status === 422
        ? validationError || "Check the event title, description, times, and time zone."
        : status === 409
          ? "This event changed. Refresh the work list before trying again."
          : "Could not confirm the save. Refresh the work list before trying again.";
    } finally {
      if (version === generation) {
        pending = false;
        close.disabled = fields.disabled = false;
        save.disabled = paused;
        syncControls();
      }
    }
  }

  editor.addEventListener("submit", event => {
    event.preventDefault();
    if (editor.hidden || save.disabled) return;
    const details = {
      title: item && title.value === initial.title ? item.data.title : title.value.trim(),
      description: item && description.value === initial.description
        ? item.data.description : description.value.trim() || null,
    };
    if (!details.title) {
      feedback.textContent = "Enter an event title.";
      return;
    }
    const schedule = readSchedule();
    if (item) {
      const changed = Object.entries(schedule).some(([key, value]) => value !== initial.shown[key]);
      if (changed && schedule.time_zone === initial.shown.time_zone) {
        for (const key of ["starts_at", "ends_at"]) {
          if (schedule[key] === initial.shown[key]) schedule[key] = initial.schedule[key];
        }
      }
      void mutate("/work/" + encodeURIComponent(item.id) + "/event-details", "PATCH", {
        expected_version: item.version, details, schedule: changed ? schedule : null,
      }, "Event updated.");
    } else {
      void mutate("/work-events", "POST", { ...details, schedule }, "Event created.");
    }
  });

  create.addEventListener("click", () => open());
  close.addEventListener("click", () => {
    if (pending) return;
    closeEditor();
    if (!paused) feedback.textContent = "";
    syncControls();
    (create.disabled ? document.querySelector("#retry-work") : create).focus();
  });

  function renderActions(row, record, own) {
    if (record.data.status !== "scheduled") return;
    const actions = document.createElement("div");
    actions.className = "actions event-actions";
    const button = (label, handler) => {
      const control = document.createElement("button");
      control.type = "button";
      control.textContent = label;
      control.addEventListener("click", handler);
      actions.append(control);
    };
    if (own) button("Edit event", () => open(record));
    button("Cancel event", () => {
      if (pending || paused || !editor.hidden || !row.isConnected) return;
      if (!window.confirm("Cancel this event? It cannot be reopened.")) return;
      void mutate("/work/" + encodeURIComponent(record.id) + "/transitions", "POST", {
        expected_version: record.version, target: "canceled",
      }, "Event canceled.");
    });
    row.append(actions);
  }

  return {
    clear,
    renderActions,
    locked: () => !editor.hidden || pending,
    paused: () => paused,
    showCreate(visible) { create.hidden = !visible; },
    disableCreate(disabled) { create.disabled = disabled || paused; },
    showFeedback(message) { feedback.textContent = message; },
  };
}
