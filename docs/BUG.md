# Known Bugs

## Orphaned session on /resume

When a user starts `claude` (creates session A) and then runs `/resume <session_id>` to switch to an earlier session (session B), session A is orphaned and lingers in Flaude.

**Why it happens:**

1. `claude` starts → `SessionStart` fires for session A, state file created
2. User runs `/resume` → Claude switches to session B, `SessionStart` fires for B
3. Claude fires `SessionEnd` for the **previous** session (the one before A), not for A
4. Session A's state file remains — no `SessionEnd` ever fires for it
5. Ghost cleanup checks via `lsof` cwd matching, but the resumed session B shares the same cwd, so A looks alive

**Why it's hard to fix:**

- No per-terminal-tab identifier available in hooks (no tty, stdin is piped JSON)
- Can't delete other sessions in the same cwd on `SessionStart` — would break legit parallel sessions in the same directory
- Attempted fix: delete only `NEW`-status sessions in the same cwd on `SessionStart` — but the timing is unreliable (session A may have progressed past NEW before `/resume` happens)
- `_load_or_create` returning None for missing sessions prevents ghost resurrection from late events, but doesn't solve the original orphan

**Workaround:**

- Manually delete the orphaned state file: `rm /tmp/flaude/state/<session_id>.json`
- Wait 30 minutes for the hard timeout cleanup
- The orphan will eventually be cleaned up if it becomes truly inactive (no events for 30 minutes)

**Proper fix requires:**

- Claude Code exposing a `SessionEnd` event for the abandoned session when `/resume` is used
- Or a per-tab identifier (tty, PID) that hooks can access to distinguish sessions in the same terminal
