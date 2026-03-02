# Dashboard

Detailed documentation for the Flaude TUI dashboard. For a quick overview, see the [README](../README.md).

## Dashboard layout

The TUI is split into a left pane and a right detail panel. Panels use rounded borders with a tiered visual hierarchy — primary panels (sessions, detail) use the theme's primary color, the waiting panel fades when dormant and escalates to warning when sessions need attention, and the activity log stays subdued.

**Left pane** (top to bottom):

- **Sessions table** -- All active sessions with columns: Status, Session, Project, Terminal, Mode, Context, Uptime. Sessions needing attention sort to the top. Agent team members are visually nested under their parent session with tree connectors (├/└) and show agent names instead of session IDs. When no sessions are active, shows a hint to start claude or run `flaude init`.
- **Waiting panel** -- Sessions waiting for user input (permission prompts or questions). Shows question text and answer options when available. Border escalates to warning color only when sessions are actually waiting.
- **Activity log** -- Transcript viewer for the selected session. Three verbosity modes cycled with `l`: All (full transcript), Summary (truncated output), Tools (hook events only).

**Right pane**:

- **Session detail** -- Sectioned view for the selected session, organized into: SESSION (ID, directory), TEAM (team name, agent role, lead session — shown for team members), STATUS (status, model, mode, terminal), TIMING (uptime, start time, current turn), CONTEXT (token usage vs model limit with color-coded ratio), LAST PROMPT, and PENDING QUESTION (with answer options or plan approval details including allowed prompts).

### Session table columns

| Column   | Description                                                                                                                                             |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Status   | Theme-colored label with duration (e.g. `RUNNING 3m12s`, `IDLE 45s`, `PERMISSION 1m05s`, `INPUT`). Team members are prefixed with tree connectors (├/└) |
| Session  | First 8 chars of the session ID, or agent name for team members (e.g. `researcher`)                                                                     |
| Project  | Directory basename                                                                                                                                      |
| Terminal | Detected terminal (iTerm2, Ghostty, Terminal, Warp, IntelliJ)                                                                                           |
| Mode     | Permission mode (default, plan, acceptEdits, etc.)                                                                                                      |
| Context  | Token count color-coded by model limit -- success (<50%), warning (50-80%), error (>80%)                                                                |
| Uptime   | Time since session started                                                                                                                              |

Context token limits are model-aware: 1M for Opus, 200K for Sonnet and Haiku. Colors adapt to the selected Textual theme.

### New session launcher

Pressing `n` opens a directory picker with tab-completion and arrow-key navigation for suggestions. Defaults to the selected session's working directory. Opens a new terminal tab and runs `claude` in the chosen directory.

### Exit session

Pressing `d` sends `/exit` to the selected session's iTerm2 terminal, cleanly exiting Claude Code. Uses the same AppleScript injection mechanism as prompt sending (`send_text_to_session`). A confirmation dialog (y/n/Esc) is shown before sending.

Same requirements as prompt sending: session must be IDLE or NEW, iTerm2 terminal, and have a known tty. Other terminals lack a per-session API to target a specific tab by TTY — sending keystrokes to the frontmost window risks hitting the wrong session.

### Notification system

Flaude has two notification categories, both **off by default**. Toggle with `s`, configure with `S`.

**Category 1: Long turn completion** -- fires when a turn finishes after exceeding a time threshold.

| Setting            | Default | Description                                                                             |
| ------------------ | ------- | --------------------------------------------------------------------------------------- |
| Enabled            | ON      | Active when master toggle is on                                                         |
| Terminal bell      | ON      | Rings the terminal bell                                                                 |
| macOS notification | OFF     | Native notification showing project name, duration, last prompt                         |
| System sound       | OFF     | Plays Glass.aiff                                                                        |
| Timer (minutes)    | 5       | Threshold before a turn is considered "long" (supports decimals like 0.1 for 6 seconds) |

Notification message: **"Flaude — \<project\>"** with subtitle **"Finished in \<duration\>"** and the last prompt as body text.

**Category 2: Waiting on input** -- fires when a session has been waiting for user input for longer than a configurable delay.

| Setting            | Default | Description                                                    |
| ------------------ | ------- | -------------------------------------------------------------- |
| Enabled            | OFF     | Must be explicitly enabled                                     |
| Terminal bell      | ON      | Rings the terminal bell                                        |
| macOS notification | OFF     | Native notification showing project name and wait reason       |
| System sound       | OFF     | Plays Glass.aiff                                               |
| Delay (seconds)    | 10      | How long to wait before firing (avoids noise from brief waits) |

Notification message: **"Flaude — \<project\>"** with subtitle depending on status:

- Permission prompt: **"Needs permission"**
- User question: **"Needs your answer"**
- Plan approval: **"Plan review needed"**

Body text shows the pending question when available.

**Behavior notes:**

- `s` quick-toggles the master switch without opening settings
- `S` opens the full settings dialog with per-category controls
- Notifications only fire for **new** events after enabling — existing sessions that already finished or are already waiting won't trigger retroactively
- Each session only fires once per event (a second alert requires the session to start a new turn or leave and re-enter a waiting state)
- Title bar shows 🔔 when notifications are on and 🔕 when off

