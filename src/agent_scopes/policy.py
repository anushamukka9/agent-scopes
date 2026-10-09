"""Policies: who may ask for what, for how long.

A policy is a list of rules. Each rule names an agent (glob), a tool
(glob), a resource (glob), the actions allowed, and a maximum TTL in
seconds. Nothing is allowed unless a rule matches. That is the whole
point: deny by default, then open exactly the holes you mean to open.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path


class PolicyError(ValueError):
    """Raised when a policy document is malformed."""


@dataclass(frozen=True)
class PolicyRule:
    """One allow rule. Globs follow fnmatch rules (`*`, `?`, `[seq]`)."""

    agent: str
    tool: str
    resource: str
    actions: tuple[str, ...]
    max_ttl_seconds: int = 300
    single_use: bool = False
    name: str = ""

    def matches(self, agent: str, tool: str, resource: str, actions: tuple[str, ...]) -> bool:
        if not fnmatch.fnmatchcase(agent, self.agent):
            return False
        if not fnmatch.fnmatchcase(tool, self.tool):
            return False
        if not fnmatch.fnmatchcase(resource, self.resource):
            return False
        for action in actions:
            if action in self.actions or "*" in self.actions:
                continue
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "agent": self.agent,
            "tool": self.tool,
            "resource": self.resource,
            "actions": list(self.actions),
            "max_ttl_seconds": self.max_ttl_seconds,
            "single_use": self.single_use,
        }


def _rule_from_dict(raw: object, index: int) -> PolicyRule:
    if not isinstance(raw, dict):
        raise PolicyError(f"rule {index} must be an object, got {type(raw).__name__}")
    for key in ("agent", "tool", "resource", "actions"):
        if key not in raw:
            raise PolicyError(f"rule {index} is missing required key {key!r}")
    actions = raw["actions"]
    if isinstance(actions, str):
        actions = [actions]
    if not isinstance(actions, list) or not actions:
        raise PolicyError(f"rule {index}: actions must be a non-empty list")
    max_ttl = raw.get("max_ttl_seconds", 300)
    if not isinstance(max_ttl, int) or isinstance(max_ttl, bool) or max_ttl <= 0:
        raise PolicyError(f"rule {index}: max_ttl_seconds must be a positive integer")
    return PolicyRule(
        agent=str(raw["agent"]),
        tool=str(raw["tool"]),
        resource=str(raw["resource"]),
        actions=tuple(str(a) for a in actions),
        max_ttl_seconds=max_ttl,
        single_use=bool(raw.get("single_use", False)),
        name=str(raw.get("name", "")),
    )


@dataclass(frozen=True)
class Policy:
    """An ordered set of allow rules, checked in order. No match, no lease."""

    rules: tuple[PolicyRule, ...] = field(default_factory=tuple)
    max_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not isinstance(self.max_ttl_seconds, int) or self.max_ttl_seconds <= 0:
            raise PolicyError("max_ttl_seconds must be a positive integer")

    @classmethod
    def from_dict(cls, data: object) -> Policy:
        if isinstance(data, list):
            data = {"rules": data}
        if not isinstance(data, dict):
            raise PolicyError("policy must be an object with a rules list")
        raw_rules = data.get("rules")
        if not isinstance(raw_rules, list) or not raw_rules:
            raise PolicyError("policy needs a non-empty rules list")
        rules = tuple(_rule_from_dict(r, i) for i, r in enumerate(raw_rules))
        max_ttl = data.get("max_ttl_seconds", 300)
        if not isinstance(max_ttl, int) or isinstance(max_ttl, bool) or max_ttl <= 0:
            raise PolicyError("max_ttl_seconds must be a positive integer")
        return cls(rules=rules, max_ttl_seconds=max_ttl)

    @classmethod
    def from_json(cls, text: str) -> Policy:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PolicyError(f"invalid JSON policy: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def from_yaml(cls, text: str) -> Policy:
        try:
            import yaml
        except ImportError as exc:
            raise PolicyError(
                "YAML policies need the yaml extra: pip install 'agent-scopes[yaml]'"
            ) from exc
        data = yaml.safe_load(text)
        return cls.from_dict(data)

    @classmethod
    def load(cls, path: str | Path) -> Policy:
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() in {".yaml", ".yml"}:
            return cls.from_yaml(text)
        return cls.from_json(text)

    def authorize(
        self, agent: str, tool: str, resource: str, actions: tuple[str, ...]
    ) -> PolicyRule | None:
        """Return the first rule that allows this request, or None."""
        for rule in self.rules:
            if rule.matches(agent, tool, resource, actions):
                return rule
        return None

    def to_dict(self) -> dict:
        return {
            "max_ttl_seconds": self.max_ttl_seconds,
            "rules": [r.to_dict() for r in self.rules],
        }
