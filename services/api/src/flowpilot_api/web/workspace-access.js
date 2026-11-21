"use strict";

function createWorkspaceAccess({ request, expired, lockNavigation, deny, refreshContext }) {
  const profile = document.querySelector("#access-profile");
  const ownRole = document.querySelector("#access-role");
  const ownId = document.querySelector("#access-user-id");
  const admin = document.querySelector("#access-admin");
  const roster = document.querySelector("#workspace-members");
  const history = document.querySelector("#access-history");
  const memberLimit = document.querySelector("#member-limit");
  const historyLimit = document.querySelector("#history-limit");
  const form = document.querySelector("#grant-access");
  const grantId = document.querySelector("#grant-user-id");
  const grantRole = document.querySelector("#grant-role");
  const refresh = document.querySelector("#refresh-access");
  const feedback = document.querySelector("#access-feedback");
  const status = document.querySelector("#access-status");
  const labels = { owner: "Owner", member: "Member", observer: "Observer" };
  const operationLabels = {
    workspace_created: "Workspace created", member_added: "Access granted",
    membership_changed: "Membership changed",
  };
  let context;
  let generation = 0;
  let saving = false;

  function setSaving(value) {
    saving = value;
    admin.inert = value;
    refresh.disabled = value;
    lockNavigation(value);
  }

  function clearAdmin() {
    admin.hidden = form.hidden = true;
    roster.replaceChildren();
    history.replaceChildren();
    form.reset();
  }

  function clear() {
    generation += 1;
    context = undefined;
    profile.hidden = refresh.hidden = true;
    ownRole.textContent = ownId.textContent = status.textContent = feedback.textContent = "";
    clearAdmin();
    setSaving(false);
  }

  function unavailable() {
    generation += 1;
    context = undefined;
    profile.hidden = refresh.hidden = true;
    ownRole.textContent = ownId.textContent = "";
    clearAdmin();
    deny();
    status.textContent = "Access details are unavailable. Refresh workspaces to check your role.";
  }

  function describe(role, active) {
    return labels[role] + " · " + (active ? "Active" : "Inactive");
  }

  function renderMember(member) {
    const row = document.createElement("li");
    const title = document.createElement("strong");
    const detail = document.createElement("span");
    const own = member.user_id === context.id;
    title.textContent = member.user_id + (own ? " (you)" : "");
    detail.textContent = describe(member.role, member.active);
    row.append(title, detail);
    if (!context.canWrite) return row;
    const actions = document.createElement("div");
    actions.className = "actions";
    if (member.active) {
      const role = document.createElement("select");
      role.setAttribute("aria-label", "Role for " + member.user_id);
      role.append(...Object.entries(labels).map(([value, label]) => new Option(label, value)));
      role.value = member.role;
      const change = document.createElement("button");
      change.type = "button";
      change.textContent = "Save role";
      change.disabled = true;
      role.addEventListener("change", () => { change.disabled = role.value === member.role; });
      change.addEventListener("click", () => updateMember(member, role.value, true));
      actions.append(role, change);
    }
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.textContent = member.active ? "Remove access" : "Reactivate access";
    toggle.addEventListener("click", () => {
      if (own && member.active && !window.confirm("Remove your own access to this workspace?")) return;
      updateMember(member, member.role, !member.active);
    });
    actions.append(toggle);
    row.append(actions);
    return row;
  }

  function renderChange(change) {
    const row = document.createElement("li");
    const name = document.createElement("strong");
    const details = document.createElement("span");
    const when = document.createElement("time");
    name.textContent = operationLabels[change.operation];
    details.textContent = `${change.target_id} · ${describe(change.to_role, change.to_active)} · version ${change.membership_version}`;
    if (change.from_role) details.textContent += ` · previously ${describe(change.from_role, change.from_active)}`;
    const actor = document.createElement("span");
    actor.textContent = "Changed by " + change.actor_id;
    when.dateTime = change.created_at;
    when.textContent = new Date(change.created_at).toLocaleString();
    row.append(name, details, actor, when);
    return row;
  }

  async function load(message = "") {
    if (context?.role !== "owner" || saving) return;
    const version = ++generation;
    const path = context.path;
    clearAdmin();
    refresh.disabled = true;
    feedback.textContent = message;
    status.textContent = "Loading access details…";
    try {
      const [members, changes] = await Promise.all([
        request(path + "/members?limit=100"),
        request(path + "/membership-history?limit=20"),
      ]);
      if (version !== generation) return;
      roster.replaceChildren(...members.map(renderMember));
      history.replaceChildren(...changes.map(renderChange));
      memberLimit.hidden = members.length < 100;
      historyLimit.hidden = changes.length < 20;
      form.hidden = !context.canWrite;
      admin.hidden = false;
      status.textContent = "";
    } catch (failure) {
      if (version !== generation || expired(failure)) return;
      if (failure === 403 || failure === 404) unavailable();
      else status.textContent = "Could not load access details. Try refreshing.";
    } finally {
      if (version === generation) refresh.disabled = false;
    }
  }

  async function write(path, method, command, message, own = false) {
    if (context?.role !== "owner" || !context.canWrite || saving || admin.hidden) return;
    const version = ++generation;
    setSaving(true);
    feedback.textContent = "Saving access change…";
    let detail;
    let member;
    try {
      member = await request(context.path + path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(command),
      }, value => { detail = value; });
    } catch (failure) {
      if (version !== generation || expired(failure)) return;
      setSaving(false);
      if (failure === 403) {
        feedback.textContent = "Access change was denied.";
        unavailable();
        return;
      }
      if (failure === 404 && method === "POST") {
        feedback.textContent = "No registered user was found for that ID.";
        return;
      }
      if (failure === 422) {
        feedback.textContent = "Check the registered user ID and role.";
        return;
      }
      const notice = detail === "Workspace must keep at least one active owner"
        ? "Keep at least one active owner. Grant ownership to another member before removing or demoting the last owner."
        : failure === 409 ? "Membership changed or already exists. Review the current access details."
          : "Could not confirm the access change. Review the current access details before trying again.";
      if (own) refreshContext(notice);
      else void load(notice);
      return;
    }
    if (version !== generation) return;
    setSaving(false);
    if (own) refreshContext(message, member);
    else void load(message);
  }

  function updateMember(member, role, active) {
    const message = member.active === active ? "Role changed."
      : active ? "Access reactivated." : "Access removed.";
    void write("/members/" + encodeURIComponent(member.user_id), "PATCH", {
      role, active, expected_version: member.version,
    }, message, member.user_id === context?.id);
  }

  refresh.addEventListener("click", () => void load());
  form.addEventListener("submit", event => {
    event.preventDefault();
    const id = grantId.value.trim();
    if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) {
      feedback.textContent = "Enter the user ID shared by the registered user.";
      return;
    }
    void write("/members", "POST", { user_id: id, role: grantRole.value }, "Access granted.");
  });

  return {
    clear,
    show(current) {
      context = current;
      if (!current.id || !current.role) {
        status.textContent = "Refresh workspaces to check your role and user ID.";
        return;
      }
      profile.hidden = false;
      ownRole.textContent = labels[current.role];
      ownId.textContent = current.id;
      refresh.hidden = current.role !== "owner";
      void load();
    },
    showFeedback(message) { feedback.textContent = message; },
  };
}
