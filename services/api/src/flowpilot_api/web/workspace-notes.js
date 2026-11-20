"use strict";

function createWorkspaceNotes({ request, expired, lockNavigation, denyWrites }) {
  const view = document.querySelector("#notes-view");
  const newNote = document.querySelector("#new-note");
  const refresh = document.querySelector("#refresh-notes");
  const editor = document.querySelector("#note-editor");
  const heading = document.querySelector("#note-editor-heading");
  const body = document.querySelector("#note-body");
  const save = document.querySelector("#save-note");
  const close = document.querySelector("#close-note-editor");
  const feedback = document.querySelector("#notes-feedback");
  const status = document.querySelector("#notes-status");
  const cards = document.querySelector("#notes-items");
  const more = document.querySelector("#more-notes");

  let context;
  let pageRequest;
  let cursor;
  let selectedNote;
  let loadedBody;
  let saving = false;
  let needsRefresh = false;

  function syncControls() {
    const editing = !editor.hidden;
    const locked = saving || editing;
    const loading = Boolean(pageRequest);
    lockNavigation(locked);
    view.disabled = refresh.disabled = locked;
    more.disabled = locked || loading;
    newNote.disabled = locked || loading || needsRefresh;
    close.disabled = body.readOnly = saving;
    save.disabled = saving || needsRefresh || Boolean(selectedNote && body.value === loadedBody);
    for (const button of cards.querySelectorAll("button")) {
      button.disabled = locked || loading || needsRefresh;
    }
  }

  function closeEditor() {
    selectedNote = loadedBody = undefined;
    editor.reset();
    editor.hidden = true;
  }

  function clear() {
    context = pageRequest = cursor = undefined;
    saving = needsRefresh = false;
    view.value = "active";
    cards.replaceChildren();
    status.textContent = feedback.textContent = "";
    newNote.hidden = more.hidden = true;
    closeEditor();
    syncControls();
  }

  function unavailable(active, writeDenied) {
    const selection = view.value;
    clear();
    view.value = selection;
    if (writeDenied) denyWrites();
    context = { ...active, canWrite: active.canWrite && !writeDenied };
    status.textContent = writeDenied
      ? "Note access changed. Refresh notes to browse, or refresh workspaces before writing."
      : "This note is unavailable. Refresh your notes.";
  }

  function openEditor(note) {
    if (!context?.canWrite || !editor.hidden || saving || pageRequest || needsRefresh) return;
    selectedNote = note;
    heading.textContent = note ? "Edit note" : "New note";
    body.value = note?.body ?? "";
    loadedBody = body.value;
    editor.hidden = false;
    feedback.textContent = "";
    syncControls();
    body.focus();
  }

  function renderCard(note, canWrite) {
    const card = document.createElement("li");
    const noteText = document.createElement("p");
    noteText.textContent = note.body;
    card.append(noteText);
    if (canWrite) {
      const actions = document.createElement("div");
      actions.className = "actions";
      if (!note.archived) {
        const edit = document.createElement("button");
        edit.type = "button";
        edit.textContent = "Edit note";
        edit.addEventListener("click", () => openEditor(note));
        actions.append(edit);
      }
      const move = document.createElement("button");
      move.type = "button";
      move.textContent = note.archived ? "Restore note" : "Archive note";
      move.addEventListener("click", () => changeNote(
        "/" + encodeURIComponent(note.id) + "/state",
        "POST",
        { expected_version: note.version, archived: !note.archived },
        note.archived ? "Note restored." : "Note archived.",
      ));
      actions.append(move);
      card.append(actions);
    }
    return card;
  }

  async function loadNotes(append = false, message = "") {
    const active = context;
    if (!active || saving || !editor.hidden || (append && (!cursor || pageRequest))) return;
    const token = {};
    pageRequest = token;
    const archived = view.value === "archived";
    const query = new URLSearchParams({ archived: String(archived), limit: "25" });
    if (append) query.set("after", cursor);
    else {
      cursor = undefined;
      cards.replaceChildren();
      newNote.hidden = more.hidden = true;
    }
    if (message) feedback.textContent = message;
    status.textContent = "Loading notes…";
    syncControls();
    try {
      const page = await request(active.path + "?" + query);
      if (context !== active || pageRequest !== token) return;
      cards.append(...page.items.map(note => renderCard(note, active.canWrite)));
      newNote.hidden = !active.canWrite || archived;
      cursor = page.next_after;
      more.hidden = !cursor;
      status.textContent = cards.childElementCount ? "" : archived ? "No archived notes." : "No notes yet.";
      if (needsRefresh) {
        needsRefresh = false;
        feedback.textContent = "Notes refreshed. Check the saved notes before trying again.";
      }
    } catch (error) {
      if (context !== active || pageRequest !== token || expired(error)) return;
      if (error === 403 || error === 404) unavailable(active, error === 403);
      else status.textContent = "Could not load notes. Refresh to try again.";
    } finally {
      if (context === active && pageRequest === token) {
        pageRequest = undefined;
        syncControls();
      }
    }
  }

  async function changeNote(suffix, method, payload, message) {
    const active = context;
    if (!active?.canWrite || saving || needsRefresh) return;
    saving = true;
    syncControls();
    feedback.textContent = "Saving note…";
    try {
      await request(active.path + suffix, {
        method,
        headers: { "Content-Type": "application/json", "X-CSRF-Token": active.csrf },
        body: JSON.stringify(payload),
      });
      if (context !== active) return;
      saving = false;
      closeEditor();
      void loadNotes(false, message);
    } catch (error) {
      if (context !== active || expired(error)) return;
      if (error === 403 || error === 404) unavailable(active, error === 403);
      else if (error === 422) feedback.textContent = "Check the note text and try again.";
      else {
        needsRefresh = true;
        const recovery = editor.hidden ? "Refresh your notes." : "Copy your draft if needed, close the editor, then refresh your notes.";
        feedback.textContent = (error === 409 ? "This note changed. " : "Could not confirm the save. ") + recovery;
      }
    } finally {
      if (context === active) {
        saving = false;
        syncControls();
      }
    }
  }

  newNote.addEventListener("click", () => openEditor());
  close.addEventListener("click", () => {
    closeEditor();
    syncControls();
    (needsRefresh ? refresh : newNote).focus();
  });
  body.addEventListener("input", syncControls);
  editor.addEventListener("submit", event => {
    event.preventDefault();
    if (editor.hidden || save.disabled) return;
    if (!body.value.trim() || [...body.value].length > 2000) {
      feedback.textContent = "Enter between 1 and 2,000 characters of note text.";
      return;
    }
    const payload = { body: body.value };
    if (selectedNote) {
      payload.expected_version = selectedNote.version;
      void changeNote("/" + encodeURIComponent(selectedNote.id), "PATCH", payload, "Note updated.");
    } else {
      void changeNote("", "POST", payload, "Note created.");
    }
  });
  view.addEventListener("change", () => loadNotes());
  refresh.addEventListener("click", () => loadNotes());
  more.addEventListener("click", () => loadNotes(true));

  return {
    clear,
    show(workspaceId, csrf, canWrite) {
      context = { path: "workspaces/" + encodeURIComponent(workspaceId) + "/notes", csrf, canWrite };
      void loadNotes();
    },
  };
}
