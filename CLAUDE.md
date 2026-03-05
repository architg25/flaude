# Flaude

Claude Code session manager — TUI dashboard for monitoring multiple concurrent Claude sessions.

## Project Structure

- `src/flaude/` — Python package (TUI, CLI, hooks, state management)
- `rust/` — Native hook dispatcher (optional, ~18x faster than Python fallback)
- `scripts/` — Developer tooling (version bump)
- `tests/` — pytest suite

## Version Management

Version source of truth: `src/flaude/__init__.py` (`__version__`).
`pyproject.toml` reads it dynamically via `[tool.hatch.version]`.
`rust/Cargo.toml` version is cosmetic — kept in sync by the bump script.

## Release Workflow

When the user asks to push, ship, or release changes:

1. **Determine bump level** from the commits since last tag:
   - **Patch** (X.Y.Z → X.Y.Z+1): Bug fixes, docs, refactors, typo fixes, dependency updates, test-only changes
   - **Minor** (X.Y.Z → X.Y+1.0): New features, new CLI commands, new config options, behavioral changes, new files with new functionality
   - **Major**: Never auto-bump. Only the user decides when to bump major.

2. **Run the bump script**: `python scripts/bump_version.py <new-version>`

3. **Update CHANGELOG.md**:
   - **Patch**: Add bullet points to the existing `### X.Y.Z-1` entry (or create `### X.Y.Z` if the previous patch had a distinct theme)
   - **Minor**: Create a new `## X.Y — <theme>` section at the top with a `### X.Y.0` entry
   - **Major**: Same as minor but with a new major section
   - List notable changes as bullet points, derived from the commits since last tag

4. **Commit, tag, and push**:
   ```
   git commit -am 'Bump to <new-version>'
   git tag v<new-version>
   git push && git push --tags
   ```

Do NOT run this workflow on every commit. Only when explicitly asked to push/ship/release.
Do NOT bump the version for documentation-only changes (README, docs/, CLAUDE.md, comments). Just commit and push directly.

## Hook Dispatcher Parity

The hook dispatcher exists in two implementations: Python (`src/flaude/hooks/dispatcher.py`) and Rust (`rust/src/main.rs`). When changing one, always check if the same change applies to the other.

## Running Tests

```
python -m pytest tests/ -x -q
```
