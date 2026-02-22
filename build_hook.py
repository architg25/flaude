"""Hatch build hook: compile the Rust hook dispatcher and include it in the wheel.

If cargo is not available, silently skips — the Python fallback dispatcher
will be used instead.
"""

import platform
import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class RustBuildHook(BuildHookInterface):
    PLUGIN_NAME = "rust-hook"

    def initialize(self, version, build_data):
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
