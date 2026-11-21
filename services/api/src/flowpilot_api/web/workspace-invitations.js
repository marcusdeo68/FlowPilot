"use strict";

function createWorkspaceInvitations({ request, expired, lockNavigation, registered, refreshWorkspace }) {
  const profile = document.querySelector("#invitation-profile");
  const userId = document.querySelector("#invitation-user-id");
  const register = document.querySelector("#register-profile");
  const refresh = document.querySelector("#refresh-invitations");
  const incoming = document.querySelector("#incoming-invitations");
  const status = document.querySelector("#invitation-status");
  const feedback = document.querySelector("#invitation-feedback");
  const labels = { owner: "Owner", member: "Member", observer: "Observer" };
  let canWrite = false;
  let saving = false;
  let generation = 0;

  function setSaving(value) {
    saving = value;
    register.disabled = refresh.disabled = incoming.inert = value;
    lockNavigation(value);
  }

  function clear() {
    generation += 1;
    canWrite = false;
    profile.hidden = register.hidden = refresh.hidden = incoming.hidden = true;
    userId.textContent = status.textContent = feedback.textContent = "";
    incoming.replaceChildren();
    setSaving(false);
  }

  function render(invitation) {
    const row = document.createElement("li");
    const name = document.createElement("strong");
    const details = document.createElement("span");
    name.textContent = invitation.workspace_name;
    details.textContent = `${labels[invitation.role]} · Expires ${new Date(invitation.expires_at).toLocaleString()}`;
    row.append(name, details);
    if (canWrite) {
      const actions = document.createElement("div");
      actions.className = "actions";
      for (const decision of ["accept", "decline"]) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = decision === "accept" ? "Accept invitation" : "Decline invitation";
        button.addEventListener("click", () => void decide(invitation, decision));
        actions.append(button);
      }
      row.append(actions);
    }
    return row;
  }

  async function load() {
    if (profile.hidden || saving) return;
    const version = ++generation;
    refresh.disabled = true;
    incoming.hidden = true;
    incoming.replaceChildren();
    status.textContent = "Loading invitations…";
    try {
      const invitations = await request("invitations?limit=20");
      if (version !== generation) return;
      incoming.replaceChildren(...invitations.map(render));
      incoming.hidden = invitations.length === 0;
      status.textContent = invitations.length === 20 ? "Showing up to 20 pending invitations."
        : invitations.length ? "" : "No pending invitations.";
    } catch (failure) {
      if (version !== generation || expired(failure)) return;
      status.textContent = "Could not load invitations. Try refreshing.";
    } finally {
      if (version === generation) refresh.disabled = false;
    }
  }

  async function decide(invitation, decision) {
    if (!canWrite || saving || incoming.hidden) return;
    const version = ++generation;
    setSaving(true);
    feedback.textContent = "Submitting decision…";
    let result;
    try {
      result = await request("invitations/" + encodeURIComponent(invitation.id) + "/decision", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, expected_version: invitation.version }),
      });
    } catch (failure) {
      if (version !== generation || expired(failure)) return;
      setSaving(false);
      refreshWorkspace(undefined, failure === 409 || failure === 404
        ? "This invitation changed or is no longer available."
        : "Could not confirm the decision. Check your invitations and workspaces.");
      return;
    }
    if (version !== generation) return;
    setSaving(false);
    if (decision === "accept") refreshWorkspace(result.workspace_id, "Invitation accepted.");
    else {
      feedback.textContent = "Invitation declined.";
      void load();
    }
  }

  register.addEventListener("click", async () => {
    if (!canWrite || saving || register.hidden) return;
    const version = ++generation;
    setSaving(true);
    feedback.textContent = "Registering profile…";
    try {
      const profile = await request("me", { method: "POST" });
      if (version !== generation) return;
      setSaving(false);
      registered(profile.id);
      feedback.textContent = "Profile registered.";
    } catch (failure) {
      if (version !== generation || expired(failure)) return;
      setSaving(false);
      feedback.textContent = "Could not register your profile. Try again.";
    }
  });

  refresh.addEventListener("click", () => void load());
  return {
    clear,
    show(id, write, unregistered = false) {
      canWrite = write;
      if (id) {
        userId.textContent = id;
        profile.hidden = refresh.hidden = false;
        register.hidden = true;
        void load();
      } else {
        register.hidden = !unregistered || !canWrite;
        status.textContent = !unregistered ? "Refresh workspaces to check your profile."
          : canWrite ? "Register and share your user ID to receive invitations."
            : "A write-enabled session is required to register.";
      }
    },
    showFeedback(message) { feedback.textContent = message; },
  };
}
