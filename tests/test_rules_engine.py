"""Tests for the rules engine."""

from pathlib import Path

import pytest

from flaude.rules.engine import RulesEngine, RuleResult

# Load the default rules for most tests
DEFAULT_YAML = (
    Path(__file__).resolve().parent.parent / "src" / "flaude" / "rules" / "default.yaml"
)


@pytest.fixture
def engine() -> RulesEngine:
    return RulesEngine.load(DEFAULT_YAML)


class TestSafeReads:
    """Safe read tools should be allowed without any input matching."""

    @pytest.mark.parametrize("tool", ["Read", "Glob", "Grep", "WebSearch", "WebFetch"])
    def test_safe_reads_allowed(self, engine: RulesEngine, tool: str):
        result = engine.evaluate(tool, {})
        assert result.action == "allow"
        assert result.rule_name == "safe_reads"


class TestSafeBash:
    """Known-safe bash commands should be allowed."""

    @pytest.mark.parametrize(
        "cmd", ["git status", "git log --oneline", "ls -la", "cat foo.txt", "pwd"]
    )
    def test_safe_bash_allowed(self, engine: RulesEngine, cmd: str):
        result = engine.evaluate("Bash", {"command": cmd})
        assert result.action == "allow"
        assert result.rule_name == "safe_bash"


class TestDangerousCommands:
    """Extremely dangerous commands should be denied outright."""

    @pytest.mark.parametrize(
        "cmd", ["rm -rf /etc", "mkfs /dev/sda", "dd if=/dev/zero of=/dev/sda"]
    )
    def test_dangerous_denied(self, engine: RulesEngine, cmd: str):
        result = engine.evaluate("Bash", {"command": cmd})
        assert result.action == "deny"
        assert result.rule_name == "block_dangerous"
        assert result.reason == "Extremely dangerous command blocked"

    def test_rm_rf_tmp_not_blocked(self, engine: RulesEngine):
        """rm -rf /tmp should NOT be caught by the dangerous rule (the [^t] exclusion)."""
        result = engine.evaluate("Bash", {"command": "rm -rf /tmp/foo"})
        # Should fall through to destructive_commands (rm -r pattern)
        assert result.action == "ask_dashboard"
        assert result.rule_name == "destructive_commands"


class TestDestructiveCommands:
    """Destructive but not catastrophic commands should require dashboard approval."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "rm -r some_dir",
            "DROP TABLE users",
            "DELETE FROM logs",
            "git push --force origin main",
        ],
    )
    def test_destructive_ask_dashboard(self, engine: RulesEngine, cmd: str):
        result = engine.evaluate("Bash", {"command": cmd})
        assert result.action == "ask_dashboard"
        assert result.timeout == 180


class TestGitPush:
    """Regular git push should require dashboard approval with shorter timeout."""

    def test_git_push_ask_dashboard(self, engine: RulesEngine):
        result = engine.evaluate("Bash", {"command": "git push origin main"})
        assert result.action == "ask_dashboard"
        assert result.rule_name == "git_push"
        assert result.timeout == 60


class TestNoMatch:
    """Unmatched tools should return no_match."""

    def test_unknown_tool(self, engine: RulesEngine):
        result = engine.evaluate("SomeFancyTool", {"input": "whatever"})
        assert result.action == "no_match"
        assert result.rule_name is None

    def test_bash_unknown_command(self, engine: RulesEngine):
        result = engine.evaluate("Bash", {"command": "python3 main.py"})
        assert result.action == "no_match"


class TestFirstMatchWins:
    """Rules are evaluated top-to-bottom; first match wins."""

    def test_order_matters(self):
        """If 'deny' comes before 'allow' for the same tool, deny wins."""
        rules = [
            {
                "name": "deny_first",
                "tools": ["Bash"],
                "match": {"command": "echo"},
                "action": "deny",
            },
            {
                "name": "allow_second",
                "tools": ["Bash"],
                "match": {"command": "echo"},
                "action": "allow",
            },
        ]
        engine = RulesEngine(rules=rules)
        result = engine.evaluate("Bash", {"command": "echo hello"})
        assert result.action == "deny"
        assert result.rule_name == "deny_first"


class TestCwdSubstitution:
    """$CWD in match patterns should be replaced with the escaped cwd value."""

    def test_cwd_match(self):
        rules = [
            {
                "name": "project_files",
                "tools": ["Read"],
                "match": {"file_path": "^$CWD/"},
                "action": "allow",
            },
        ]
        engine = RulesEngine(rules=rules)
        result = engine.evaluate(
            "Read", {"file_path": "/home/user/project/foo.py"}, cwd="/home/user/project"
        )
        assert result.action == "allow"

    def test_cwd_no_match(self):
        rules = [
            {
                "name": "project_files",
                "tools": ["Read"],
                "match": {"file_path": "^$CWD/"},
                "action": "allow",
            },
        ]
        engine = RulesEngine(rules=rules)
        result = engine.evaluate(
            "Read", {"file_path": "/etc/passwd"}, cwd="/home/user/project"
        )
        assert result.action == "no_match"

    def test_cwd_with_special_chars(self):
        """Paths with regex-special chars (like dots) should be escaped properly."""
        rules = [
            {
                "name": "project_files",
                "tools": ["Read"],
                "match": {"file_path": "^$CWD/"},
                "action": "allow",
            },
        ]
        engine = RulesEngine(rules=rules)
        # The dot in "my.project" should be escaped so it doesn't match any char
        result = engine.evaluate(
            "Read",
            {"file_path": "/home/user/myXproject/foo.py"},
            cwd="/home/user/my.project",
        )
        assert result.action == "no_match"


class TestLoadFromYaml:
    """Loading rules from YAML files."""

    def test_load_default_yaml(self):
        engine = RulesEngine.load(DEFAULT_YAML)
        assert len(engine.rules) == 5
        assert engine.defaults["approval_timeout"] == 120

    def test_load_missing_file(self, tmp_path: Path):
        engine = RulesEngine.load(tmp_path / "nonexistent.yaml")
        assert engine.rules == []
        assert engine.defaults == {}

    def test_load_empty_file(self, tmp_path: Path):
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        engine = RulesEngine.load(empty)
        assert engine.rules == []
        assert engine.defaults == {}
