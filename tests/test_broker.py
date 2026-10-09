import pytest

from agent_scopes.backends import InMemoryBackend
from agent_scopes.broker import (
    Broker,
    LeaseExpired,
    LeaseRevoked,
    PolicyDenied,
    ScopeMismatch,
    UnknownLease,
)
from agent_scopes.policy import Policy

POLICY_DICT = {
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
            "name": "support-single",
            "agent": "support-bot",
            "tool": "tickets.lookup",
            "resource": "tickets/*",
            "actions": ["read"],
            "max_ttl_seconds": 60,
            "single_use": True,
        },
    ],
}


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_broker(clock=None, backend=None):
    return Broker(
        Policy.from_dict(POLICY_DICT),
        backend or InMemoryBackend({"warehouse/prod": "fake-secret", "tickets/1": "fake-ticket"}),
        clock=clock or Clock(),
    )


def test_issue_and_redeem_happy_path():
    broker = make_broker()
    lease = broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("read",))
    assert lease.token and lease.token.startswith("asc_")
    assert lease.ttl_seconds == 300
    secret = broker.redeem(
        lease.token, tool="warehouse.query", resource="warehouse/prod", action="read"
    )
    assert secret == "fake-secret"


def test_issue_denied_by_default_and_audited():
    broker = make_broker()
    with pytest.raises(PolicyDenied):
        broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("write",))
    assert broker.audit_log[-1].event == "denied"


def test_ttl_clamped_to_rule_cap():
    broker = make_broker()
    lease = broker.issue(
        "support-bot", "tickets.lookup", "tickets/1", actions=("read",), ttl_seconds=3600
    )
    assert lease.ttl_seconds == 60


def test_ttl_request_below_cap_honored():
    broker = make_broker()
    lease = broker.issue(
        "data-analyst", "warehouse.query", "warehouse/prod", actions=("read",), ttl_seconds=30
    )
    assert lease.ttl_seconds == 30


def test_bad_ttl_rejected():
    broker = make_broker()
    with pytest.raises(ValueError):
        broker.issue("data-analyst", "warehouse.query", "warehouse/prod", ttl_seconds=0)


def test_scope_mismatch_on_redeem():
    broker = make_broker()
    lease = broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("read",))
    with pytest.raises(ScopeMismatch):
        broker.redeem(
            lease.token, tool="warehouse.query", resource="warehouse/other", action="read"
        )
    with pytest.raises(ScopeMismatch):
        broker.redeem(lease.token, tool="shell.exec", resource="warehouse/prod", action="read")
    with pytest.raises(ScopeMismatch):
        broker.redeem(
            lease.token, tool="warehouse.query", resource="warehouse/prod", action="write"
        )


def test_unknown_token():
    broker = make_broker()
    with pytest.raises(UnknownLease):
        broker.redeem("asc_nope", tool="warehouse.query", resource="warehouse/prod", action="read")


def test_expiry():
    clock = Clock()
    broker = make_broker(clock=clock)
    lease = broker.issue(
        "data-analyst", "warehouse.query", "warehouse/prod", actions=("read",), ttl_seconds=30
    )
    clock.advance(31)
    assert lease.is_expired(now=clock.now)
    with pytest.raises(LeaseExpired):
        broker.redeem(lease.token, tool="warehouse.query", resource="warehouse/prod", action="read")


def test_revoke_by_token_and_by_id():
    broker = make_broker()
    lease = broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("read",))
    assert broker.revoke(lease.token) is True
    assert broker.revoke(lease.token) is False
    with pytest.raises(LeaseRevoked):
        broker.redeem(lease.token, tool="warehouse.query", resource="warehouse/prod", action="read")
    lease2 = broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("read",))
    assert broker.revoke(lease2.lease_id) is True


def test_single_use_consumed_after_redeem():
    broker = make_broker()
    lease = broker.issue("support-bot", "tickets.lookup", "tickets/1", actions=("read",))
    assert lease.single_use is True
    assert (
        broker.redeem(lease.token, tool="tickets.lookup", resource="tickets/1", action="read")
        == "fake-ticket"
    )
    with pytest.raises(LeaseRevoked):
        broker.redeem(lease.token, tool="tickets.lookup", resource="tickets/1", action="read")


def test_validate_does_not_consume_or_fetch():
    backend = InMemoryBackend({"warehouse/prod": "fake-secret", "tickets/1": "fake-ticket"})
    broker = make_broker(backend=backend)
    lease = broker.issue("support-bot", "tickets.lookup", "tickets/1", actions=("read",))
    checked = broker.validate(
        lease.token, tool="tickets.lookup", resource="tickets/1", action="read"
    )
    assert checked.lease_id == lease.lease_id
    # still redeemable after validate, even on a single-use rule
    assert (
        broker.redeem(lease.token, tool="tickets.lookup", resource="tickets/1", action="read")
        == "fake-ticket"
    )


def test_revoke_all_for_agent():
    broker = make_broker()
    broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("read",))
    broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("read",))
    broker.issue("support-bot", "tickets.lookup", "tickets/1", actions=("read",))
    assert broker.revoke_all(agent="data-analyst") == 2
    assert len(broker.list_leases(agent="support-bot", active_only=True)) == 1


def test_purge_expired():
    clock = Clock()
    broker = make_broker(clock=clock)
    broker.issue(
        "data-analyst", "warehouse.query", "warehouse/prod", actions=("read",), ttl_seconds=10
    )
    clock.advance(20)
    assert broker.purge_expired() == 1
    assert broker.list_leases() == []


def test_credential_context_manager_revokes_on_exit():
    broker = make_broker()
    with broker.credential("data-analyst", "warehouse.query", "warehouse/prod") as secret:
        assert secret == "fake-secret"
    assert broker.list_leases(active_only=True) == []


def test_credential_context_manager_revokes_on_error():
    broker = make_broker()
    with pytest.raises(RuntimeError, match="boom"):
        with broker.credential("data-analyst", "warehouse.query", "warehouse/prod"):
            raise RuntimeError("boom")
    assert broker.list_leases(active_only=True) == []


def test_token_never_in_repr_or_dict():
    broker = make_broker()
    lease = broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("read",))
    assert lease.token not in repr(lease)
    assert "token" not in lease.to_dict()


def test_audit_trail_has_no_secrets_or_tokens():
    broker = make_broker()
    lease = broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("read",))
    broker.redeem(lease.token, tool="warehouse.query", resource="warehouse/prod", action="read")
    events = [e.event for e in broker.audit_log]
    assert events == ["issued", "redeemed"]
    for event in broker.audit_log:
        assert lease.token not in str(event.to_dict())
        assert "fake-secret" not in str(event.to_dict())


def test_string_action_shorthand():
    broker = make_broker()
    lease = broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions="read")
    assert lease.actions == ("read",)
