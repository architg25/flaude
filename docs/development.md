# Development Guide

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Rust toolchain (optional — only needed for the native hook dispatcher)

## Setup

Clone the repo and install in editable mode with dev dependencies:

```bash
git clone git@ghe.spotify.net:vibes/flaude.git
cd flaude
uv pip install -e ".[dev]"
```

Initialize hooks into Claude Code:

```bash
flaude init
```

This registers flaude's hook dispatcher in `~/.claude/settings.json` for all hook events (PreToolUse, PostToolUse, SessionStart, etc.). It also copies the default rules file to `~/.config/flaude/rules.yaml` if one doesn't exist.

To verify:

```bash
flaude init --dry-run   # preview what would be installed
flaude status           # quick status table without launching the TUI
flaude                  # launch the dashboard
```

## Project Structure

```
src/flaude/
├── cli.py                 # CLI entry point (init, run, status, update, uninstall)
├── config.py              # User config loading/saving
├── constants.py           # Paths, timeouts, shared constants
├── formatting.py          # Display formatting helpers
├── git.py                 # Git/worktree detection
├── tools.py               # Tool name/category mapping
├── version_check.py       # Update availability check
├── hooks/
│   ├── dispatcher.py      # Python hook dispatcher (fallback)
│   └── teams.py           # Agent team config reader
├── rules/
│   ├── engine.py          # Rules engine for hook filtering
│   └── default.yaml       # Default rules shipped with the package
├── state/
│   ├── models.py          # Pydantic session state models
│   ├── manager.py         # State file I/O
│   ├── scanner.py         # Session discovery from state files
│   └── cleanup.py         # Stale session cleanup
├── terminal/
│   ├── detect.py          # Terminal emulator detection
│   ├── navigate.py        # TTY-based terminal navigation
│   ├── inject.py          # Send prompts via AppleScript
│   └── launch.py          # Launch new Claude sessions
└── tui/
    ├── app.py             # Main Textual app
    ├── notifications.py   # Notification system
    ├── screens/           # Dialogs (prompt, settings, help, confirm)
    └── widgets/           # Table, detail panel, activity log, permissions
rust/
├── src/main.rs            # Native hook dispatcher (~18x faster)
└── Cargo.toml
```

## Versioning

Version is derived automatically from git tags at build time — no manual version bumping.

The build hook (`build_hook.py`) runs `git describe --tags --match 'v*'` and computes the version:

| Scenario            | Example             | Version                     |
| ------------------- | ------------------- | --------------------------- |
| On a tagged commit  | `v0.14.0`           | `0.14.0`                    |
| 3 commits after tag | `v0.14.0-3-gabcdef` | `0.14.3`                    |
| No tags in repo     | 42 total commits    | `0.0.42`                    |
| No git available    | —                   | Falls back to `__init__.py` |

The version is written into `src/flaude/__init__.py` during the build. The `rust/Cargo.toml` version is cosmetic and not auto-synced.

## Running Tests

```bash
python -m pytest tests/ -x -q
```

The test suite uses pytest with pytest-asyncio for async tests. Tests live in `tests/` with `pythonpath = ["tests"]` configured in `pyproject.toml`.

## Hook Dispatcher

The hook dispatcher is the core integration point with Claude Code. It receives JSON events on stdin and updates session state files that the TUI reads.

There are two implementations that must be kept in sync:

- **Python** — `src/flaude/hooks/dispatcher.py` (always available)
- **Rust** — `rust/src/main.rs` (optional, ~18x faster per invocation)

`flaude init` automatically picks the Rust binary if it was compiled during install. Otherwise it falls back to the Python dispatcher.

### Building the Rust dispatcher

```bash
cd rust
cargo build --release
```

The binary lands at `rust/target/release/flaude-hook`. During `pip install`, the build hook copies it to `src/flaude/bin/flaude-hook` automatically if cargo is available.

See [rust-hook.md](rust-hook.md) for performance benchmarks and implementation details.

## Key Data Paths

| Path                                   | Purpose                                          |
| -------------------------------------- | ------------------------------------------------ |
| `~/.claude/settings.json`              | Claude Code settings (hooks are registered here) |
| `~/.config/flaude/config.yaml`         | User config (theme, notifications, etc.)         |
| `~/.config/flaude/rules.yaml`          | Hook filtering rules                             |
| `~/.config/flaude/state/sessions/`     | Per-session state files (JSON)                   |
| `~/.config/flaude/state/dashboard.pid` | PID file for the running dashboard               |

## CLI Commands

| Command                    | Description                             |
| -------------------------- | --------------------------------------- |
| `flaude`                   | Launch the TUI dashboard                |
| `flaude init`              | Install hooks into Claude Code settings |
| `flaude init --dry-run`    | Preview hook installation               |
| `flaude status`            | Quick status table (no TUI)             |
| `flaude update`            | Self-update from Artifactory or Git     |
| `flaude update --dev`      | Include pre-release versions            |
| `flaude uninstall`         | Remove hooks from settings              |
| `flaude uninstall --purge` | Also remove config/state directories    |

## Release Workflow

Releases happen on demand, not on every commit. When ready to release:

1. Determine version bump from commits since last tag:
   - **Patch**: bug fixes, docs, refactors, dependency updates
   - **Minor**: new features, new CLI commands, behavioral changes
   - **Major**: never auto-bumped — user decides

2. Update `CHANGELOG.md` with notable changes

3. Commit, tag, push:
   ```bash
   git commit -am 'Release X.Y.Z'
   git tag vX.Y.Z
   git push && git push --tags
   ```

CI auto-publishes to Artifactory on push. Users install via:

```bash
uv pip install flaude                                           # from Artifactory
pip install git+ssh://git@ghe.spotify.net/vibes/flaude.git      # from source
```

## Environment Variables

All optional — sensible defaults are used if unset.

| Variable                       | Purpose                                      |
| ------------------------------ | -------------------------------------------- |
| `FLAUDE_STATE_DIR`             | Override state directory                     |
| `FLAUDE_CONFIG_PATH`           | Override config file path                    |
| `FLAUDE_RULES_PATH`            | Override rules file path                     |
| `FLAUDE_STALE_SESSION_TIMEOUT` | Seconds before a session is considered stale |
| `FLAUDE_TUI_REFRESH_INTERVAL`  | Dashboard refresh interval                   |
| `FLAUDE_TERMINAL`              | Force terminal emulator detection            |
