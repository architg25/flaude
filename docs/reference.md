# Reference

Detailed documentation for Flaude. For a quick overview, see the [README](../README.md).

## Dashboard layout

The TUI is split into a left pane and a right detail panel. Panels use rounded borders with a tiered visual hierarchy — primary panels (sessions, detail) use the theme's primary color, the waiting panel fades when dormant and escalates to warning when sessions need attention, and the activity log stays subdued.

**Left pane** (top to bottom):

- **Sessions table** -- All active sessions with columns: Status, Session ID, Project, Terminal, Mode, Context, Uptime. Sessions needing attention sort to the top. When no sessions are active, shows a hint to start claude or run `flaude init`.
- **Waiting panel** -- Sessions waiting for user input (permission prompts or questions). Shows question text and answer options when available. Border escalates to warning color only when sessions are actually waiting.
- **Activity log** -- Transcript viewer for the selected session. Three verbosity modes cycled with `l`: All (full transcript), Summary (truncated output), Tools (hook events only).

**Right pane**:

- **Session detail** -- Sectioned view for the selected session, organized into: SESSION (ID, directory), STATUS (status, model, mode, terminal), TIMING (uptime, start time, current turn), CONTEXT (token usage vs model limit with color-coded ratio), LAST PROMPT, and PENDING QUESTION (with answer options or plan approval details including allowed prompts).

### Session table columns

| Column   | Description                                                                                       |
| -------- | ------------------------------------------------------------------------------------------------- |
| Status   | Theme-colored label with duration (e.g. `RUNNING 3m12s`, `IDLE 45s`, `PERMISSION 1m05s`, `INPUT`) |
| Session  | First 8 chars of the session ID                                                                   |
| Project  | Directory basename                                                                                |
| Terminal | Detected terminal (iTerm2, Ghostty, Terminal, Warp, IntelliJ)                                     |
| Mode     | Permission mode (default, plan, acceptEdits, etc.)                                                |
| Context  | Token count color-coded by model limit -- success (<50%), warning (50-80%), error (>80%)          |
| Uptime   | Time since session started                                                                        |

Context token limits are model-aware: 1M for Opus, 200K for Sonnet and Haiku. Colors adapt to the selected Textual theme.

### New session launcher

Pressing `n` opens a directory picker with tab-completion and arrow-key navigation for suggestions. Defaults to the selected session's working directory. Opens a new terminal tab and runs `claude` in the chosen directory.

### Notification system

Flaude alerts you when a long-running turn finishes. Notifications are **off by default**. Configure via `S`:

- **Notify on finish** -- master toggle (off by default)
- **Terminal bell** -- rings the terminal bell (on by default when notifications enabled)
- **macOS notification** -- native notification center alert showing project name, last prompt, and duration
- **System sound** -- plays Glass.aiff
- **Timer threshold** -- minutes before a turn is considered "long" (default: 5, supports decimals like 0.1 for 6 seconds)

Quick toggle with `s` to mute/unmute without opening settings. Notifications fire when a turn that exceeded the timer finishes, not while it's still running. The title bar shows 🔔 when notifications are on and 🔕 when off.

## Supported terminals

Navigation (switching to the correct tab/window) and session launching:

| Terminal     | Tab switch | New tab | Bring to front | Detection              |
| ------------ | ---------- | ------- | -------------- | ---------------------- |
| iTerm2       | Yes        | Yes     | Yes            | tty-to-cwd match       |
| Ghostty      | Window     | Yes     | Yes            | Window title match     |
| Terminal.app | Yes        | Yes     | Yes            | Custom tab title match |
| Warp         | No         | Yes     | Yes            | Brings app to front    |
| IntelliJ     | No         | No      | Yes            | Detects running IDE    |

Terminal detection happens two ways: per-session via `TERM_PROGRAM` / `TERMINAL_EMULATOR` env vars (set by each session's hook), and as a dashboard fallback via AppleScript process detection.

## Ghost session cleanup

Sessions that stop reporting are cleaned up automatically:

- **30 seconds inactive** -- checks if a `claude` or `node` process still has the session's cwd (via `lsof`). If not, the session file is deleted.
- **30 minutes inactive** -- hard timeout, session file deleted regardless of process state.

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
| `FLAUDE_STALE_SESSION_TIMEOUT` | `1800`                         | Seconds before a silent session is hard-removed |
| `FLAUDE_TUI_REFRESH_INTERVAL`  | `1.0`                          | Dashboard poll interval in seconds              |
| `FLAUDE_TERMINAL`              | (auto-detect)                  | Override terminal detection                     |
