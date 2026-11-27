# Implementation 0038 — Workspace projects

In **Work items**, create a project and use **Project filter** to open it.
For example, create “Conference” and add “Reserve meeting room.” A new task
defaults to the selected project. Edit an existing task to move it or choose
**No project** to remove the assignment. Project filters combine with title,
task status, and work visibility in the paginated Work views.

Project names are visible to active workspace members. Members and owners
with write access can create projects. The task's creator can change its
assignment. Assigning a private task leaves it private. Sharing a task shows
its project name alongside the other fields the workspace will see.

The browser reads and adds names through the workspace's `GET /projects`
and `POST /projects` routes. Task creation accepts a project ID, and the
task details request can change it. The work-page and title search routes
apply the project ID before pagination.

PostgreSQL stores project creation in an append-only catalog with the actor
and timestamp. The database prevents duplicate names within a workspace,
compared without case, and a workspace-qualified foreign key limits
assignments to projects in the same workspace. The task-only constraint
keeps other work types out. Task updates set the project and details in the
same transaction, increment the task version, and append the existing
details-change audit event. A project change invalidates older sharing
reviews. An edit that omits the project field keeps the current assignment.

Apply `alembic upgrade head` before starting the updated workspace.
Migration `0010_workspace_projects` leaves existing tasks unassigned.
It blocks a downgrade if project records would be lost. The hosted
readiness check expects the new revision.

The PostgreSQL tests exercise workspace isolation, private visibility,
sharing version conflicts, and downgrade protection. Chromium covers the
create, assign, share-preview, and remove flow. Projects are create-only
in this increment. Renaming, archiving, and project summaries can be
designed after testing the grouping workflow.
