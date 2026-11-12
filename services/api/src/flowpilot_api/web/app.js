const taskList = document.querySelector("#task-list");
const dialog = document.querySelector("#task-dialog");
const form = document.querySelector("#task-form");
const toast = document.querySelector("#toast");
const today = new Date();
const todayLabel = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" });
document.querySelector("#today-date").textContent = todayLabel.format(today);
document.querySelector(".welcome-row .eyebrow").textContent = today
  .toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }).toUpperCase();
document.querySelectorAll(".event-row[data-day-offset]").forEach((event) => {
  const date = new Date();
  date.setDate(date.getDate() + Number(event.dataset.dayOffset));
  event.querySelector(".event-date strong").textContent = String(date.getDate()).padStart(2, "0");
  event.querySelector(".event-date small").textContent = new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(date).toUpperCase();
});

const sampleTasks = [
  { id: "sample-1", title: "Send revised project timeline", owner_name: "Marcus", due_date: localDate(0), priority: "high", status: "active" },
  { id: "sample-2", title: "Review campaign launch assets", owner_name: "Priya S.", due_date: localDate(1), priority: "normal", status: "active" },
  { id: "sample-3", title: "Share notes from the planning session", owner_name: "Marcus", due_date: localDate(2), priority: "normal", status: "active" },
];
let tasks = [];

function localDate(offset) {
  const date = new Date();
  date.setDate(date.getDate() + offset);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDueDate(value) {
  if (!value) return "No due date";
  const date = new Date(`${value}T12:00:00`);
  if (value === localDate(0)) return "Due today";
  if (value === localDate(1)) return "Due tomorrow";
  return `Due ${new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date)}`;
}

function createTaskRow(task, index) {
  const row = document.createElement("article");
  row.className = "task-row";
  if (task.status === "completed") row.classList.add("done");

  const checkbox = document.createElement("input");
  checkbox.className = "task-check";
  checkbox.type = "checkbox";
  checkbox.checked = task.status === "completed";
  const completionPaths = {
    detected: ["confirmed", "active", "completed"],
    confirmed: ["active", "completed"],
    active: ["completed"],
    blocked: ["active", "completed"],
    disputed: ["confirmed", "active", "completed"],
  };
  checkbox.disabled = task.id.startsWith("sample-") || !completionPaths[task.status];
  checkbox.setAttribute("aria-label", `Mark ${task.title} complete`);

  const copy = document.createElement("div");
  copy.className = "task-copy";
  const title = document.createElement("strong");
  title.className = "task-title";
  title.textContent = task.title;
  const details = document.createElement("div");
  details.className = "task-detail";
  const due = document.createElement("span");
  due.textContent = formatDueDate(task.due_date);
  details.append(due);
  const priority = document.createElement("span");
  priority.className = `priority ${task.priority === "high" ? "high" : "normal"}`;
  priority.textContent = task.priority === "high" ? "HIGH PRIORITY" : "TASK";
  details.append(priority);
  if (task.owner_name) {
    const owner = document.createElement("span");
    owner.className = "task-owner";
    const avatar = document.createElement("span");
    avatar.className = "mini-avatar";
    avatar.textContent = task.owner_name.trim().slice(0, 1).toUpperCase();
    const name = document.createElement("span");
    name.textContent = task.owner_name;
    owner.append(avatar, name);
    details.append(owner);
  }
  copy.append(title, details);
  row.append(checkbox, copy);
  if (!task.id.startsWith("sample-")) {
    checkbox.addEventListener("change", () => transitionTask(task, row));
  }
  row.style.animationDelay = `${index * 35}ms`;
  return row;
}

function render() {
  taskList.replaceChildren();
  if (!tasks.length) {
    const empty = document.createElement("p");
    empty.className = "loading-row";
    empty.textContent = "No tasks yet. Add one to get started.";
    taskList.append(empty);
  } else {
    tasks.slice(0, 4).forEach((task, index) => taskList.append(createTaskRow(task, index)));
  }
  const todayCount = tasks.filter((task) => task.due_date === localDate(0) && !["completed", "canceled"].includes(task.status)).length;
  document.querySelector("#due-count").textContent = String(todayCount);
}

async function loadTasks() {
  try {
    const response = await fetch("/api/v1/commitments?limit=50", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("Could not load local tasks");
    const data = await response.json();
    tasks = data.items.length ? data.items : sampleTasks;
  } catch {
    tasks = sampleTasks;
    showToast("Showing sample tasks. Start the local API to save changes.");
  }
  render();
}

async function transitionTask(task, row) {
  const checkbox = row.querySelector(".task-check");
  checkbox.disabled = true;
  try {
    let state = task.status;
    let version = task.version;
    const path = `/api/v1/commitments/${encodeURIComponent(task.id)}/transitions`;
    const completionPaths = {
      detected: ["confirmed", "active", "completed"],
      confirmed: ["active", "completed"],
      active: ["completed"],
      blocked: ["active", "completed"],
      disputed: ["confirmed", "active", "completed"],
    };
    for (const target_status of completionPaths[state] || []) {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ target_status, expected_version: version }),
      });
      if (!response.ok) throw new Error("Task changed. Reload and try again.");
      const updated = await response.json();
      state = updated.status;
      version = updated.version;
    }
    await loadTasks();
    showToast("Task marked complete.");
  } catch (error) {
    checkbox.checked = false;
    checkbox.disabled = false;
    showToast(error.message || "Could not update task.");
  }
}

function openTaskDialog() {
  form.reset();
  dialog.showModal();
  document.querySelector("#task-title").focus();
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timeoutId);
  showToast.timeoutId = window.setTimeout(() => toast.classList.remove("show"), 3000);
}

document.querySelector("#new-task").addEventListener("click", openTaskDialog);
document.querySelector("#add-task").addEventListener("click", openTaskDialog);
document.querySelector("#view-all").addEventListener("click", () => showToast("The task workspace is coming in a later increment."));
document.querySelector("#review-draft").addEventListener("click", () => showToast("Draft review will be added with the approval workflow."));
form.addEventListener("submit", async (event) => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  const saveButton = document.querySelector("#save-task");
  saveButton.disabled = true;
  const payload = Object.fromEntries(new FormData(form));
  for (const field of ["owner_name", "due_date"]) if (!payload[field]) delete payload[field];
  try {
    const response = await fetch("/api/v1/commitments", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.detail || "Could not save this task.");
    }
    dialog.close();
    await loadTasks();
    showToast("Task saved in the local workspace.");
  } catch (error) {
    showToast(error.message || "Could not save this task.");
  } finally {
    saveButton.disabled = false;
  }
});

loadTasks();
