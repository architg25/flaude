# Changelog

## 0.12 — Git worktree support & repo grouping

### 0.12.5

- Fix repeated git subprocess calls on every hook event for non-repo directories
- Increase transcript tail read from 10KB to 50KB to catch usage data in larger responses
- Pre-compile regex patterns in rules engine
- Extract shared team config reader, removing duplication between dispatcher and scanner
- Add MultiEdit to Rust tool summarizer (parity fix)

### 0.12.4

- Configurable grouping — auto-group toggle and manual group assignment via `G` key
- Rename groups via Enter on group header row
- Auto-group toggle in settings panel

### 0.12.3

- Truncate long session names in Name column to 20 chars

### 0.12.2

- Smart truncation for Project column
- Show worktree path in detail panel

### 0.12.1

- Fix auto-hide NEW sessions after idle timeout

### 0.12.0

- Add git worktree support — repo grouping, branch display, worktree detection
- Rename repo groups via Enter on header row
- Sort sessions within repo groups, not globally
- Deduplicate repo header logic and extract shared constant
- Cache custom_title to avoid full transcript scan on every Stop

## 0.11 — Custom session titles

### 0.11.0

- Display custom session titles from `/rename`

## 0.10 — Agent teams & pipx fix

### 0.10.2

- Fix hook dispatcher failing when installed via pipx (#2)
- Flesh out demo activity logs to match tool_stats counts

### 0.10.1

- Improve empty-state hint — explain hook-powered session discovery

### 0.10.0

- Add agent team visibility — nest team members under parent session
- Treat empty permission_mode as default in table and detail panel
- Add exit session keybind (`d`) — sends `/exit` to iTerm2 via AppleScript

## 0.9 — Plan mode in prompt dialog

### 0.9.0

- Add plan mode toggle to prompt dialog (Shift+Tab)
- Fix stale documentation: cleanup timeouts, terminal nav, missing keybinding

## 0.8 — Settings panel overhaul

### 0.8.0

- Overhaul settings panel UI

## 0.7 — Unified notification settings

### 0.7.0

- Consolidate notification settings into unified settings panel

## 0.6 — Stale session handling

### 0.6.0

- Soft-hide stale idle sessions instead of deleting them
- Delete ended sessions from disk during cleanup
- Fix activity log crash on non-dict JSON transcript lines
- Hide sessions with unknown terminal from dashboard

## 0.5 — Send prompt to session

### 0.5.1

- Fix user messages not showing in activity log
- Fix prompt dialog: Enter submits, Shift+Enter for new line

### 0.5.0

- Send prompt to session via iTerm2 AppleScript
- Fix PermissionRequest overwriting WAITING_ANSWER and PLAN statuses

## 0.4 — Permission detection

### 0.4.0

- Add PermissionRequest handler, drop Notification hook

## 0.3 — Activity log & stability fixes

### 0.3.4

- Move transcript reading from PostToolUse to Stop handler

### 0.3.3

- Fix waiting status stuck after declining permission/plan

### 0.3.2

- Split TUI refresh into fast and slow paths

### 0.3.1

- Fix session stuck in WAITING_ANSWER after user declines question

### 0.3.0

- Fix activity log truncation bug, deduplicate shared logic into modules
- Update notification docs for two-category system

## 0.2 — Foundation

### 0.2.0

- Self-update command, version check, and release workflow
- Notification system with two-category layout
- TTY-based terminal navigation (iTerm2, Ghostty, Terminal.app, Warp, IntelliJ)
- Native Rust hook dispatcher (~18x faster invocations)
- Diff-based DataTable updates instead of full rebuild every tick
- Theme picker with persistence
- Session detail panel, activity log with toggleable modes
- New session launcher with directory autocomplete
- Ghost session cleanup
- Monitor-only hooks — never blocks Claude Code
