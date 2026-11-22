"""Token broker demo: one task, small credentials, hard edges.

Run: python examples/token_broker_demo.py

This is the demo I use when I talk about agent-scopes. A support bot
gets one job: answer a question about ticket 4821 and order 551.
For each step of that job the broker mints a separate credential
that is good for one tool, one resource, one action, and five
minutes. Everything outside that task is refused, and the refusal
happens before any secret moves.

The clock here is fake so the demo is deterministic. In a real
harness the broker uses wall time and the five minutes are real.
"""

from __future__ import annotations

from agent_scopes import (
    Broker,
    InMemoryBackend,
    LeaseExpired,
    Policy,
    PolicyDenied,
    ScopeMismatch,
)

TASK_POLICY = Policy.from_dict(
    {
        "max_ttl_seconds": 300,
        "rules": [
            {
                "name": "support bot reads one ticket",
                "agent": "support-bot",
                "tool": "tickets.lookup",
                "resource": "tickets/*",
                "actions": ["read"],
                "max_ttl_seconds": 300,
                "single_use": True,
            },
            {
                "name": "support bot checks one order",
                "agent": "support-bot",
                "tool": "orders.status",
                "resource": "orders/*",
                "actions": ["read"],
                "max_ttl_seconds": 300,
            },
            {
                "name": "support bot searches the knowledge base",
                "agent": "support-bot",
                "tool": "kb.search",
                "resource": "kb/*",
                "actions": ["read"],
                "max_ttl_seconds": 300,
            },
        ],
    }
)

SECRETS = {
    "tickets/4821": "fake-ticket-4821-record",
    "orders/551": "fake-order-551-status",
    "kb/billing": "fake-kb-billing-article",
}


class FakeClock:
    """A clock the demo can advance, so expiry needs no sleeping."""

    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def run_demo() -> dict:
    """Run the whole task and return a transcript plus outcomes.

    Tests use the returned dict. People can just read the transcript.
    """
    clock = FakeClock()
    broker = Broker(TASK_POLICY, InMemoryBackend(dict(SECRETS)), clock=clock)
    lines: list[str] = []
    outcomes: dict[str, str] = {}

    lines.append("task: answer a question about ticket 4821 and order 551")
    lines.append("rule: one credential per step, five minutes, nothing else")

    # Step 1: mint a credential for exactly this ticket, then use it.
    ticket = broker.issue("support-bot", "tickets.lookup", "tickets/4821", actions=("read",))
    lines.append(f"1. minted ticket lease {ticket.lease_id} for {ticket.ttl_seconds:.0f}s")
    secret = broker.redeem(
        ticket.token, tool="tickets.lookup", resource="tickets/4821", action="read"
    )
    lines.append(f"   redeemed inside the tool call: {secret!r} (fake, for the demo)")
    outcomes["ticket_redeem"] = "ok"

    # Step 2: the ticket token is not a general pass. Reusing it for
    # the order tool fails on scope before any secret moves. This
    # lease is single use too, so scope is checked on a live lease
    # by minting a fresh one for the attempt.
    fresh = broker.issue("support-bot", "tickets.lookup", "tickets/4821", actions=("read",))
    try:
        broker.redeem(fresh.token, tool="orders.status", resource="orders/551", action="read")
        outcomes["cross_tool_reuse"] = "allowed"
    except ScopeMismatch as exc:
        lines.append(f"2. ticket token reused for orders correctly refused: {exc}")
        outcomes["cross_tool_reuse"] = "scope_mismatch"

    # Step 3: the order step gets its own separate credential.
    order = broker.issue("support-bot", "orders.status", "orders/551", actions=("read",))
    secret = broker.redeem(order.token, tool="orders.status", resource="orders/551", action="read")
    lines.append(f"3. minted a separate order lease and redeemed it: {secret!r} (fake)")
    outcomes["order_redeem"] = "ok"

    # Step 4: work outside the task never gets a credential at all.
    for tool, resource, action in (
        ("billing.charge", "billing/acme", "charge"),
        ("tickets.lookup", "tickets/4821", "write"),
        ("crm.customers", "crm/acme", "read"),
    ):
        try:
            broker.issue("support-bot", tool, resource, actions=(action,))
            outcomes[f"issue_{tool}"] = "allowed"
        except PolicyDenied:
            lines.append(f"4. {tool} on {resource} ({action}) refused at issue time")
            outcomes[f"issue_{tool}"] = "policy_denied"

    # Step 5: asking for an hour quietly gives five minutes, and
    # five minutes later the token is worthless even if it leaked.
    kb = broker.issue("support-bot", "kb.search", "kb/billing", actions=("read",), ttl_seconds=3600)
    lines.append(f"5. asked for 3600s, got {kb.ttl_seconds:.0f}s (clamped by policy)")
    outcomes["kb_ttl_seconds"] = str(int(kb.ttl_seconds))
    clock.advance(301)
    try:
        broker.redeem(kb.token, tool="kb.search", resource="kb/billing", action="read")
        outcomes["expired_redeem"] = "allowed"
    except LeaseExpired as exc:
        lines.append(f"   after five minutes the kb token is refused: {exc}")
        outcomes["expired_redeem"] = "lease_expired"

    events = [event.event for event in broker.audit_log]
    lines.append(
        "audit: "
        + ", ".join(f"{name} x{events.count(name)}" for name in sorted(set(events)))
        + " (no tokens or secrets in the log)"
    )
    outcomes["audit_events"] = ",".join(sorted(set(events)))
    lines.append("done. the bot finished its task and holds nothing that still works.")
    return {"transcript": lines, "outcomes": outcomes}


def main() -> None:
    for line in run_demo()["transcript"]:
        print(line)


if __name__ == "__main__":
    main()
