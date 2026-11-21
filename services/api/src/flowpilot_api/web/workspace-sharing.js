"use strict";

function createWorkspaceSharing({ request, expired, context, syncControls, reload, deny, offerReload }) {
  const form = document.querySelector("#share-preview");
  const heading = document.querySelector("#share-heading");
  const details = document.querySelector("#share-details");
  const workspace = document.querySelector("#share-workspace");
  const fields = document.querySelector("#share-fields");
  const evidencePanel = document.querySelector("#share-evidence-panel");
  const evidence = document.querySelector("#share-evidence");
  const confirm = document.querySelector("#confirm-share");
  const close = document.querySelector("#close-share");
  const feedback = document.querySelector("#share-feedback");
  let generation = 0;
  let version;
  let path;
  let workspacePath;
  let opener;
  let paused = false;

  function dismiss() {
    generation += 1;
    form.hidden = details.hidden = evidencePanel.hidden = true;
    confirm.disabled = true;
    close.disabled = false;
    fields.replaceChildren();
    evidence.replaceChildren();
    workspace.textContent = "";
    version = path = workspacePath = opener = undefined;
    syncControls();
  }

  function clear() {
    feedback.textContent = "";
    paused = false;
    dismiss();
  }

  function render(data, projections) {
    const rows = [
      ["Type", data.kind], ["Title", data.title],
      ["Description", data.description ?? "None"], ["Status", data.status],
    ];
    if (data.kind === "event") rows.push(
      ["Start", data.starts_at], ["End", data.ends_at], ["Time zone", data.time_zone],
    );
    else rows.push(["Due date", data.due_date ?? "None"]);
    for (const [label, value] of rows) {
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = label;
      description.textContent = value;
      fields.append(term, description);
    }
    for (const projection of projections) {
      const row = document.createElement("li");
      row.textContent = projection.summary;
      if (projection.excerpt !== undefined) {
        const excerpt = document.createElement("p");
        excerpt.textContent = projection.excerpt;
        row.append(excerpt);
      }
      evidence.append(row);
    }
    evidencePanel.hidden = projections.length === 0;
    details.hidden = false;
  }

  async function open(id, button) {
    const current = context();
    if (!current || !form.hidden || paused) return;
    const active = ++generation;
    workspacePath = current.path;
    path = workspacePath + "/work/" + encodeURIComponent(id);
    opener = button;
    workspace.textContent = current.name;
    form.hidden = false;
    feedback.textContent = "Loading sharing review…";
    syncControls();
    heading.focus();
    try {
      const preview = await request(path + "/share-preview");
      if (active !== generation) return;
      render(preview.item.data, preview.evidence);
      version = preview.item.version;
      confirm.disabled = false;
      feedback.textContent = "";
    } catch (failure) {
      if (active !== generation || expired(failure)) return;
      if (failure === 403 || failure === 404) deny(failure);
      else if (failure === 409) requireRefresh("This item changed. Close the review and refresh the work list.");
      else feedback.textContent = "Could not load the review. Close it and try again.";
    }
  }

  function requireRefresh(message) {
    paused = true;
    feedback.textContent = message;
    offerReload();
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (form.hidden || confirm.disabled || context()?.path !== workspacePath) return;
    const active = generation;
    confirm.disabled = close.disabled = true;
    feedback.textContent = "Sharing work…";
    try {
      await request(path + "/share", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_version: version }),
      });
      if (active === generation) reload("Work shared with the workspace.");
    } catch (failure) {
      if (active !== generation || expired(failure)) return;
      if (failure === 403 || failure === 404) deny(failure);
      else requireRefresh(failure === 409
        ? "This item changed. Close the review and refresh the work list."
        : "Could not confirm sharing. Close the review and check the work list before trying again.");
    } finally {
      if (active === generation) close.disabled = false;
    }
  });

  close.addEventListener("click", () => {
    const target = opener;
    dismiss();
    if (!paused) feedback.textContent = "";
    if (target?.isConnected) (paused ? document.querySelector("#retry-work") : target).focus();
  });

  return {
    clear, open, locked: () => !form.hidden, paused: () => paused,
    showFeedback(message) { feedback.textContent = message; },
  };
}
