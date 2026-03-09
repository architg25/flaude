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
        "last_event": "PermissionRequest",
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
    # --- Team lead: orchestrating a migration with subagents ---
    {
        "session_id": str(uuid.uuid4()),
        "status": "working",
        "cwd": "/Users/you/Git/payments-service",
        "permission_mode": "default",
        "terminal": "Ghostty",
        "model": "claude-opus-4-6",
        "context_tokens": 680_000,
        "turn_started_at_offset": 45,
        "started_at_offset": 5400,  # 1.5 hours ago
        "last_event": "PostToolUse",
        "last_prompt": "Migrate payments-service from REST to gRPC, delegate tests to subagents",
        "last_tool": {"name": "Agent", "summary": "integration-tests"},
        "tool_stats": {"Read": 22, "Edit": 14, "Bash": 5, "Agent": 3, "Grep": 8},
        "team_name": "payments-migration",
        "agent_name": "lead",
        "subagent_count": 3,
        "git_repo_root": "/Users/you/Git/payments-service",
        "git_branch": "feat/grpc-migration",
    },
    # --- Team member: working in a worktree, linked to lead ---
    {
        "session_id": str(uuid.uuid4()),
        "status": "working",
        "cwd": "/Users/you/Git/payments-service-wt-1",
        "permission_mode": "bypassPermissions",
        "terminal": "Ghostty",
        "model": "claude-sonnet-4-6",
        "context_tokens": 95_000,
        "turn_started_at_offset": 12,
        "started_at_offset": 300,  # 5 minutes ago
        "last_event": "PostToolUse",
        "last_prompt": "Write integration tests for the new gRPC endpoints",
        "last_tool": {"name": "Bash", "summary": "pytest tests/integration/ -x -q"},
        "tool_stats": {"Read": 6, "Edit": 4, "Bash": 3},
        "team_name": "payments-migration",
        "agent_name": "integration-tests",
        "lead_session_id": "LEAD_PLACEHOLDER",  # patched at creation time
        "git_repo_root": "/Users/you/Git/payments-service",
        "git_branch": "feat/grpc-migration",
        "git_is_worktree": True,
    },
    # --- Error session: something went wrong ---
    {
        "session_id": str(uuid.uuid4()),
        "status": "error",
        "cwd": "/Users/you/Git/search-index",
        "permission_mode": "default",
        "terminal": "iTerm2",
        "model": "claude-opus-4-6",
        "context_tokens": 920_000,
        "started_at_offset": 7200,  # 2 hours ago
        "last_event": "Error",
        "last_prompt": "Rebuild the search index with the new tokenizer",
        "last_tool": {"name": "Bash", "summary": "python rebuild_index.py --shard=3"},
        "tool_stats": {"Read": 30, "Edit": 12, "Bash": 18, "Grep": 9},
        "error_count": 2,
        "git_repo_root": "/Users/you/Git/search-index",
        "git_branch": "main",
    },
    # --- Loops + custom title: monitoring session ---
    {
        "session_id": str(uuid.uuid4()),
        "status": "idle",
        "cwd": "/Users/you/Git/platform-health",
        "permission_mode": "default",
        "terminal": "iTerm2",
        "model": "claude-sonnet-4-6",
        "context_tokens": 55_000,
        "started_at_offset": 10800,  # 3 hours ago
        "last_event": "Stop",
        "last_prompt": "Check service health and alert on anomalies",
        "last_tool": {"name": "Bash", "summary": "curl -s health.internal/status"},
        "tool_stats": {"Read": 3, "Bash": 12},
        "last_turn_duration": 8.0,
        "custom_title": "Platform Monitor",
        "is_tmux": True,
        "tmux_pane": "%7",
        "parent_terminal": "iTerm2",
        "loops": {
            "health-check": {
                "task_id": "task-001",
                "cron_expr": "*/5 * * * *",
                "human_schedule": "every 5 minutes",
                "prompt": "Check /status endpoints for all services and report anomalies",
                "recurring": True,
                "created_at": "2026-03-09T10:00:00",
            },
            "log-scan": {
                "task_id": "task-002",
                "cron_expr": "0 * * * *",
                "human_schedule": "every hour",
                "prompt": "Scan error logs for new patterns since last check",
                "recurring": True,
                "created_at": "2026-03-09T10:05:00",
            },
        },
    },
]

