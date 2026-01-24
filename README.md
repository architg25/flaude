## flaude

A TUI dashboard for monitoring multiple concurrent Claude Code sessions.

### What it does

flaude installs lightweight hooks into Claude Code that report session activity to a shared state directory. A Textual-based dashboard polls that state and displays a live overview of all running sessions.

```
Claude Code sessions         flaude
┌──────────┐
│ session A │──hook──┐
└──────────┘        │     ┌──────────────────┐
┌──────────┐        ├────▶│  /tmp/flaude/     │──poll──▶  TUI Dashboard
│ session B │──hook──┤     │  state/*.json     │
└──────────┘        │     └──────────────────┘
┌──────────┐        │
│ session C │──hook──┘
└──────────┘
```

Hooks are **monitor-only**. flaude never blocks Claude Code's normal operation (except for hard-deny rules on dangerous commands like `rm -rf /`). Users approve permissions in their Claude terminal as usual.

### Install

```
pip install .
flaude init
```

`flaude init` registers hooks in `~/.claude/settings.json` (backs up the file first) and copies default rules to `~/.config/flaude/rules.yaml`.

### Usage

```
flaude                  # Launch the dashboard
flaude status           # Quick CLI status table (no TUI)
flaude init             # Install hooks into Claude Code
flaude init --dry-run   # Preview hook installation
flaude uninstall        # Remove hooks from Claude Code
flaude uninstall --purge # Also remove ~/.config/flaude/
flaude --help           # All commands
```

### Dashboard

The TUI has three panels stacked vertically:

**Sessions** -- DataTable of all active sessions. Columns: status icon, session ID, project directory, terminal, age, tool call count. Sessions needing attention sort to the top.

**Waiting** -- Lists sessions that are waiting for user input (permission prompts or questions). Shows the question text and answer options when available.

**Activity** -- Tails the activity log or session transcript for the selected session. Three verbosity modes cycled with `l`: Tools (hook events only), Summary (transcript with truncated output), All (full transcript).

#### Key bindings

| Key     | Action                                      |
| ------- | ------------------------------------------- |
| `Enter` | Navigate to the selected session's terminal |
| `g`     | Navigate to the selected session's terminal |
| `l`     | Cycle activity log mode (Tools/Summary/All) |
| `t`     | Change theme (Textual theme picker)         |
| `?`     | Show help                                   |
| `q`     | Quit                                        |

Pressing Enter/g uses AppleScript to find and focus the terminal tab running that session. Works by matching the session's working directory to terminal tab cwds.

### Supported terminals

Navigation support (switching to the correct tab/window from the dashboard):

| Terminal     | Tab switching | Bring to front | Notes                                |
| ------------ | ------------- | -------------- | ------------------------------------ |
| iTerm2       | Yes           | Yes            | Full support via tty-to-cwd match    |
| Ghostty      | Window only   | Yes            | Matches window title                 |
| Terminal.app | Yes           | Yes            | Matches custom tab title             |
| Warp         | No            | Yes            | No tab API; brings app to front      |
| JetBrains    | No            | Yes            | Detects running IDE, brings to front |

### Configuration

**`~/.config/flaude/rules.yaml`** -- Rules engine for tool call evaluation. First-match-wins. Actions: `allow`, `deny`, `ask_dashboard`. Supports regex matching on tool inputs with `$CWD` substitution. Default rules allow safe reads, allow common git/shell commands, and block destructive operations.

**`~/.config/flaude/config.yaml`** -- Persists theme selection and log mode preference across restarts. Created automatically.

### Environment variables

| Variable                       | Default                        | Description                                     |
| ------------------------------ | ------------------------------ | ----------------------------------------------- |
| `FLAUDE_STATE_DIR`             | `/tmp/flaude`                  | Root directory for state files                  |
| `FLAUDE_RULES_PATH`            | `~/.config/flaude/rules.yaml`  | Path to rules YAML                              |
| `FLAUDE_CONFIG_PATH`           | `~/.config/flaude/config.yaml` | Path to config YAML                             |
| `FLAUDE_STALE_SESSION_TIMEOUT` | `1800`                         | Seconds before a silent session is marked ended |
| `FLAUDE_TUI_REFRESH_INTERVAL`  | `1.0`                          | Dashboard poll interval in seconds              |
| `FLAUDE_TERMINAL`              | (auto-detect)                  | Override terminal detection                     |

### Architecture

```
Hook events (stdin JSON)
        │
        ▼
  hooks/dispatcher.py     ← Claude Code invokes on every event
        │
        ├─▶ state/manager.py   ← Atomic write to /tmp/flaude/state/<session>.json
        ├─▶ rules/engine.py    ← Evaluate tool call, emit deny if matched
        └─▶ logs/activity.log  ← Append one-line log entry

  tui/app.py              ← Polls state files every 1s, updates widgets
        │
        ├─▶ session_table.py     ← DataTable of sessions
        ├─▶ permission_panel.py  ← Waiting sessions list
        └─▶ activity_log.py     ← Tails logs or transcripts
```

Hook events handled: `SessionStart`, `PreToolUse`, `PostToolUse`, `Stop`, `Notification`, `UserPromptSubmit`, `SubagentStop`, `PreCompact`, `SessionEnd`.

State files are JSON (Pydantic models), written atomically via tmp+rename. The TUI reads them on a 1-second timer. Stale sessions are cleaned up every 30 seconds -- first by checking if the process still exists (via `lsof`), then by hard timeout.

The hook dispatcher swallows all exceptions to guarantee it never blocks Claude Code.

### Requirements

- Python 3.11+
- macOS (terminal navigation uses AppleScript)
- [textual](https://github.com/Textualize/textual) >= 1.0.0
- [pydantic](https://github.com/pydantic/pydantic) >= 2.0
- [pyyaml](https://github.com/yaml/pyyaml) >= 6.0
- [setproctitle](https://github.com/dvarrazzo/py-setproctitle) >= 1.3
