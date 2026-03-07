# tmux Support

**Status: Experimental**

tmux backend for terminal-agnostic session management. Report issues in **#flaude**.

## Settings

In the settings panel (`S`), under **Terminal**:

| Setting        | Values               | Default  | Description                                                                                                                            |
| -------------- | -------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Launch backend | `auto` / `tmux`      | `auto`   | How new sessions are spawned. `auto` uses the current terminal's native tab. `tmux` creates windows in a shared `flaude` tmux session. |
| Tmux open mode | `inline` / `new_tab` | `inline` | How "go to session" (`g`) works for tmux sessions.                                                                                     |

### Open modes

- **inline** — If flaude is inside tmux, switches windows directly. Otherwise suspends flaude's TUI, attaches tmux in the same terminal. Detach with your tmux prefix + `d` (default `Ctrl+B D`) to return.
- **new_tab** — Opens a new terminal tab and runs `tmux attach` there. For iTerm2, tries to reuse an existing tab first.

## How it works

- New sessions run as windows inside a single `flaude` tmux session.
- The hook dispatcher detects `TMUX` and `TMUX_PANE` env vars on `SessionStart` and stores them in session state.
- Parent terminal (e.g. iTerm2, Warp) is detected by walking the tmux client's process tree.
- Send prompt (`p`) and exit session (`d`) use `tmux send-keys` — works on any terminal, not just iTerm2.
- `claude --teammateMode tmux` is supported automatically since each subagent fires its own hooks.

## Known Limitations

- **Parent terminal detection requires an attached client.** If no terminal is attached to the tmux session (fully detached), parent terminal shows `?`. It resolves once a client attaches.
- **No scanner backfill for tmux fields.** Pre-existing tmux sessions discovered at TUI startup won't have `tmux_pane` or `parent_terminal` until their next hook event fires (any prompt or tool use).
- **Navigate for non-iTerm2 terminals is imprecise in `new_tab` mode.** Warp, Ghostty, and others lack a tab-switching API — flaude can only bring the app to front, not select a specific tab.
- **Generic terminal launch uses clipboard.** For terminals without a scripting API (Warp, Ghostty, etc.), flaude copies the command to clipboard, pastes it, and presses Enter. The clipboard is saved and restored, but there's a brief moment where it's overwritten.
- **Inline mode suspend relies on Textual's `app.suspend()`.** If flaude crashes or is killed while tmux is attached, you'll be left in the tmux session. Just detach (`Ctrl+B D`) and restart flaude.
- **tmux must be installed.** If `tmux` is not on PATH when you select the tmux backend, flaude shows an error and falls back gracefully. Install with `brew install tmux`.