# Patch team member's lead_session_id to point to the actual team lead
SESSIONS[6]["lead_session_id"] = SESSIONS[5]["session_id"]


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
            "error_count": s.get("error_count", 0),
            "subagent_count": s.get("subagent_count", 0),
            "transcript_path": None,
            "team_name": s.get("team_name"),
            "agent_name": s.get("agent_name"),
            "lead_session_id": s.get("lead_session_id"),
            "custom_title": s.get("custom_title"),
            "git_repo_root": s.get("git_repo_root"),
            "git_branch": s.get("git_branch"),
            "git_is_worktree": s.get("git_is_worktree", False),
            "is_tmux": s.get("is_tmux"),
            "tmux_pane": s.get("tmux_pane"),
            "parent_terminal": s.get("parent_terminal"),
            "loops": s.get("loops", {}),
        }

        path = STATE_DIR / f"{s['session_id']}.json"
        path.write_text(json.dumps(state, indent=2))
        print(f"  Created {s['status']:<20} {s['cwd'].rsplit('/', 1)[-1]}")

    # Generate fake activity log entries
    log_dir = STATE_DIR.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "activity.log"

    FAKE_LOGS = {
        0: [  # backend-api (WORKING) — Read:12, Edit:8, Bash:3, Grep:5
            ("SessionStart", ""),
            (
                "UserPrompt",
                "Refactor the authentication middleware to use JWT tokens instead of session cookies",
            ),
            ("PreToolUse", 'Read "middleware.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "settings.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "session.*cookie"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Grep "jwt.*token"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "jwt.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "models.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "requirements.txt"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "import.*session"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Edit "middleware.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Edit "middleware.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Edit "settings.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Read "test_auth.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "test_middleware.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "test_auth.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Edit "test_middleware.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "python -m pytest tests/test_auth.py -x -q"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Read "conftest.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "conftest.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Read "views.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "authenticate"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "views.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "views.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Read "urls.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "middleware"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Edit "middleware.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Read "serializers.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Bash "python -m pytest tests/ -x -q"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Bash "python -m pytest tests/ -x -q --tb=short"'),
            ("PostToolUse", "Bash"),
        ],
        1: [  # flaude (IDLE) — Read:4, Edit:3, Bash:2
            ("SessionStart", ""),
            ("UserPrompt", "Add notification indicator to the title bar"),
            ("PreToolUse", 'Read "app.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "session_table.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "models.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "app.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Edit "app.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Read "constants.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "session_table.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "python -m pytest tests/ -x -q"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Bash "git push origin master"'),
            ("PostToolUse", "Bash"),
            ("Stop", "idle"),
        ],
        2: [  # mobile-app (INPUT - AskUserQuestion) — Read:7, Grep:3, Bash:1
            ("SessionStart", ""),
            ("UserPrompt", "Set up the CI/CD pipeline for the mobile app"),
            ("PreToolUse", 'Read "ci.yml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "Fastfile"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "runner.*macos"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "Gemfile"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "build.gradle"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "signing.*config"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "Podfile"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "package.json"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Bash "fastlane lanes"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Read "Matchfile"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "deploy.*lane"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'AskUserQuestion "CI provider"'),
        ],
        3: [  # infra (PERMISSION) — Read:15, Edit:6, Bash:9, Grep:4
            ("SessionStart", ""),
            ("UserPrompt", "Deploy the new database migration to staging"),
            ("PreToolUse", 'Read "migration.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "values.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "postgres.*version"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "kustomization.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "deployment.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Bash "kubectl get pods -n staging"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Read "configmap.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "migration.yaml"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "kubectl diff -f migration.yaml"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Read "secrets.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "migration.*version"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "rollback.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "values.yaml"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "helm template staging . -f values.yaml | head -50"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Read "service.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "hpa.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Bash "kubectl get migrations -n staging"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Read "pdb.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "configmap.yaml"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Grep "readinessProbe"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "ingress.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "deployment.yaml"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "kubectl apply --dry-run=server -f ."'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Read "cronjob.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "resources.*limits"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Edit "migration.yaml"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Read "statefulset.yaml"'),
            ("PostToolUse", "Read"),
            (
                "PreToolUse",
                'Bash "kubectl get events -n staging --sort-by=.lastTimestamp"',
            ),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Edit "rollback.yaml"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "kubectl diff -f ."'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Read "namespace.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "networkpolicy.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Bash "kubectl get pvc -n staging"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Bash "kubectl describe node staging-pool-0"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Bash "kubectl top pods -n staging"'),
            ("PostToolUse", "Bash"),
            (
                "PreToolUse",
                'Bash "kubectl logs -n staging deploy/db-migration --tail=20"',
            ),
            ("PostToolUse", "Bash"),
            (
                "PreToolUse",
                'Bash "kubectl apply -f migration.yaml --namespace staging"',
            ),
            ("PostToolUse", "Bash"),
            (
                "PreToolUse",
                'Bash "kubectl rollout status deployment/db-migration -n staging"',
            ),
            ("PostToolUse", "Bash"),
            ("PermissionRequest", "Bash"),
        ],
        4: [  # data-pipeline (PLAN - ExitPlanMode) — Read:10, Grep:6, Glob:2
            ("SessionStart", ""),
            ("UserPrompt", "Optimize the Spark job to reduce shuffle operations"),
            ("PreToolUse", 'Read "job.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "shuffle"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "config.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Glob "spark/**/*.py"'),
            ("PostToolUse", "Glob"),
            ("PreToolUse", 'Read "transforms.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "repartition"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "pipeline.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "groupBy"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "schemas.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "partitioner.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "coalesce"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Glob "spark/**/test_*.py"'),
            ("PostToolUse", "Glob"),
            ("PreToolUse", 'Read "test_job.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "broadcast"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "utils.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "join.*shuffle"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "metrics.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "spark_submit.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'ExitPlanMode ""'),
        ],
        5: [  # payments-service (WORKING, team lead) — Read:22, Edit:14, Bash:5, Agent:3, Grep:8
            ("SessionStart", ""),
            (
                "UserPrompt",
                "Migrate payments-service from REST to gRPC, delegate tests to subagents",
            ),
            ("PreToolUse", 'Read "api/routes.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "@app.route"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "proto/payments.proto"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "services/payment.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "proto/payments.proto"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Edit "services/payment.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Grep "def process_payment"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "models/transaction.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "services/grpc_server.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "python -m grpc_tools.protoc payments.proto"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Agent "unit-tests"'),
            ("PostToolUse", "Agent"),
            ("PreToolUse", 'Agent "integration-tests"'),
            ("PostToolUse", "Agent"),
            ("PreToolUse", 'Read "config/grpc.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "config/grpc.yaml"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Agent "load-tests"'),
            ("PostToolUse", "Agent"),
        ],
        6: [  # payments-service-wt-1 (WORKING, team member) — Read:6, Edit:4, Bash:3
            ("SessionStart", ""),
            ("UserPrompt", "Write integration tests for the new gRPC endpoints"),
            ("PreToolUse", 'Read "tests/conftest.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "proto/payments_pb2_grpc.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Read "tests/integration/test_rest.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "tests/integration/test_grpc.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Read "services/grpc_server.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "tests/integration/test_grpc.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Read "tests/fixtures/payments.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "tests/integration/test_grpc.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "pytest tests/integration/test_grpc.py -x -q"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Read "tests/integration/test_grpc.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "tests/integration/test_grpc.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "pytest tests/integration/test_grpc.py -x -q"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Bash "pytest tests/integration/ -x -q"'),
            ("PostToolUse", "Bash"),
        ],
        7: [  # search-index (ERROR) — Read:30, Edit:12, Bash:18, Grep:9
            ("SessionStart", ""),
            ("UserPrompt", "Rebuild the search index with the new tokenizer"),
            ("PreToolUse", 'Read "tokenizer.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Grep "class.*Tokenizer"'),
            ("PostToolUse", "Grep"),
            ("PreToolUse", 'Read "index_builder.py"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Edit "index_builder.py"'),
            ("PostToolUse", "Edit"),
            ("PreToolUse", 'Bash "python rebuild_index.py --shard=0"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Bash "python rebuild_index.py --shard=1"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Bash "python rebuild_index.py --shard=2"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Bash "python rebuild_index.py --shard=3"'),
            ("Error", "Process exited with code 137 (OOM killed)"),
        ],
        8: [  # platform-health (IDLE, loops + custom title) — Read:3, Bash:12
            ("SessionStart", ""),
            ("UserPrompt", "Check service health and alert on anomalies"),
            ("PreToolUse", 'Read "services.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Bash "curl -s health.internal/status"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Read "alerting/rules.yaml"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Bash "curl -s health.internal/status"'),
            ("PostToolUse", "Bash"),
            ("PreToolUse", 'Read "dashboards/overview.json"'),
            ("PostToolUse", "Read"),
            ("PreToolUse", 'Bash "curl -s health.internal/status"'),
            ("PostToolUse", "Bash"),
            ("Stop", "idle"),
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
