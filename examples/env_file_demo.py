"""Env-file backend demo: the dev setup most people start with.

Run: python examples/env_file_demo.py

Writes a throwaway .env in a temp dir, issues a lease, and redeems it.
The honest caveat, also in docs/backends.md: the secret in the .env
file is still long-lived. This backend shortens how long the agent
holds it. It does not rotate it. Use Vault when that matters.
"""

import tempfile
from pathlib import Path

from agent_scopes import Broker, EnvFileBackend, Policy

POLICY = Policy.from_dict(
    {
        "rules": [
            {
                "agent": "support-bot",
                "tool": "tickets.lookup",
                "resource": "tickets/api",
                "actions": ["read"],
                "max_ttl_seconds": 120,
            }
        ]
    }
)

with tempfile.TemporaryDirectory() as tmp:
    env_path = Path(tmp) / ".env"
    env_path.write_text("TICKETS_API_KEY=fake-tickets-key-for-demo\n", encoding="utf-8")
    backend = EnvFileBackend(path=str(env_path), mapping={"tickets/api": "TICKETS_API_KEY"})
    broker = Broker(POLICY, backend)
    with broker.credential("support-bot", "tickets.lookup", "tickets/api") as secret:
        print(f"inside the tool call, secret in hand: {secret!r}")
    print(f"lease still active after the block? {broker.list_leases(active_only=True)}")
print("done. the context manager revoked the lease on the way out.")
