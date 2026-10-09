import pytest

from agent_scopes.policy import Policy, PolicyError

BASE = {
    "max_ttl_seconds": 300,
    "rules": [
        {
            "name": "analyst-read",
            "agent": "data-analyst",
            "tool": "warehouse.query",
            "resource": "warehouse/*",
            "actions": ["read"],
            "max_ttl_seconds": 300,
        },
        {
            "name": "deploy",
            "agent": "deploy-bot",
            "tool": "deploy.*",
            "resource": "prod/*",
            "actions": ["deploy", "rollback"],
            "max_ttl_seconds": 120,
            "single_use": True,
        },
    ],
}


def test_authorize_exact_and_glob():
    policy = Policy.from_dict(BASE)
    assert policy.authorize("data-analyst", "warehouse.query", "warehouse/prod", ("read",))
    assert policy.authorize("deploy-bot", "deploy.api", "prod/api", ("deploy",))


def test_authorize_denies_by_default():
    policy = Policy.from_dict(BASE)
    assert policy.authorize("data-analyst", "warehouse.query", "warehouse/prod", ("write",)) is None
    assert policy.authorize("nobody", "warehouse.query", "warehouse/prod", ("read",)) is None
    assert policy.authorize("data-analyst", "shell.exec", "warehouse/prod", ("read",)) is None
    assert policy.authorize("data-analyst", "warehouse.query", "other/prod", ("read",)) is None


def test_authorize_needs_all_actions_in_one_rule():
    policy = Policy.from_dict(BASE)
    assert policy.authorize("deploy-bot", "deploy.api", "prod/api", ("deploy", "rollback"))
    assert policy.authorize("deploy-bot", "deploy.api", "prod/api", ("deploy", "delete")) is None


def test_wildcard_action():
    policy = Policy.from_dict(
        {"rules": [{"agent": "a", "tool": "t", "resource": "r", "actions": ["*"]}]}
    )
    assert policy.authorize("a", "t", "r", ("anything",))


def test_list_top_level_and_string_action():
    policy = Policy.from_dict([{"agent": "a", "tool": "t", "resource": "r", "actions": "read"}])
    assert policy.authorize("a", "t", "r", ("read",))


def test_json_roundtrip():
    assert Policy.from_json(__import__("json").dumps(BASE)).to_dict()["rules"][0]["name"]


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"rules": []},
        {"rules": [{"tool": "t", "resource": "r", "actions": ["read"]}]},
        {"rules": [{"agent": "a", "tool": "t", "resource": "r", "actions": []}]},
        {
            "rules": [
                {
                    "agent": "a",
                    "tool": "t",
                    "resource": "r",
                    "actions": ["read"],
                    "max_ttl_seconds": 0,
                }
            ]
        },
        {
            "rules": [{"agent": "a", "tool": "t", "resource": "r", "actions": ["read"]}],
            "max_ttl_seconds": -1,
        },
        {"rules": ["nope"]},
    ],
)
def test_malformed_policies_raise(bad):
    with pytest.raises(PolicyError):
        Policy.from_dict(bad)


def test_invalid_json_raises():
    with pytest.raises(PolicyError):
        Policy.from_json("{not json")


def test_yaml_policy_when_available():
    yaml = pytest.importorskip("yaml")  # noqa: F841
    text = """
max_ttl_seconds: 300
rules:
  - agent: data-analyst
    tool: warehouse.query
    resource: "warehouse/*"
    actions: [read]
"""
    policy = Policy.from_yaml(text)
    assert policy.authorize("data-analyst", "warehouse.query", "warehouse/x", ("read",))
