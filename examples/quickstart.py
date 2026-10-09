"""Thirty-second demo: issue a scoped lease, redeem it, watch it die.

Run: python examples/quickstart.py

The agent asks for a credential for one tool and one resource. The
broker checks policy, mints a five-minute token, and the real secret
only moves at redeem time, inside the tool call. Wrong scope, expired
token, revoked token: every one of those fails closed.
"""

from agent_scopes import Broker, InMemoryBackend, LeaseExpired, Policy, ScopeMismatch

POLICY = Policy.from_dict(
    {
        "max_ttl_seconds": 300,
        "rules": [
            {
                "name": "analyst reads the warehouse",
                "agent": "data-analyst",
                "tool": "warehouse.query",
                "resource": "warehouse/*",
                "actions": ["read"],
                "max_ttl_seconds": 300,
            }
        ],
    }
)

# In real life this is Vault. In the demo it is a dict.
backend = InMemoryBackend({"warehouse/prod": "fake-warehouse-password"})
broker = Broker(POLICY, backend)

# 1. Issue: the agent gets a token, not the password.
lease = broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("read",))
print(f"issued {lease.lease_id} for {lease.ttl_seconds:.0f}s, token {lease.token[:12]}...")

# 2. Wrong scope fails before any secret moves.
try:
    broker.redeem(lease.token, tool="warehouse.query", resource="billing/prod", action="read")
except ScopeMismatch as exc:
    print(f"wrong resource correctly denied: {exc}")

# 3. Redeem: the right tool, resource, and action get the secret.
secret = broker.redeem(
    lease.token, tool="warehouse.query", resource="warehouse/prod", action="read"
)
print(f"redeemed inside the tool call: {secret!r} (fake, for the demo)")

# 4. Asking for more than policy allows never even gets a token.
try:
    broker.issue("data-analyst", "warehouse.query", "warehouse/prod", actions=("write",))
except Exception as exc:
    print(f"write correctly denied at issue time: {type(exc).__name__}")

# 5. Five minutes later the token is worthless, even if it leaked.
import time as _time

short = broker.issue(
    "data-analyst", "warehouse.query", "warehouse/prod", actions=("read",), ttl_seconds=1
)
_time.sleep(1.1)
try:
    broker.redeem(short.token, tool="warehouse.query", resource="warehouse/prod", action="read")
except LeaseExpired as exc:
    print(f"expired token correctly rejected: {exc}")

print("done. the long-lived password never left the backend until redeem, and only for read.")
