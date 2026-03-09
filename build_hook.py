"""Hatch build hook: resolve version from git tags and compile the Rust
hook dispatcher.

Version logic: latest git tag + commits since → patch version.
Rust compilation is optional — falls back to the Python dispatcher.
"""

import re
import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class RustBuildHook(BuildHookInterface):
    PLUGIN_NAME = "rust-hook"

    def _resolve_version(self) -> str | None:
        """Resolve version from git: latest tag + commit count since tag."""
        root = str(Path(self.root))

        # Try: git describe --tags --match 'v*'
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--match", "v*"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            # Output like "v0.14.0" or "v0.14.0-3-gabcdef"
            desc = result.stdout.strip()
            m = re.match(r"v(\d+\.\d+\.\d+)(?:-(\d+)-g[0-9a-f]+)?$", desc)
            if m:
                base = m.group(1)
                commits_since = int(m.group(2)) if m.group(2) else 0
                if commits_since == 0:
                    return base
                major, minor, patch = base.split(".")
                return f"{major}.{minor}.{int(patch) + commits_since}"
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
        ):
            pass

        # Fallback: commit count
        try:
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            return f"0.0.{result.stdout.strip()}"
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
        ):
            return None

    def _write_version(self, version: str) -> None:
        """Write resolved version to __init__.py."""
        init_path = Path(self.root) / "src" / "flaude" / "__init__.py"
        text = init_path.read_text()
        new_text = re.sub(
            r'__version__\s*=\s*"[^"]*"', f'__version__ = "{version}"', text
        )
        if new_text != text:
            init_path.write_text(new_text)
            self._log(f"Set version to {version}")

    def initialize(self, version, build_data):
        # Resolve version from git tags
        resolved = self._resolve_version()
        if resolved:
            self._write_version(resolved)

        rust_dir = Path(self.root) / "rust"
        if not rust_dir.exists():
            return

        cargo = shutil.which("cargo")
        if cargo is None:
            self._log(
                "cargo not found, skipping Rust build (Python fallback will be used)"
            )
            return

        self._log("Building flaude-hook with cargo...")
        try:
            subprocess.run(
                [cargo, "build", "--release"],
                cwd=str(rust_dir),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            self._log(f"cargo build failed: {e.stderr}")
            self._log("Skipping Rust build (Python fallback will be used)")
            return

        # Find the compiled binary
        binary_name = "flaude-hook"
        binary = rust_dir / "target" / "release" / binary_name
        if not binary.exists():
            self._log(f"Binary not found at {binary}, skipping")
            return

        # Copy to src/flaude/bin/
        dest_dir = Path(self.root) / "src" / "flaude" / "bin"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / binary_name
        shutil.copy2(str(binary), str(dest))
        dest.chmod(0o755)

        self._log(f"Installed flaude-hook binary to {dest}")

    def _log(self, msg):
        self.app.display_info(f"[rust-hook] {msg}")
