<p align="center">
  <img src="!/flaude.svg" width="120" alt="flaude">
</p>

## flaude

A TUI dashboard for monitoring multiple concurrent Claude Code sessions.

### What it does

flaude installs lightweight hooks into Claude Code that report session activity to a shared state directory. A Textual-based dashboard polls that state and displays a live overview of all running sessions -- status, context usage, pending questions, transcripts, and more.

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
```

### Dashboard layout

The TUI is split into a left pane and a right detail panel.

**Left pane** (top to bottom):

- **Sessions table** -- All active sessions with columns: Status, Session ID, Project, Terminal, Mode, Context, Uptime. Sessions needing attention sort to the top.
- **Waiting panel** -- Sessions waiting for user input (permission prompts or questions). Shows question text and answer options when available.
- **Activity log** -- Transcript viewer for the selected session. Three verbosity modes cycled with `l`: All (full transcript), Summary (truncated output), Tools (hook events only).

**Right pane**:

- **Session detail** -- Deep info for the selected session: full session ID, status, project, directory, terminal, permission mode, model, start time, uptime, current turn duration, context tokens vs model limit, last prompt, and any pending questions with their options.

#### Session table columns

| Column   | Description                                                                                     |
| -------- | ----------------------------------------------------------------------------------------------- |
| Status   | Color-coded label with duration (e.g. `RUNNING 3m12s`, `IDLE 45s`, `PERMISSION 1m05s`, `INPUT`) |
| Session  | First 8 chars of the session ID                                                                 |
| Project  | Directory basename                                                                              |
| Terminal | Detected terminal (iTerm2, Ghostty, Terminal, Warp, IntelliJ)                                   |
| Mode     | Permission mode (default, plan, etc.)                                                           |
| Context  | Token count color-coded by model limit -- green (<50%), yellow (50-80%), red (>80%)             |
| Uptime   | Time since session started                                                                      |

Context token limits are model-aware: 1M for Opus, 200K for Sonnet and Haiku.

#### Key bindings

| Key         | Action                                          |
| ----------- | ----------------------------------------------- |
| `Enter`/`g` | Navigate to the selected session's terminal     |
| `n`         | Launch a new Claude session (directory picker)  |
| `l`         | Cycle activity log mode (All / Summary / Tools) |
| `s`         | Quick toggle notifications on/off               |
| `S`         | Notification settings dialog                    |
| `t`         | Change theme (Textual theme picker with search) |
| `?`         | Help dialog                                     |
| `q`         | Quit                                            |

#### New session launcher

Pressing `n` opens a directory picker with tab-completion and arrow-key navigation for suggestions. Defaults to the selected session's working directory. Opens a new terminal tab and runs `claude` in the chosen directory.

#### Notification system

flaude alerts you when a long-running turn finishes. Configure via `S`:

- **Terminal bell** -- rings the terminal bell (on by default)
- **macOS notification** -- native notification center alert
- **System sound** -- plays Glass.aiff
- **Timer threshold** -- minutes before a turn is considered "long" (default: 5, supports decimals like 0.1 for 6 seconds)

Quick toggle with `s` to mute/unmute without opening settings. Notifications fire when a turn that exceeded the timer finishes, not while it's still running.

### Supported terminals

Navigation (switching to the correct tab/window) and session launching:

| Terminal     | Tab switch | New tab | Bring to front | Detection              |
| ------------ | ---------- | ------- | -------------- | ---------------------- |
| iTerm2       | Yes        | Yes     | Yes            | tty-to-cwd match       |
| Ghostty      | Window     | Yes     | Yes            | Window title match     |
| Terminal.app | Yes        | Yes     | Yes            | Custom tab title match |
| Warp         | No         | Yes     | Yes            | Brings app to front    |
| IntelliJ     | No         | No      | Yes            | Detects running IDE    |

Terminal detection happens two ways: per-session via `TERM_PROGRAM` / `TERMINAL_EMULATOR` env vars (set by each session's hook), and as a dashboard fallback via AppleScript process detection.

### Ghost session cleanup

Sessions that stop reporting are cleaned up automatically:

- **30 seconds inactive** -- checks if a `claude` or `node` process still has the session's cwd (via `lsof`). If not, the session file is deleted.
- **30 minutes inactive** -- hard timeout, session file deleted regardless of process state.

### Model and token tracking

The hook reads the session's transcript JSONL to extract the latest token usage (input + cache read + cache creation) and model name. This data populates the Context column and detail panel. Supported models: `claude-opus-4-6` (1M limit), `claude-sonnet-4-6` (200K), `claude-haiku-4-5` (200K).

### Configuration

**`~/.config/flaude/rules.yaml`** -- Rules engine for tool call evaluation. First-match-wins. Actions: `allow`, `deny`. Supports regex matching on tool inputs with `$CWD` substitution. Default rules allow safe reads, common git/shell commands, and block destructive operations.

**`~/.config/flaude/config.yaml`** -- Persists theme, log mode, and notification settings across restarts. Created automatically.

### Environment variables

| Variable                       | Default                        | Description                                     |
| ------------------------------ | ------------------------------ | ----------------------------------------------- |
| `FLAUDE_STATE_DIR`             | `/tmp/flaude`                  | Root directory for state files                  |
| `FLAUDE_RULES_PATH`            | `~/.config/flaude/rules.yaml`  | Path to rules YAML                              |
| `FLAUDE_CONFIG_PATH`           | `~/.config/flaude/config.yaml` | Path to config YAML                             |
| `FLAUDE_STALE_SESSION_TIMEOUT` | `1800`                         | Seconds before a silent session is hard-removed |
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
        ├─▶ session_table.py     ← DataTable with status, context, mode columns
        ├─▶ session_detail.py    ← Right panel: full session info + pending questions
        ├─▶ permission_panel.py  ← Waiting sessions with question details
        └─▶ activity_log.py     ← Transcript viewer (All/Summary/Tools modes)
```

Hook events handled: `SessionStart`, `PreToolUse`, `PostToolUse`, `Stop`, `Notification`, `UserPromptSubmit`, `SubagentStop`, `PreCompact`, `SessionEnd`.

State files are JSON (Pydantic models), written atomically via tmp+rename. The TUI reads them on a 1-second timer. The hook dispatcher swallows all exceptions to guarantee it never blocks Claude Code.

### Requirements

- Python 3.11+
- macOS (terminal navigation uses AppleScript)
- [textual](https://github.com/Textualize/textual) >= 1.0.0
- [pydantic](https://github.com/pydantic/pydantic) >= 2.0
- [pyyaml](https://github.com/yaml/pyyaml) >= 6.0
- [setproctitle](https://github.com/dvarrazzo/py-setproctitle) >= 1.3
