# Quickstart

## Install

```bash
pip install agent-scopes
pip install "agent-scopes[yaml]"   # only if your policies are YAML
```

## The thirty-second version

```python
from agent_scopes import Broker, InMemoryBackend, Policy

policy = Policy.from_dict({
    "rules": [{
        "agent": "data-analyst",
        "tool": "warehouse.query",
        "resource": "warehouse/*",
        "actions": ["read"],
        "max_ttl_seconds": 300,
    }],
})
broker = Broker(policy, InMemoryBackend({"warehouse/prod": "the-real-secret"}))

lease = broker.issue("data-analyst", "warehouse.query", "warehouse/prod")
secret = broker.redeem(lease.token, tool="warehouse.query",
                       resource="warehouse/prod", action="read")
```

The agent holds `lease.token`. The secret moves only in that last
call, inside the tool, for the exact scope the lease was minted for.

## The context manager, for most tool calls

```python
with broker.credential("data-analyst", "warehouse.query", "warehouse/prod") as secret:
    run_query(secret, sql)
```

Issue, redeem, revoke, handled. If the block raises, the lease is
still revoked on the way out.

## What fails, and how

- No policy rule matches at issue time: `PolicyDenied`. Nothing is minted.
- Token presented for a different tool, resource, or action at
  redeem time: `ScopeMismatch`. Nothing is fetched.
- Token past its expiry: `LeaseExpired`. Token revoked or already
  consumed by a single-use rule: `LeaseRevoked`. Unknown token:
  `UnknownLease`.
- Backend cannot produce the secret: `BackendError`, with no secret
  material in the message.

Every denial lands in `broker.audit_log` (or your `audit_sink`) with
the agent, tool, resource, and action. Never the token, never the
secret.

## Next

- [policies.md](policies.md): rule reference and TTL clamping.
- [backends.md](backends.md): env-file for dev, Vault for production.
- [cli.md](cli.md): the same flow from the shell.
- [limitations.md](limitations.md): what this does not do. Read it.
