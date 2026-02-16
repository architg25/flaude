#!/usr/bin/env python3
"""Populate /tmp/flaude/state/ with mock sessions for demo screenshots/GIFs.

Usage:
    python scripts/demo.py          # Create mock sessions
    python scripts/demo.py --clean  # Remove mock sessions
"""

import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

STATE_DIR = Path("/tmp/flaude/state")

# Session IDs generated at import time, cleaned up on Ctrl+C
SESSIONS = [
    {
        "session_id": str(uuid.uuid4()),
        "status": "working",
        "cwd": "/Users/you/Git/backend-api",
        "permission_mode": "default",
        "terminal": "iTerm2",
        "model": "claude-opus-4-6",
        "context_tokens": 820_000,
        "turn_started_at_offset": 180,  # 3 minutes ago
        "started_at_offset": 2400,  # 40 minutes ago
        "last_event": "PostToolUse",
        "last_prompt": "Refactor the authentication middleware to use JWT tokens instead of session cookies",
        "last_tool": {"name": "Edit", "summary": "auth/middleware.py"},
        "tool_stats": {"Read": 12, "Edit": 8, "Bash": 3, "Grep": 5},
    },
    {
        "session_id": str(uuid.uuid4()),
        "status": "idle",
        "cwd": "/Users/you/Git/flaude",
        "permission_mode": "acceptEdits",
        "terminal": "iTerm2",
        "model": "claude-opus-4-6",
        "context_tokens": 210_000,
        "started_at_offset": 600,  # 10 minutes ago
        "last_event": "Stop",
        "last_prompt": "Add notification indicator to the title bar",
        "last_tool": {"name": "Bash", "summary": "git push origin master"},
        "tool_stats": {"Read": 4, "Edit": 3, "Bash": 2},
        "last_turn_duration": 45.0,
    },
    {
        "session_id": str(uuid.uuid4()),
        "status": "waiting_answer",
        "cwd": "/Users/you/Git/mobile-app",
        "permission_mode": "default",
        "terminal": "Ghostty",
        "model": "claude-sonnet-4-6",
        "context_tokens": 95_000,
        "started_at_offset": 1800,  # 30 minutes ago
        "last_event": "PreToolUse",
        "last_prompt": "Set up the CI/CD pipeline for the mobile app",
        "last_tool": {"name": "AskUserQuestion", "summary": ""},
        "tool_stats": {"Read": 7, "Grep": 3, "Bash": 1},
        "pending_question": {
            "questions": [
                {
                    "question": "Which CI provider should we use for the mobile builds?",
                    "header": "CI Provider",
                    "options": [
                        {
                            "label": "GitHub Actions",
                            "description": "Native GitHub integration, free for public repos",
                        },
                        {
                            "label": "CircleCI",
                            "description": "Better caching, macOS runners available",
                        },
                        {
                            "label": "Bitrise",
                            "description": "Mobile-first CI, built-in device testing",
                        },
                    ],
                    "multiSelect": False,
                }
            ]
        },
    },
    {
        "session_id": str(uuid.uuid4()),
        "status": "waiting_permission",
        "cwd": "/Users/you/Git/infra",
        "permission_mode": "plan",
        "terminal": "Terminal",
        "model": "claude-opus-4-6",
        "context_tokens": 450_000,
        "turn_started_at_offset": 5,
        "started_at_offset": 3600,  # 1 hour ago
        "last_event": "Notification",
        "last_prompt": "Deploy the new database migration to staging",
        "last_tool": {"name": "Bash", "summary": "kubectl apply -f migration.yaml"},
        "tool_stats": {"Read": 15, "Edit": 6, "Bash": 9, "Grep": 4},
    },
    {
        "session_id": str(uuid.uuid4()),
        "status": "waiting_answer",
        "cwd": "/Users/you/Git/data-pipeline",
        "permission_mode": "plan",
        "terminal": "iTerm2",
        "model": "claude-sonnet-4-6",
        "context_tokens": 140_000,
        "started_at_offset": 900,  # 15 minutes ago
        "last_event": "PreToolUse",
        "last_prompt": "Optimize the Spark job to reduce shuffle operations",
        "last_tool": {"name": "ExitPlanMode", "summary": ""},
        "tool_stats": {"Read": 10, "Grep": 6, "Glob": 2},
        "pending_question": {
            "allowedPrompts": [
                {"tool": "Bash", "prompt": "run spark tests"},
                {"tool": "Bash", "prompt": "submit spark job to staging"},
            ]
        },
    },
]


