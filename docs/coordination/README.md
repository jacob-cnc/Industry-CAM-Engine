# Shared agent coordination

The live shared folder is `docs/coordination/` on GitHub branch `agent-sync`.
Copies on main and feature branches are bootstrap documentation; always fetch
the live branch. This is software-only coordination, with no machine changes.
GitHub is the transport between separate machines, not a shared local disk.

## Read before work

From your project checkout, before any repository work and again before making
edits, committing, integrating, or deploying:

```bash
git fetch origin agent-sync
git show origin/agent-sync:docs/coordination/README.md
git show origin/agent-sync:docs/coordination/codex.md
git show origin/agent-sync:docs/coordination/claude.md
```

Poll at least every five minutes during active work and after long commands.
No background polling is promised when an agent is idle or its session ends.
If fetch fails, do not start new changes or assume ownership is free. Preserve
local work and resolve access. Read-only investigation may continue.

## Publish status without disturbing the application checkout

Create a separate, ordinary coordination clone once (not a Git worktree):

```bash
git clone --single-branch --branch agent-sync https://github.com/jacob-cnc/Industry-CAM-Engine.git /tmp/industry-cam-agent-sync
```

Before each update, in that clone run `git pull --ff-only`. Edit only your own
status file, commit it, and `git push origin HEAD:agent-sync`. This clone is for
coordination only; never develop or deploy application code there. If the push
is rejected, fetch, rebase the coordination-only commit, reread both statuses,
resolve any ownership conflict, and retry. Never force-push. A failed push does
not establish a published claim. Only docs/coordination changes belong on this
branch. Never merge this branch wholesale into an application branch.

## Claim before implementing

Each agent owns its own status file. Include UTC update time, task, state,
application branch and base commit, exact paths or modules claimed, acceptance
criteria, test results, questions for the other agent, and handoff commit IDs.
Use states proposed, active, blocked, review-ready, or idle. Publish before
implementation, then fetch again and inspect the other agent's claim. Claims
are advisory coordination, not atomic filesystem locks. Overlapping claims
must be resolved by explicit agreement in both status files before either
agent edits the overlap. An old timestamp never automatically frees a claim.
If overlap is discovered mid-task, stop that scope and continue unrelated work.

Address messages to the other agent in your own file. The receiver acknowledges
them in its own file with the request's timestamp or commit. Publish checkpoints,
blockers, scope changes, and final results promptly. Release claimed paths when
done. Never treat silence as acknowledgement or deployment approval.

## Initial responsibilities

- Codex: offline dependencies, CAM/tests, software diagnosis, integration review.
- Claude: lathe runtime, HAL/INI, Mesa/I/O, machine-local state and commissioning.
- User: overall priorities and physical-machine observations.

These are proposed defaults, not authorization to begin an unrequested task.
Claude must publish its actual current task and claimed paths before Codex
starts overlapping work. Machine-control and motion changes retain all existing
AGENTS.md verification and commissioning requirements. Identify exact software
commits in handoffs; keep software verification separate from machine evidence.
Do not pull over dirty machine-local changes, overwrite offsets/tool tables,
or deploy from the coordination clone.

## Bootstrap limitation

A running agent must first discover these instructions by fetching the updated
main branch or reading this folder. Git cannot inject instructions into an
already-running Claude session. Until Claude acknowledges in claude.md, its
participation is unconfirmed; Codex must not assume its files are unclaimed.
