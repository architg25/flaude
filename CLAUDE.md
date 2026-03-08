# Flaude

Claude Code session manager — TUI dashboard for monitoring multiple concurrent Claude sessions.

## Project Structure

- `src/flaude/` — Python package (TUI, CLI, hooks, state management)
- `rust/` — Native hook dispatcher (optional, ~18x faster than Python fallback)
- `tests/` — pytest suite

## Version Management

Version is auto-derived from git tags at build time (via `build_hook.py`).
No manual version bumping needed — tag a commit and the version follows.

- On tagged commits (e.g. `v0.14.0`): version = `0.14.0`
- Between tags (3 commits after `v0.14.0`): version = `0.14.3`
- No tags: version = `0.0.<commit_count>`
- No git: falls back to `0.0.0` (the placeholder in `__init__.py`)
- `rust/Cargo.toml` and `__init__.py` both contain `0.0.0` placeholders — do not manually update them.

## Pushing Changes

When asked to push, commit and push. Patch versions are automatic (commit count since last tag).
Only create tags for minor/major releases — the user will say when.
Update CHANGELOG.md with notable changes on each push.

CI auto-publishes to Artifactory on push.

## Hook Dispatcher Parity

The hook dispatcher exists in two implementations: Python (`src/flaude/hooks/dispatcher.py`) and Rust (`rust/src/main.rs`). When changing one, always check if the same change applies to the other.

## Running Tests

```
python -m pytest tests/ -x -q
```
