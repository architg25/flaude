<p align="center">
  <img src="docs/img/flaude-animated.svg" width="120" alt="Flaude">
</p>

## Flaude

A portmanteau of "flawed" and "Claude" — because anything that passes through me picks up a few imperfections along the way. Powered by Claude, it occasionally achieves flawlessness, but true to its namesake, flawed is the default setting.

A lightweight TUI dashboard for monitoring multiple concurrent Claude Code sessions. Powered by Claude Code's hook system — zero polling of Claude's internals, no process injection, no bloat. Hooks fire on session events, write a JSON file, and exit. The dashboard reads those files on a 1-second timer. That's it.

<p align="center">
  <img src="docs/img/demo.gif" alt="Flaude demo">
</p>

### Features

- **Live session dashboard** -- theme-aware status colors, context usage, uptime, and model info for all running sessions
- **Terminal navigation** -- jump to any session's terminal tab/window with a keypress (iTerm2, Ghostty, Terminal.app, Warp, IntelliJ)
- **Session launcher** -- start new Claude sessions from the dashboard with directory autocomplete
- **Notification system** -- terminal bell, macOS notifications, and system sounds when long-running turns finish (off by default, 🔔/🔕 indicator in title bar)
- **Activity log** -- tail session transcripts in real time with three verbosity modes (All / Summary / Tools)
- **Session detail panel** -- sectioned view with session info, status, timing, context ratio, last prompt, and pending questions with plan approval details
- **Monitor-only hooks** -- never blocks Claude Code; users approve permissions in their own terminal as usual
- **Theme customization** -- all colors adapt to the selected Textual theme, with persistence across restarts
- **Ghost session cleanup** -- sessions inactive for 30s get a process check, 30min hard timeout. This only removes the session from Flaude's dashboard, not the actual Claude session — it reappears automatically on next activity. Configurable via `FLAUDE_STALE_SESSION_TIMEOUT`

### Install

Requires **Python 3.11+** and **macOS** (terminal navigation uses AppleScript).

```
pip install git+ssh://git@ghe.spotify.net/architg/flaude.git
flaude init
```

`flaude init` registers hooks in `~/.claude/settings.json` (backs up the file first).

### Usage

```
flaude                  # Launch the dashboard
flaude status           # Quick CLI status table (no TUI)
flaude init             # Install hooks into Claude Code
flaude init --dry-run   # Preview hook installation
flaude uninstall        # Remove hooks from Claude Code
flaude uninstall --purge # Remove config, state, and pip uninstall
```

### Key bindings

| Key         | Action                                          |
| ----------- | ----------------------------------------------- |
| `Enter`/`g` | Navigate to the selected session's terminal     |
| `n`         | Launch a new Claude session (directory picker)  |
| `l`         | Cycle activity log mode (All / Summary / Tools) |
| `s`/`S`     | Toggle notifications / notification settings    |
| `t`         | Change theme (Textual theme picker with search) |
| `?`         | Help dialog                                     |
| `q`         | Quit                                            |

### Architecture

```
Hook events (stdin JSON)
        │
        ▼
  hooks/dispatcher.py     ← Claude Code invokes on every event
        │
        ├─▶ state/manager.py   ← Atomic write to /tmp/flaude/state/<session>.json
        └─▶ logs/activity.log  ← Append one-line log entry

  tui/app.py              ← Polls state files every 1s, updates widgets
        │
        ├─▶ session_table.py     ← DataTable with status, context, mode columns
        ├─▶ session_detail.py    ← Right panel: full session info + pending questions
        ├─▶ permission_panel.py  ← Waiting sessions with question details
        └─▶ activity_log.py     ← Transcript viewer (All/Summary/Tools modes)
```

### Requirements

- Python 3.11+
- macOS (terminal navigation uses AppleScript)
- [textual](https://github.com/Textualize/textual) >= 1.0.0
- [pydantic](https://github.com/pydantic/pydantic) >= 2.0
- [pyyaml](https://github.com/yaml/pyyaml) >= 6.0
- [setproctitle](https://github.com/dvarrazzo/py-setproctitle) >= 1.3

For detailed documentation on dashboard layout, terminals, notifications, configuration, and environment variables, see [docs/reference.md](docs/reference.md). Known bugs are tracked in [docs/BUG.md](docs/BUG.md). Future plans are in [docs/TODO.md](docs/TODO.md).
