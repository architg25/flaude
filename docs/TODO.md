# TODO

## Customisable session sort order

The session table currently sorts by status priority (waiting > error > new > running > idle > ended), then by start time. Allow users to customise this.

**Ideas:**

- Keybind to cycle sort modes (e.g. by status, by project, by uptime, by context usage)
- Click column headers to sort (Textual DataTable may support this)
- Persist sort preference in config.yaml
- Secondary sort key (e.g. sort by project, then by status within each project)

## Improve notification system

The current notification system is basic — terminal bell, macOS notification, and system sound with a single timer threshold. Needs improvement to be more useful for multi-session monitoring.

**Ideas:**

- Per-session notification preferences (some sessions are background tasks, some need immediate attention)
- Notification on status change (e.g. session goes from RUNNING to IDLE, or enters WAITING_PERMISSION)
- Notification on error (session hits ERROR status)
- Notification when context usage exceeds a threshold (e.g. 80% of model limit)
- Notification grouping — batch multiple session alerts instead of firing one per session
- Custom sounds per notification type
- Slack/webhook integration for remote monitoring
- Notification history — show recent alerts in the TUI so you know what you missed

## Monorepo support

The Project column shows the cwd basename, which for monorepos is the repo root (e.g. `services-pilot`) even when you're working in a sub-directory. Multiple sessions in the same monorepo all show the same project name with no way to distinguish them.

**What needs to change:**

- Detect when cwd is a monorepo root (e.g. contains multiple service directories, or has a workspace config like `pom.xml`, `package.json` with workspaces, `BUILD`)
- Show the sub-directory path relative to the repo root, e.g. `services-pilot/auth-service` instead of just `services-pilot`
- Or detect the git root and show `repo/subdir` when the session's cwd is deeper than the repo root
- Detail panel should show both the repo name and the sub-path for clarity

## ~~Kill session from dashboard (d key)~~ — DONE

Sends `/exit` to the session's iTerm2 terminal via AppleScript (same mechanism as prompt sending).

- `d` keybind → confirmation dialog → `send_text_to_session(tty, "/exit")`
- Requires: session is IDLE or NEW, iTerm2, has tty
- Only works for iTerm2 (has per-session AppleScript API with TTY matching)
- Ghostty/Warp/Terminal lack a way to target a specific tab by TTY — would need navigate-then-keystroke which risks hitting the wrong tab

## Permission management from dashboard

Approve or deny permission prompts directly from the Flaude dashboard, while still allowing the user to respond in the Claude terminal as usual.

**Problem:** Claude Code's `PreToolUse` hook expects a single synchronous response (allow/deny JSON on stdout). If Flaude's hook blocks waiting for dashboard input, but the user also approves in their terminal, there's a race condition — two responses to the same prompt. The hook must return before Claude Code proceeds, so blocking the hook while waiting for dashboard input would freeze the Claude session.

**Why we went monitor-only:** The current architecture deliberately avoids this. Hooks write state and exit immediately. The dashboard displays pending permissions but doesn't act on them. This guarantees hooks never block Claude Code.

**Possible approaches:**

- Hook writes a "pending" file and blocks with a short poll loop; dashboard writes an "approved/denied" file; hook reads it and responds. Risk: if user approves in terminal first, the hook's response is ignored but the poll loop still runs until timeout.
- Wait for Claude Code to support an async permission API or a way to programmatically respond to prompts from outside the session.
- Use the hook's timeout as a natural fallback — if no dashboard response within N seconds, allow the user's terminal response to take over. Requires careful coordination to avoid double-responses.

## Agent team visibility

Surface Claude Code agent teams (spawned via `TeamCreate` / `Agent` tool) in the dashboard so you can see what a session's subagents are doing.

**Problem:** When Claude spawns a team of agents, each subagent runs in a separate process but only the parent session fires hook events. Flaude has `subagent_count` (decremented on `SubagentStop`) but no visibility into what each subagent is working on, its status, or its task list.

**Ideas:**

- Show subagent count as a badge/indicator on the session row (e.g. `WORKING [3]`)
- Expand a session row to show its active subagents as nested sub-rows
- Track subagent names/types from `SubagentStop` events (event payload may contain agent metadata)
- Read the team task list files (`~/.claude/tasks/<team-name>/`) to show task progress
- Read the team config (`~/.claude/teams/<team-name>/config.json`) to discover team members and their roles
- Detail panel section showing team overview: member names, assigned tasks, completion status
- Investigate whether `PreToolUse`/`PostToolUse` events fire for subagent tool calls (they may only fire for the parent session)

## Nested groups

Support groups within groups — e.g. a "backend" group containing "auth-service" and "payment-service" sub-groups.

**Current state:** Sessions can be grouped by git repo (auto) or manually assigned to a flat named group. Groups cannot contain other groups.

**Ideas:**

- Use a path-like syntax for group names (e.g. `backend/auth-service`) to imply hierarchy
- Render nested groups with indentation in the table (similar to how team members are indented under their lead)
- Collapsible group headers — expand/collapse a parent group to show/hide its children
- Allow drag-and-drop (via keybindings) to move a group under another group
- Config format: `session_groups` values could use `/` as a nesting separator, or a separate `group_hierarchy` config section
