# TODO

## Kill session from dashboard (d key)

Need a reliable way to terminate a Claude Code session from the flaude TUI.

**Problem:** Claude Code doesn't expose a CLI command to stop a session by ID. Process matching is unreliable because:

- `pkill -f` only works for `--resume` sessions (session ID is in args)
- Fresh sessions started with just `claude` don't have the session ID in their command line
- `lsof` cwd matching is noisy — hundreds of `node` processes share generic cwds

**Possible approaches:**

- Wait for Claude Code to add a `claude stop <session-id>` CLI command
- Use the Stop hook to write a "please exit" signal file that a custom Stop hook reads
- Send SIGTERM to the specific tty's foreground process group (needs tty tracking in session state)

**UI already built (removed, can be restored):**

- `d` keybind on session table
- Confirmation dialog with session details (project, ID, terminal, status, age, tools)
- `ConfirmScreen` modal (y/n/Esc)

## Send prompt to session from dashboard

Type a message in flaude and have it sent to a selected Claude session as if typed in the terminal.

**Problem:** Claude Code reads from stdin in its own terminal. We don't own that stdin, so there's no clean way to inject a prompt into a running session.

**Possible approaches:**

- Wait for Claude Code to add a `claude send <session-id> <prompt>` API
- Keystroke injection via AppleScript to iTerm2 (fragile, single-line only, iTerm2-only)
- Navigate + clipboard: copy prompt to clipboard, switch to the terminal, user pastes
- File-based messaging with a custom hook (no hook event fires while waiting for input)
