"""Extended benchmarks for agent-scopes. Prints measured numbers.

Run: python benchmarks/bench.py
Record the output in benchmarks/results.md.
"""

from __future__ import annotations

import statistics
import time

from agent_scopes.backends import InMemoryBackend
from agent_scopes.broker import Broker
from agent_scopes.policy import Policy

POLICY = Policy.from_dict(
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


def _time(fn, iterations: int, rounds: int = 5) -> float:
    samples = []
    for _ in range(rounds):
        start = time.perf_counter()
        for _ in range(iterations):
            fn()
        samples.append(iterations / (time.perf_counter() - start))
    return statistics.median(samples)


def main() -> None:
    broker = Broker(POLICY, InMemoryBackend({"warehouse/prod": "fake-bench-secret"}))
    issue = _time(
        lambda: broker.issue("bench-agent", "warehouse.query", "warehouse/prod", actions=("read",)),
        10000,
    )
    total = 10000 * 5
    tokens = [
        broker.issue("bench-agent", "warehouse.query", "warehouse/prod", actions=("read",)).token
        for _ in range(total)
    ]
    it = iter(tokens)
    redeem = _time(
        lambda: broker.redeem(
            next(it), tool="warehouse.query", resource="warehouse/prod", action="read"
        ),
        10000,
    )
    tokens2 = [
        broker.issue("bench-agent", "warehouse.query", "warehouse/prod", actions=("read",)).token
        for _ in range(total)
    ]
    it2 = iter(tokens2)
    validate = _time(
        lambda: broker.validate(
            next(it2), tool="warehouse.query", resource="warehouse/prod", action="read"
        ),
        10000,
    )
    print(f"issue lease:    {issue:>12,.0f} ops/sec")
    print(f"redeem lease:   {redeem:>12,.0f} ops/sec")
    print(f"validate token: {validate:>12,.0f} ops/sec")
    print("done")


if __name__ == "__main__":
    main()