## Supported terminals

Navigation (switching to the correct tab/window) and session launching:

| Terminal     | Tab switch | New tab | Bring to front | Send prompt/exit | Detection              |
| ------------ | ---------- | ------- | -------------- | ---------------- | ---------------------- |
| iTerm2       | Yes        | Yes     | Yes            | Yes              | tty-to-cwd match       |
| Ghostty      | Window     | Yes     | Yes            | No               | Window title match     |
| Terminal.app | Yes        | Yes     | Yes            | No               | Custom tab title match |
| Warp         | No         | Yes     | Yes            | No               | Brings app to front    |
| IntelliJ     | No         | No      | Yes            | No               | Detects running IDE    |

Terminal detection happens two ways: per-session via `TERM_PROGRAM` / `TERMINAL_EMULATOR` env vars (set by each session's hook), and as a dashboard fallback via AppleScript process detection.

## Ghost session cleanup

Sessions that stop reporting are cleaned up automatically:

- **30 seconds inactive** -- checks if a `claude` or `node` process still has the session's cwd (via `lsof`). If not, the session file is deleted.
- **30 minutes inactive** -- soft-hidden from the dashboard UI (configurable via settings or `FLAUDE_SOFT_HIDE_TIMEOUT`). The session file is NOT deleted; press `h` to toggle hidden sessions.
- **8 hours inactive** -- hard timeout, session file deleted regardless of process state. Configurable via `FLAUDE_STALE_SESSION_TIMEOUT`.

## Hook dispatcher

Claude Code invokes the hook dispatcher on every event (tool calls, session start/end, prompts, notifications). The dispatcher reads JSON from stdin, updates session state, and exits.

Flaude ships two dispatcher implementations:

- **`flaude-hook` (Rust)** — Native binary compiled from `rust/src/main.rs`. ~1.7MB, starts in ~14ms. Used automatically when available.
- **`hooks/dispatcher.py` (Python)** — Fallback when the Rust binary isn't present. Starts in ~250ms due to Python interpreter overhead.

Both produce identical output — the same JSON state files and activity log lines. The TUI reads these files and doesn't know or care which dispatcher wrote them.

### How the binary is selected

At import time, `constants.py` checks for `src/flaude/bin/flaude-hook`. If the binary exists and is executable, `HOOK_COMMAND` points to it. Otherwise, it falls back to `python3 -m flaude.hooks.dispatcher`. The `flaude init` command writes whichever command is active into `~/.claude/settings.json`.

### Building the Rust binary

If `cargo` is on PATH when you `pip install flaude`, the hatch build hook (`build_hook.py`) compiles the Rust crate automatically. If cargo isn't available, the build hook silently skips and the Python fallback is used.

To build manually:

```
cd rust && cargo build --release
cp target/release/flaude-hook ../src/flaude/bin/
flaude init   # re-register hooks with the binary
```

After upgrading flaude, re-run `flaude init` to pick up a new binary version.

### Performance

Measured on Apple Silicon (M-series Mac):

| Dispatcher | Avg invocation time | Relative |
| ---------- | ------------------- | -------- |
| Rust       | ~14ms               | 1x       |
| Python     | ~250ms              | ~18x     |

At high tool-call rates (busy search-and-edit sessions with dozens of tool calls per minute), the Rust binary reduces hook overhead from noticeable to imperceptible.

## Model and token tracking

The hook reads the session's transcript JSONL to extract the latest token usage (input + cache read + cache creation) and model name. This data populates the Context column and detail panel. Supported models: `claude-opus-4-6` (1M limit), `claude-sonnet-4-6` (200K), `claude-haiku-4-5` (200K).

## Configuration

**`~/.config/flaude/config.yaml`** -- Persists theme, log mode, and notification settings across restarts. Created automatically.

## Uninstalling

```
flaude uninstall          # Remove hooks from Claude Code
flaude uninstall --purge  # Also remove config, state dir, env var hints, and pip uninstall
```

## Environment variables

| Variable                       | Default                        | Description                                     |
| ------------------------------ | ------------------------------ | ----------------------------------------------- |
| `FLAUDE_STATE_DIR`             | `/tmp/flaude`                  | Root directory for state files                  |
| `FLAUDE_CONFIG_PATH`           | `~/.config/flaude/config.yaml` | Path to config YAML                             |
| `FLAUDE_STALE_SESSION_TIMEOUT` | `28800`                        | Seconds before a silent session is hard-removed |
| `FLAUDE_TUI_REFRESH_INTERVAL`  | `1.0`                          | Dashboard poll interval in seconds              |
| `FLAUDE_TERMINAL`              | (auto-detect)                  | Override terminal detection                     |
| `FLAUDE_SOFT_HIDE_TIMEOUT`     | (config's soft_hide_minutes)   | Seconds before idle sessions are hidden from UI |

Both the Rust and Python dispatchers respect `FLAUDE_STATE_DIR`.
