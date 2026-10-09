import json

import pytest

from agent_scopes.broker import Broker
from agent_scopes.cli import main
from agent_scopes.policy import Policy
from agent_scopes.store import LeaseStore, hash_token

POLICY = {
    "rules": [
        {
            "agent": "data-analyst",
            "tool": "warehouse.query",
            "resource": "warehouse/*",
            "actions": ["read"],
            "max_ttl_seconds": 300,
        }
    ]
}


def test_store_never_persists_raw_token(tmp_path):
    from agent_scopes.backends import InMemoryBackend

    store = LeaseStore.file_backed(tmp_path / "leases.json")
    broker = Broker(
        Policy.from_dict(POLICY), InMemoryBackend({"warehouse/prod": "fake"}), store=store
    )
    lease = broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("read",))
    text = (tmp_path / "leases.json").read_text(encoding="utf-8")
    assert lease.token not in text
    assert hash_token(lease.token) in text
    assert "fake" not in text.split("resource")[0]  # secret never written


def test_store_reload_finds_lease(tmp_path):
    from agent_scopes.backends import InMemoryBackend

    path = tmp_path / "leases.json"
    store = LeaseStore.file_backed(path)
    broker = Broker(
        Policy.from_dict(POLICY), InMemoryBackend({"warehouse/prod": "fake"}), store=store
    )
    lease = broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("read",))
    reloaded = LeaseStore.load(path)
    record = reloaded.get_by_token(lease.token)
    assert record is not None and record.lease_id == lease.lease_id


def _write_cli_files(tmp_path):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(POLICY), encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("WAREHOUSE_PROD=fake-cli-secret\n", encoding="utf-8")
    return policy, env, tmp_path / "leases.json"


def test_cli_issue_redeem_revoke_roundtrip(tmp_path, capsys):
    policy, env, store = _write_cli_files(tmp_path)
    base = ["--policy", str(policy), "--store", str(store), "--env-file", str(env)]
    assert (
        main(
            [
                "issue",
                *base,
                "--agent",
                "data-analyst",
                "--tool",
                "warehouse.query",
                "--resource",
                "warehouse/prod",
            ]
        )
        == 0
    )
    issued = json.loads(capsys.readouterr().out)
    token = issued["token"]
    assert (
        main(
            [
                "validate",
                *base,
                "--token",
                token,
                "--tool",
                "warehouse.query",
                "--resource",
                "warehouse/prod",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "redeem",
                *base,
                "--token",
                token,
                "--tool",
                "warehouse.query",
                "--resource",
                "warehouse/prod",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["secret"] == "fake-cli-secret"
    assert main(["revoke", *base, token]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "redeem",
                *base,
                "--token",
                token,
                "--tool",
                "warehouse.query",
                "--resource",
                "warehouse/prod",
            ]
        )
        == 3
    )


def test_cli_issue_denied_exit_code(tmp_path, capsys):
    policy, env, store = _write_cli_files(tmp_path)
    base = ["--policy", str(policy), "--store", str(store), "--env-file", str(env)]
    code = main(
        [
            "issue",
            *base,
            "--agent",
            "intruder",
            "--tool",
            "warehouse.query",
            "--resource",
            "warehouse/prod",
        ]
    )
    assert code == 2


def test_cli_list_and_purge(tmp_path, capsys):
    policy, env, store = _write_cli_files(tmp_path)
    base = ["--policy", str(policy), "--store", str(store), "--env-file", str(env)]
    assert (
        main(
            [
                "issue",
                *base,
                "--agent",
                "data-analyst",
                "--tool",
                "warehouse.query",
                "--resource",
                "warehouse/prod",
                "--ttl",
                "1",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["list", *base]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1
    assert main(["purge", *base]) == 0


def test_cli_bad_policy_exits(tmp_path):
    with pytest.raises(SystemExit):
        main(
            [
                "list",
                "--policy",
                str(tmp_path / "missing.json"),
                "--store",
                str(tmp_path / "s.json"),
            ]
        )
