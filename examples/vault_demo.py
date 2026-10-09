"""Vault backend demo, with a fake Vault so it runs anywhere.

Run: python examples/vault_demo.py

In production you point VaultBackend at your real Vault address and
leave the transport alone. Here a fake transport answers the two
calls that matter: read a dynamic database credential, then revoke
its lease when the broker lease dies.
"""

from agent_scopes import Broker, Policy, VaultBackend

POLICY = Policy.from_dict(
    {
        "rules": [
            {
                "agent": "data-analyst",
                "tool": "warehouse.query",
                "resource": "db/warehouse-ro",
                "actions": ["read"],
                "max_ttl_seconds": 300,
            }
        ]
    }
)


def fake_vault(method, url, headers, body):
    print(f"vault <- {method} {url.split('/v1/')[-1]}")
    if url.endswith("/database/creds/warehouse-ro"):
        return 200, {
            "data": {"username": "fake-ro-user", "password": "fake-ro-pass"},
            "lease_id": "database/creds/warehouse-ro/demo123",
            "lease_duration": 300,
        }
    if url.endswith("/sys/leases/revoke"):
        return 204, {}
    return 404, {}


backend = VaultBackend(
    "https://vault.example:8200",
    token="fake-vault-token-for-demo",
    mapping={"db/warehouse-ro": "database/creds/warehouse-ro"},
    transport=fake_vault,
)
broker = Broker(POLICY, backend)

lease = broker.issue("data-analyst", "warehouse.query", "db/warehouse-ro", actions=("read",))
creds = broker.redeem(
    lease.token, tool="warehouse.query", resource="db/warehouse-ro", action="read"
)
print(f"dynamic credentials minted at redeem time: {creds}")
broker.revoke(lease.token)
print("broker lease revoked, and the Vault lease went with it.")
print("done.")
