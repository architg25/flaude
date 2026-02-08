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

## Permission management from dashboard

Approve or deny permission prompts directly from the Flaude dashboard, while still allowing the user to respond in the Claude terminal as usual.

**Problem:** Claude Code's `PreToolUse` hook expects a single synchronous response (allow/deny JSON on stdout). If Flaude's hook blocks waiting for dashboard input, but the user also approves in their terminal, there's a race condition — two responses to the same prompt. The hook must return before Claude Code proceeds, so blocking the hook while waiting for dashboard input would freeze the Claude session.

**Why we went monitor-only:** The current architecture deliberately avoids this. Hooks write state and exit immediately. The dashboard displays pending permissions but doesn't act on them. This guarantees hooks never block Claude Code.

**Possible approaches:**

- Hook writes a "pending" file and blocks with a short poll loop; dashboard writes an "approved/denied" file; hook reads it and responds. Risk: if user approves in terminal first, the hook's response is ignored but the poll loop still runs until timeout.
- Wait for Claude Code to support an async permission API or a way to programmatically respond to prompts from outside the session.
- Use the hook's timeout as a natural fallback — if no dashboard response within N seconds, allow the user's terminal response to take over. Requires careful coordination to avoid double-responses.
