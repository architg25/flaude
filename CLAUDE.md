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
- No git: falls back to whatever is in `__init__.py`
- `rust/Cargo.toml` version is cosmetic and no longer auto-synced.

## Release Workflow

When the user asks to push, ship, or release changes:

1. **Determine version** from the commits since last tag:
   - **Patch** (X.Y.Z → X.Y.Z+1): Bug fixes, docs, refactors, typo fixes, dependency updates, test-only changes
   - **Minor** (X.Y.Z → X.Y+1.0): New features, new CLI commands, new config options, behavioral changes
   - **Major**: Never auto-bump. Only the user decides when to bump major.

2. **Update CHANGELOG.md**:
   - **Patch**: Add bullet points to the existing entry (or create new one if distinct theme)
   - **Minor**: Create a new `## X.Y — <theme>` section at the top
   - List notable changes as bullet points, derived from the commits since last tag

3. **Commit, tag, and push**:
   ```
   git commit -am 'Release <new-version>'
   git tag v<new-version>
   git push && git push --tags
   ```

CI auto-publishes to Artifactory on push. Users can install via:

- `uv pip install flaude` (from Artifactory)
- `pip install git+ssh://git@ghe.spotify.net/vibes/flaude.git` (from source)

Do NOT run this workflow on every commit. Only when explicitly asked to push/ship/release.
Do NOT create tags for documentation-only changes. Just commit and push directly.

## Hook Dispatcher Parity

The hook dispatcher exists in two implementations: Python (`src/flaude/hooks/dispatcher.py`) and Rust (`rust/src/main.rs`). When changing one, always check if the same change applies to the other.

## Running Tests

```
python -m pytest tests/ -x -q
```
