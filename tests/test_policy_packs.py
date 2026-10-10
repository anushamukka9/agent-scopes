"""The shipped policy packs behave the way their docs promise.

Each pack is loaded from its YAML file, then exercised through the
broker: the allows the pack documents must issue, and the denies the
"deliberately absent" blocks promise must raise PolicyDenied.
"""

from pathlib import Path

import pytest

from agent_scopes import Broker, InMemoryBackend, LeaseRevoked, Policy, PolicyDenied

POLICIES = Path(__file__).resolve().parent.parent / "examples" / "policies"


def load_pack(name: str) -> Policy:
    return Policy.load(POLICIES / name)


def broker_for(policy: Policy) -> Broker:
    return Broker(policy, InMemoryBackend({}))


def test_packs_load_and_have_rules():
    for name in (
        "read-only-data-analyst.yaml",
        "deploy-bot.yaml",
        "customer-support.yaml",
    ):
        policy = load_pack(name)
        assert len(policy.rules) >= 3, name
        assert policy.max_ttl_seconds > 0


def test_data_analyst_reads_but_never_writes():
    policy = load_pack("read-only-data-analyst.yaml")
    assert policy.authorize("data-analyst", "warehouse.query", "warehouse/prod", ("read",))
    assert policy.authorize("data-analyst", "warehouse.history", "warehouse/eu", ("read",))
    assert policy.authorize("data-analyst", "exports.read", "exports/analyst/q3", ("read",))
    for tool, resource, actions in (
        ("warehouse.query", "warehouse/prod", ("write",)),
        ("warehouse.write", "warehouse/prod", ("write",)),
        ("warehouse.admin", "warehouse/prod", ("read",)),
        ("etl.trigger", "etl/nightly", ("run",)),
        ("exports.read", "exports/shared/all", ("read",)),
    ):
        assert policy.authorize("data-analyst", tool, resource, actions) is None


def test_deploy_bot_staging_deploy_is_one_shot_and_short():
    policy = load_pack("deploy-bot.yaml")
    broker = broker_for(policy)
    assert policy.authorize("deploy-bot", "releases.plan", "releases/v2.4", ("read",))
    lease = broker.issue(
        "deploy-bot", "releases.deploy", "releases/staging/v2.4", actions=("deploy",)
    )
    assert lease.single_use
    assert lease.ttl_seconds <= 60
    # Asking for an hour on a one-minute rule quietly gives a minute.
    long_ask = broker.issue(
        "deploy-bot",
        "releases.deploy",
        "releases/staging/v2.5",
        actions=("deploy",),
        ttl_seconds=3600,
    )
    assert long_ask.ttl_seconds <= 60
    # Production deploys are not in this pack at all.
    with pytest.raises(PolicyDenied):
        broker.issue("deploy-bot", "releases.deploy", "releases/prod/v2.4", actions=("deploy",))
    with pytest.raises(PolicyDenied):
        broker.issue("deploy-bot", "releases.delete", "releases/staging/v2.4", actions=("delete",))


def test_customer_support_stays_away_from_pii_and_money():
    policy = load_pack("customer-support.yaml")
    broker = broker_for(policy)
    assert policy.authorize("support-bot", "tickets.lookup", "tickets/4821", ("read",))
    assert policy.authorize("support-bot", "kb.search", "kb/billing", ("read",))
    assert policy.authorize("support-bot", "refunds.quote", "refunds/9917", ("read",))
    assert policy.authorize("support-bot", "orders.status", "orders/551", ("read",))
    # Raw PII stores, money movement, and sending replies: absent by design.
    for tool, resource, actions in (
        ("crm.customers", "crm/acme", ("read",)),
        ("crm.export", "crm/all", ("read",)),
        ("billing.charge", "billing/acme", ("charge",)),
        ("refunds.issue", "refunds/9917", ("issue",)),
        ("tickets.reply", "tickets/4821", ("write",)),
    ):
        assert policy.authorize("support-bot", tool, resource, actions) is None
        with pytest.raises(PolicyDenied):
            broker.issue("support-bot", tool, resource, actions=actions)


def test_single_use_leases_die_after_one_redeem():
    policy = load_pack("customer-support.yaml")
    backend = InMemoryBackend({"tickets/4821": "masked-ticket-record"})
    broker = Broker(policy, backend)
    lease = broker.issue("support-bot", "tickets.lookup", "tickets/4821", actions=("read",))
    assert (
        broker.redeem(lease.token, tool="tickets.lookup", resource="tickets/4821", action="read")
        == "masked-ticket-record"
    )
    with pytest.raises(LeaseRevoked):
        broker.redeem(lease.token, tool="tickets.lookup", resource="tickets/4821", action="read")