def create_demo():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.utcnow()

    for s in SESSIONS:
        started = now - timedelta(seconds=s["started_at_offset"])
        state = {
            "session_id": s["session_id"],
            "status": s["status"],
            "cwd": s["cwd"],
            "permission_mode": s["permission_mode"],
            "terminal": s["terminal"],
            "model": s["model"],
            "context_tokens": s["context_tokens"],
            "started_at": started.isoformat(),
            "last_event": s["last_event"],
            "last_event_at": (now - timedelta(seconds=5)).isoformat(),
            "last_prompt": s.get("last_prompt"),
            "tool_stats": s.get("tool_stats", {}),
            "last_tool": (
                {
                    "name": s["last_tool"]["name"],
                    "summary": s["last_tool"]["summary"],
                    "at": (now - timedelta(seconds=10)).isoformat(),
                }
                if s.get("last_tool")
                else None
            ),
            "pending_question": s.get("pending_question"),
            "turn_started_at": (
                (now - timedelta(seconds=s["turn_started_at_offset"])).isoformat()
                if s.get("turn_started_at_offset")
                else None
            ),
            "last_turn_duration": s.get("last_turn_duration", 0),
            "error_count": 0,
            "subagent_count": 0,
            "transcript_path": None,
        }

        path = STATE_DIR / f"{s['session_id']}.json"
        path.write_text(json.dumps(state, indent=2))
        print(f"  Created {s['status']:<20} {s['cwd'].rsplit('/', 1)[-1]}")

    # Generate fake activity log entries
    log_dir = STATE_DIR.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "activity.log"

    FAKE_LOGS = {
        0: [  # backend-api (WORKING)
            ("SessionStart", ""),
            ("UserPrompt", ""),
            ("PreToolUse", 'Read "auth/middleware.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "jwt.*token"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "auth/jwt.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "auth/middleware.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Read "tests/test_auth.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "auth/middleware.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "python -m pytest tests/test_auth.py"'),
            ("PostToolUse", "Bash"),
        ],
        1: [  # flaude (IDLE)
            ("SessionStart", ""),
            ("UserPrompt", ""),
            ("PreToolUse", 'Read "app.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "app.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "git add . && git commit"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Bash "git push origin master"'),
            ("PostToolUse", "Bash"),
            ("Stop", "idle"),
        ],
        2: [  # mobile-app (INPUT - AskUserQuestion)
            ("SessionStart", ""),
            ("UserPrompt", ""),
            ("PreToolUse", 'Read ".github/workflows/ci.yml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "runner.*macos"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "fastlane/Fastfile"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'AskUserQuestion "CI provider"'),
        ],
        3: [  # infra (PERMISSION)
            ("SessionStart", ""),
            ("UserPrompt", ""),
            ("PreToolUse", 'Read "k8s/migration.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "k8s/staging/values.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "k8s/migration.yaml"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "kubectl diff -f migration.yaml"'),
            ("PostToolUse", "Bash"),
            ("Notification", "permission"),
        ],
        4: [  # data-pipeline (PLAN - ExitPlanMode)
            ("SessionStart", ""),
            ("UserPrompt", ""),
            ("PreToolUse", 'Read "spark/job.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "shuffle"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "spark/config.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Glob "spark/**/*.py"'),
            ("PostToolUse", "Glob"),
            ("PreToolUse", 'ExitPlanMode ""'),
        ],
    }

    with open(log_file, "a") as f:
        for idx, s in enumerate(SESSIONS):
            sid = s["session_id"][:8]
            entries = FAKE_LOGS.get(idx, [])
            base_time = now - timedelta(seconds=s["started_at_offset"])
            for i, (event, detail) in enumerate(entries):
                ts = (base_time + timedelta(seconds=i * 15)).strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
                parts = [ts, f"[{sid}]", event]
                if detail:
                    parts.append(detail)
                f.write(" ".join(parts) + "\n")

    print(f"\n{len(SESSIONS)} demo sessions created. Run 'flaude' to see them.")
    print("Keeping sessions alive (Ctrl+C to stop and clean up)...\n")

    import time

    try:
        while True:
            time.sleep(10)
            now = datetime.utcnow()
            for s in SESSIONS:
                path = STATE_DIR / f"{s['session_id']}.json"
                if path.exists():
                    data = json.loads(path.read_text())
                    data["last_event_at"] = now.isoformat()
                    if data.get("turn_started_at"):
                        data["turn_started_at"] = (
                            now - timedelta(seconds=s.get("turn_started_at_offset", 0))
                        ).isoformat()
                    path.write_text(json.dumps(data, indent=2))
            print(".", end="", flush=True)
    except KeyboardInterrupt:
        print("\n\nCleaning up...")
        clean_demo()


def clean_demo():
    cleaned = 0
    for s in SESSIONS:
        path = STATE_DIR / f"{s['session_id']}.json"
        if path.exists():
            path.unlink()
            cleaned += 1
    print(f"Removed {cleaned} demo sessions.")


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean_demo()
    else:
        print("Creating demo sessions...\n")
        create_demo()
