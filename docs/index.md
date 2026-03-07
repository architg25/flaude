# Flaude

A portmanteau of "flawed" and "Claude" — because anything that passes through me picks up a few imperfections along the way. Powered by Claude, it occasionally achieves flawlessness, but true to its namesake, flawed is the default setting.

A lightweight TUI dashboard for monitoring multiple concurrent Claude Code sessions. Powered by Claude Code's hook system — zero polling of Claude's internals, no process injection, no bloat. Hooks fire on session events, write a JSON file, and exit. The dashboard reads those files on a 1-second timer. That's it.

The hook dispatcher ships as a native Rust binary for fast invocation (~14ms vs ~250ms for Python). Falls back to Python automatically if Rust isn't available at build time.

![Flaude demo](img/demo.gif)

## Features

- **Live session dashboard** — theme-aware status colors, context usage, uptime, and model info for all running sessions. Agent team members are visually nested under their parent session with tree connectors and agent names
- **Terminal navigation** — jump to any session's terminal tab/window with a keypress. Full tab-level switching on iTerm2 (via TTY matching). Ghostty does window-level matching. Terminal.app matches by custom tab title. Warp and IntelliJ bring the app to the foreground
- **Session launcher** — start new Claude sessions from the dashboard with directory autocomplete
- **Send prompt** — type a prompt in flaude and send it to an idle Claude session (iTerm2 / tmux)
- **Exit session** — send `/exit` to an idle Claude session from the dashboard (iTerm2 / tmux)
- **tmux backend** _(experimental)_ — launch and manage sessions through tmux for terminal-agnostic operation. See [tmux.md](tmux.md)
- **Notification system** — long turn completion and waiting-on-input alerts. Supports terminal bell, macOS notifications, and system sounds. Off by default
- **Custom session titles** — displays titles set via Claude Code's `/rename` command
- **Git worktree support** — sessions auto-grouped by git repo, worktrees grouped with main repo
- **Configurable grouping** — auto-group by repo, manual group assignment, group renaming
- **Activity log** — tail session transcripts with three verbosity modes (All / Summary / Tools)
- **Session detail panel** — session info, status, timing, context ratio, last prompt, pending questions
- **Monitor-only hooks** — never blocks Claude Code
- **Ghost session cleanup** — 30s process check, 30m soft-hide, 8h hard timeout

## Install

Requires **Python 3.11+** and **macOS** (terminal navigation uses AppleScript).

For faster hooks (~18x), install [Rust](https://www.rust-lang.org/tools/install) first.

```bash
# Optional: install Rust for the native hook dispatcher
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install flaude (compiles Rust binary if cargo is on PATH)
pip install git+ssh://git@ghe.spotify.net/vibes/flaude.git
flaude init
```

## Usage

```
flaude                  # Launch the dashboard
flaude status           # Quick CLI status table (no TUI)
flaude init             # Install hooks into Claude Code
flaude init --dry-run   # Preview hook installation
flaude uninstall        # Remove hooks from Claude Code
flaude uninstall --purge # Remove config, state, and pip uninstall
flaude update           # Self-update to latest version
```

## Key bindings

| Key         | Action                                                         |
| ----------- | -------------------------------------------------------------- |
| `Enter`/`g` | Navigate to session's terminal (or rename group on header row) |
| `n`         | Launch a new Claude session (directory picker)                 |
| `p`         | Send a prompt to the selected session (iTerm2 / tmux)          |
| `d`         | Exit the selected session (iTerm2 / tmux)                      |
| `l`         | Cycle activity log mode (All / Summary / Tools)                |
| `s`/`S`     | Toggle notifications / notification settings                   |
| `t`         | Change theme (Textual theme picker with search)                |
| `G`         | Assign session to a named group (manual grouping)              |
| `h`         | Toggle display of hidden/stale sessions                        |
| `?`         | Help dialog                                                    |
| `q`         | Quit                                                           |

## Architecture

```
Hook events (stdin JSON)
        │
        ▼
  flaude-hook (Rust)      ← Native binary, ~14ms per invocation
  or dispatcher.py        ← Python fallback if Rust binary unavailable
        │
        ├─▶ state/<session>.json  ← Atomic write to /tmp/flaude/state/
        └─▶ logs/activity.log     ← Append one-line log entry

  tui/app.py              ← Polls state files every 1s, updates widgets
        │
        ├─▶ session_table.py     ← DataTable with status, context, mode columns
        ├─▶ session_detail.py    ← Right panel: full session info + pending questions
        ├─▶ permission_panel.py  ← Waiting sessions with question details
        └─▶ activity_log.py     ← Transcript viewer (All/Summary/Tools modes)
```

## More docs

- [Dashboard](dashboard.md) — detailed layout, terminals, notifications, configuration
- [tmux](tmux.md) — experimental tmux backend for terminal-agnostic session management
- [Rust Hook](rust-hook.md) — performance analysis of the native hook dispatcher
- [Known Bugs](BUG.md) — tracked issues
- [TODO](TODO.md) — future plans

## Slack

[#flaude](https://spotify.enterprise.slack.com/archives/C0AJW0SUJ2Y)
