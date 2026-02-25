#!/usr/bin/env python3
"""Bump version across all source files.

Usage: python scripts/bump_version.py 0.2.0
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

TARGETS = [
    (
        ROOT / "src/flaude/__init__.py",
        r'(__version__\s*=\s*["\'])[^"\']+(["\'])',
    ),
    (
        ROOT / "rust/Cargo.toml",
        r'^(version\s*=\s*")[^"]+(")',
    ),
]


def bump(version: str) -> None:
    for path, pattern in TARGETS:
        text = path.read_text()
        new_text = re.sub(
            pattern, rf"\g<1>{version}\g<2>", text, count=1, flags=re.MULTILINE
        )
        if new_text == text:
            print(f"  WARNING: no match in {path.name}")
        else:
            path.write_text(new_text)
            print(f"  Updated {path.name}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <version>")
        sys.exit(1)
    version = sys.argv[1]
    # Validate format
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        print(f"Invalid version: {version} (expected X.Y.Z)")
        sys.exit(1)
    print(f"Bumping to {version}:")
    bump(version)
    print(
        f"\n  git commit -am 'Bump to {version}' && git tag v{version} && git push --tags"
    )
