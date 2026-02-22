"""Rules engine for evaluating tool calls against YAML-defined rules."""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class RuleResult:
    action: str  # "allow", "deny", "ask_dashboard", "no_match"
    rule_name: str | None = None
    reason: str | None = None
    timeout: int | None = None


class RulesEngine:
    def __init__(self, rules: list[dict], defaults: dict | None = None):
        self.rules = rules
        self.defaults = defaults or {}

    @classmethod
    def load(cls, path: Path | None = None) -> "RulesEngine":
        """Load rules from YAML file. Falls back to empty rules if file doesn't exist."""
        from flaude.constants import RULES_PATH

        path = path or RULES_PATH
        if not path.exists():
            return cls(rules=[])
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(
            rules=data.get("rules", []),
            defaults=data.get("defaults", {}),
        )

    def evaluate(self, tool_name: str, tool_input: dict, cwd: str = "") -> RuleResult:
        """Evaluate a tool call against rules. First match wins."""
        for rule in self.rules:
            if not self._tool_matches(rule, tool_name):
                continue
            if not self._input_matches(rule, tool_input, cwd):
                continue
            return RuleResult(
                action=rule["action"],
                rule_name=rule.get("name"),
                reason=rule.get("reason"),
                timeout=rule.get("timeout", self.defaults.get("approval_timeout", 120)),
            )
        return RuleResult(action="no_match")

    def _tool_matches(self, rule: dict, tool_name: str) -> bool:
        tools = rule.get("tools", [])
        return tool_name in tools

    def _input_matches(self, rule: dict, tool_input: dict, cwd: str) -> bool:
        match_spec = rule.get("match")
        if not match_spec:
            return True
        for field, pattern in match_spec.items():
            value = str(tool_input.get(field, ""))
            resolved_pattern = pattern.replace("$CWD", re.escape(cwd))
            try:
                if not re.search(resolved_pattern, value):
                    return False
            except re.error:
                return False
        return True
