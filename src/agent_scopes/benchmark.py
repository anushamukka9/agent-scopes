"""CI smoke benchmark: issue, validate, and redeem against memory.

Run with: python -m agent_scopes.benchmark
"""

from __future__ import annotations

import time

from agent_scopes.backends import InMemoryBackend
from agent_scopes.broker import Broker
from agent_scopes.policy import Policy

_POLICY = Policy.from_dict(
    {
        "max_ttl_seconds": 300,
        "rules": [
            {
                "agent": "bench-agent",
                "tool": "warehouse.query",
                "resource": "warehouse/*",
                "actions": ["read"],
                "max_ttl_seconds": 300,
            }
        ],
    }
)


def _broker() -> Broker:
    return Broker(_POLICY, InMemoryBackend({"warehouse/prod": "fake-bench-secret"}))


def bench_issue(iterations: int = 20000) -> float:
    broker = _broker()
    start = time.perf_counter()
    for _ in range(iterations):
        broker.issue("bench-agent", "warehouse.query", "warehouse/prod", actions=("read",))
    elapsed = time.perf_counter() - start
    return iterations / elapsed


def bench_redeem(iterations: int = 20000) -> float:
    broker = _broker()
    tokens = [
        broker.issue("bench-agent", "warehouse.query", "warehouse/prod", actions=("read",)).token
        for _ in range(iterations)
    ]
    start = time.perf_counter()
    for token in tokens:
        assert token is not None
        secret = broker.redeem(
            token, tool="warehouse.query", resource="warehouse/prod", action="read"
        )
        assert secret == "fake-bench-secret"
    elapsed = time.perf_counter() - start
    return iterations / elapsed


def main() -> None:
    issue_ops = bench_issue()
    redeem_ops = bench_redeem()
    print(f"issue throughput: {issue_ops:,.0f} ops/sec")
    print(f"redeem throughput: {redeem_ops:,.0f} ops/sec")
    print("benchmark smoke test passed")


if __name__ == "__main__":
    main()
