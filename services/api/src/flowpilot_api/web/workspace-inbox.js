"use strict";

function createWorkspaceInbox({ request, expired, openWork, lockWorkNavigation, denyWrites }) {
  const addSource = document.querySelector("#add-source");
  const refresh = document.querySelector("#refresh-inbox");
  const sourceForm = document.querySelector("#source-form");
  const sourceFields = document.querySelector("#source-fields");
  const reference = document.querySelector("#source-reference");
  const summary = document.querySelector("#source-summary");
  const excerpt = document.querySelector("#source-excerpt");
  const closeSourceForm = document.querySelector("#close-source-form");
  const feedback = document.querySelector("#inbox-feedback");
  const listStatus = document.querySelector("#inbox-status");
  const list = document.querySelector("#source-items");
  const more = document.querySelector("#more-sources");
  const detail = document.querySelector("#source-detail");
  const detailHeading = document.querySelector("#source-detail-heading");
  const loading = document.querySelector("#source-loading");
  const preview = document.querySelector("#source-preview");
  const previewFields = {
    summary: document.querySelector("#preview-summary"),
    reference: document.querySelector("#preview-reference"),
    excerpt: document.querySelector("#preview-excerpt"),
  };
  const state = document.querySelector("#proposal-state");
  const proposalForm = document.querySelector("#proposal-form");
  const title = document.querySelector("#proposal-title");
  const dueDate = document.querySelector("#proposal-due-date");
  const actions = document.querySelector("#proposal-actions");
  const save = document.querySelector("#save-proposal");
  const accept = document.querySelector("#accept-proposal");
  const dismiss = document.querySelector("#dismiss-proposal");
  const hint = document.querySelector("#proposal-draft-hint");
  const suggest = document.querySelector("#suggest-task");
  const reloadSource = document.querySelector("#reload-source");
  const returnToWork = document.querySelector("#return-to-work");
  const closeDetailButton = document.querySelector("#close-source-detail");
  const proposalFeedback = document.querySelector("#proposal-feedback");
  const statusLabels = {
    pending_review: "Pending review",
    accepted: "Accepted",
    dismissed: "Dismissed",
  };

  let context;
  let listRequest;
  let nextCursor;
  let opened;
  let saving = false;
  let sourceNeedsRefresh = false;

  function setSaving(value) {
    saving = value;
    lockWorkNavigation(value);
  }

  function write(active, path, method, payload) {
    return request(active.base + path, {
      method,
      headers: { "Content-Type": "application/json", "X-CSRF-Token": active.csrf },
      body: JSON.stringify(payload),
    });
  }

  function proposedFields() {
    return {
      title: title.value === opened.displayTitle ? opened.proposal.title : title.value.trim(),
      due_date: dueDate.value || null,
    };
  }

  function hasChanges() {
    if (!opened?.proposal) return false;
    const draft = proposedFields();
    return draft.title !== opened.proposal.title || draft.due_date !== opened.proposal.due_date;
  }

  function syncControls() {
    const stale = Boolean(opened?.needsReload);
    const canReview = Boolean(context?.canWrite && opened?.proposal?.state === "pending_review");
    const dirty = canReview && hasChanges();
    const invalidDate = canReview && dueDate.validity.badInput;
    sourceFields.disabled = saving || sourceNeedsRefresh;
    closeSourceForm.disabled = refresh.disabled = closeDetailButton.disabled = saving;
    addSource.disabled = saving || !sourceForm.hidden;
    more.disabled = saving || Boolean(listRequest);
    for (const button of list.querySelectorAll("button")) button.disabled = saving;
    actions.hidden = !canReview;
    title.readOnly = dueDate.readOnly = saving || stale || !canReview;
    save.disabled = saving || stale || invalidDate || !dirty;
    accept.disabled = dismiss.disabled = saving || stale || invalidDate || dirty;
    suggest.disabled = reloadSource.disabled = returnToWork.disabled = saving;
    if (stale) hint.textContent = "";
    else if (invalidDate) hint.textContent = "Enter a complete due date.";
    else hint.textContent = dirty ? "Save your changes before reviewing this suggestion." : "";
  }

  function closeDetail() {
    opened = undefined;
    detail.hidden = preview.hidden = proposalForm.hidden = true;
    suggest.hidden = reloadSource.hidden = returnToWork.hidden = true;
    loading.textContent = state.textContent = proposalFeedback.textContent = "";
    for (const field of Object.values(previewFields)) field.textContent = "";
    proposalForm.reset();
    syncControls();
  }

  function clear() {
    context = listRequest = nextCursor = undefined;
    setSaving(false);
    sourceNeedsRefresh = false;
    sourceForm.reset();
    sourceForm.hidden = addSource.hidden = more.hidden = true;
    feedback.textContent = listStatus.textContent = "";
    list.replaceChildren();
    closeDetail();
  }

  function showForbidden(active) {
    clear();
    // The workspace list must supply a fresh role before showing write controls again.
    denyWrites();
    context = { ...active, canWrite: false };
    listStatus.textContent = "Inbox access changed. Refresh the inbox to browse or refresh workspaces before writing.";
  }

  function forgetSource(source) {
    source.button.closest("li").remove();
    closeDetail();
    listStatus.textContent = "This source or suggestion is unavailable. Refresh the inbox.";
  }

  function renderSource(entry) {
    const row = document.createElement("li");
    const button = document.createElement("button");
    const badge = document.createElement("span");
    const source = { entry, button, badge };
    button.type = "button";
    button.textContent = entry.summary;
    const date = document.createElement("time");
    date.dateTime = entry.created_at;
    date.textContent = new Date(entry.created_at).toLocaleDateString();
    badge.textContent = statusLabels[entry.review?.state] ?? "No suggestion";
    button.addEventListener("click", () => openSource(source));
    row.append(button, badge, date);
    return row;
  }

  async function loadInbox(append = false, savedMessage = "") {
    const active = context;
    if (!active || saving || (append && (!nextCursor || listRequest))) return;
    const token = {};
    listRequest = token;
    const query = new URLSearchParams({ limit: "20" });
    if (append) query.set("after", nextCursor);
    else {
      closeDetail();
      nextCursor = undefined;
      list.replaceChildren();
      addSource.hidden = more.hidden = true;
      if (savedMessage) feedback.textContent = savedMessage;
    }
    listStatus.textContent = "Loading sources…";
    syncControls();
    try {
      const page = await request(active.base + "/sources?" + query);
      if (context !== active || listRequest !== token) return;
      list.append(...page.items.map(renderSource));
      nextCursor = page.next_after;
      addSource.hidden = !active.canWrite;
      more.hidden = !nextCursor;
      listStatus.textContent = list.childElementCount ? "" : "No sources yet.";
      if (!append && sourceNeedsRefresh) {
        sourceNeedsRefresh = false;
        feedback.textContent = "Inbox refreshed. Check for this source before saving again.";
      }
    } catch (status) {
      if (context !== active || listRequest !== token || expired(status)) return;
      if (status === 403) {
        showForbidden(active);
      } else if (append && status === 404) {
        more.hidden = true;
        nextCursor = undefined;
        listStatus.textContent = "Refresh the inbox to continue browsing sources.";
      } else {
        listStatus.textContent = "Could not load sources. Refresh the inbox to try again.";
      }
    } finally {
      if (context === active && listRequest === token) {
        listRequest = undefined;
        syncControls();
      }
    }
  }

  function renderProposal(selection, proposal) {
    selection.proposal = proposal;
    selection.needsReload = false;
    reloadSource.hidden = true;
    proposalForm.hidden = !proposal;
    suggest.hidden = Boolean(proposal) || !context.canWrite;
    returnToWork.hidden = proposal?.state !== "accepted";
    state.textContent = statusLabels[proposal?.state] ?? "No suggestion yet.";
    if (proposal) {
      selection.source.entry.review = { id: proposal.id, state: proposal.state };
      selection.source.badge.textContent = state.textContent;
      title.value = proposal.title;
      selection.displayTitle = title.value;
      dueDate.value = proposal.due_date ?? "";
    }
    syncControls();
  }

  async function openSource(source) {
    const active = context;
    if (!active || saving || !source.button.isConnected) return;
    closeDetail();
    const selection = { source };
    opened = selection;
    detail.hidden = false;
    detailHeading.focus();
    loading.textContent = "Loading source details…";
    try {
      const sourcePath = "/sources/" + encodeURIComponent(source.entry.id);
      const data = await request(active.base + sourcePath);
      if (context !== active || opened !== selection) return;
      const review = source.entry.review;
      const proposal = review
        ? await request(active.base + "/proposals/" + encodeURIComponent(review.id))
        : undefined;
      if (context !== active || opened !== selection) return;
      for (const [field, element] of Object.entries(previewFields)) element.textContent = data[field];
      preview.hidden = false;
      loading.textContent = "";
      renderProposal(selection, proposal);
    } catch (status) {
      if (context !== active || opened !== selection || expired(status)) return;
      if (status === 403) showForbidden(active);
      else if (status === 404) forgetSource(source);
      else {
        loading.textContent = "Could not load source details.";
        reloadSource.hidden = false;
      }
    }
  }

  async function changeProposal(operation) {
    const active = context;
    const selection = opened;
    if (!active?.canWrite || !selection || selection.needsReload || saving) return;
    const current = selection.proposal;
    let path, method, payload;
    if (operation === "suggest") {
      if (suggest.hidden) return;
      path = "/sources/" + encodeURIComponent(selection.source.entry.id) + "/task-proposal";
      method = "PUT";
    } else {
      if (current?.state !== "pending_review" || dueDate.validity.badInput) return;
      const correcting = operation === "correct";
      if (hasChanges() !== correcting) return;
      path = "/proposals/" + encodeURIComponent(current.id) + (correcting ? "" : "/review");
      method = correcting ? "PATCH" : "POST";
      payload = { expected_version: current.version };
      if (correcting) {
        const draft = proposedFields();
        if (!draft.title) {
          proposalFeedback.textContent = "Enter a task title.";
          return;
        }
        Object.assign(payload, draft);
      } else {
        if (operation === "dismiss" && !window.confirm("Dismiss this suggestion?")) return;
        payload.decision = operation;
      }
    }
    setSaving(true);
    syncControls();
    proposalFeedback.textContent = "Saving suggestion…";
    try {
      const proposal = await write(active, path, method, payload);
      if (context !== active || opened !== selection) return;
      renderProposal(selection, proposal);
      proposalFeedback.textContent = {
        suggest: "Suggestion loaded.",
        correct: "Suggestion changes saved.",
        accept: "Private task created.",
        dismiss: "Suggestion dismissed.",
      }[operation];
    } catch (status) {
      if (context !== active || opened !== selection || expired(status)) return;
      if (status === 403) showForbidden(active);
      else if (status === 404) forgetSource(selection.source);
      else if (status === 422) {
        proposalFeedback.textContent = "Check the suggestion title and due date.";
      } else if (operation === "suggest") {
        proposalFeedback.textContent = "Could not confirm the suggestion. Use Suggest task to check again.";
      } else {
        selection.needsReload = true;
        reloadSource.hidden = false;
        proposalFeedback.textContent = status === 409
          ? "The suggestion changed. Reload its details before reviewing it again."
          : "Could not confirm the decision. Reload the source details to check its saved state.";
      }
    } finally {
      if (context === active) {
        setSaving(false);
        syncControls();
      }
    }
  }

  addSource.addEventListener("click", () => {
    sourceForm.hidden = false;
    syncControls();
    reference.focus();
  });
  closeSourceForm.addEventListener("click", () => {
    sourceForm.hidden = true;
    if (!sourceNeedsRefresh) sourceForm.reset();
    syncControls();
    addSource.focus();
  });
  sourceForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const active = context;
    if (!active?.canWrite || sourceForm.hidden || saving || sourceNeedsRefresh) return;
    const payload = {
      reference: reference.value.trim(),
      summary: summary.value.trim(),
      excerpt: excerpt.value.trim(),
    };
    if (Object.values(payload).some(value => !value)) {
      feedback.textContent = "Enter a reference, summary, and excerpt.";
      return;
    }
    setSaving(true);
    syncControls();
    feedback.textContent = "Saving source…";
    try {
      await write(active, "/sources", "POST", payload);
      if (context !== active) return;
      setSaving(false);
      sourceForm.reset();
      sourceForm.hidden = true;
      void loadInbox(false, "Source saved.");
    } catch (status) {
      if (context !== active || expired(status)) return;
      if (status === 403 || status === 404) showForbidden(active);
      else if (status === 422) feedback.textContent = "Check the reference, summary, and excerpt.";
      else {
        sourceNeedsRefresh = true;
        feedback.textContent = status === 409
          ? "That reference may already be in use. Refresh the inbox to check."
          : "Could not confirm the source was saved. Refresh the inbox to check before trying again.";
      }
    } finally {
      if (context === active) {
        setSaving(false);
        syncControls();
      }
    }
  });

  proposalForm.addEventListener("input", syncControls);
  // A segmented date can change its validation state without changing its value.
  dueDate.addEventListener("keyup", syncControls);
  dueDate.addEventListener("blur", syncControls);
  proposalForm.addEventListener("submit", event => {
    event.preventDefault();
    void changeProposal("correct");
  });
  accept.addEventListener("click", () => changeProposal("accept"));
  dismiss.addEventListener("click", () => changeProposal("dismiss"));
  suggest.addEventListener("click", () => changeProposal("suggest"));
  reloadSource.addEventListener("click", () => opened && openSource(opened.source));
  closeDetailButton.addEventListener("click", () => {
    const button = opened?.source.button;
    closeDetail();
    button?.focus();
  });
  refresh.addEventListener("click", () => loadInbox());
  more.addEventListener("click", () => loadInbox(true));
  returnToWork.addEventListener("click", openWork);

  return {
    clear,
    show(workspaceId, csrf, canWrite) {
      context = { base: "workspaces/" + encodeURIComponent(workspaceId), csrf, canWrite };
      void loadInbox();
    },
  };
}
