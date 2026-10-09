# Backends

The broker stores no secrets. At redeem time it asks a backend for
the secret behind a resource name. Which backend you pick decides how
strong the whole setup actually is. Be honest with yourself about
which one you are running.

## InMemoryBackend: tests and demos

```python
InMemoryBackend({"warehouse/prod": "fake-secret"})
```

A dict. Nothing persists, nothing rotates. Useful in tests, and to
see the flow run. Not a production answer.

## EnvFileBackend: local development

```python
EnvFileBackend(
    path=".env",
    mapping={"warehouse/prod": "WAREHOUSE_PASSWORD"},
)
```

Reads a `.env` file first (`KEY=value`, `#` comments, optional
`export `, quotes stripped), then the process environment. The
mapping names which variable holds which resource; without one, the
variable name is derived (`warehouse/prod` reads `WAREHOUSE_PROD`).

The honest part: the secret in that file is long-lived. This backend
does not rotate it and cannot revoke it at the source. What it buys
you is real, but narrow: the agent holds a five-minute scoped token
instead of the password, the password moves only at the moment the
tool runs, and the audit log shows every ask. When the agent's
context leaks (and prompts leak), a dead token leaks. A password
would not have been dead.

## VaultBackend: production

```python
VaultBackend(
    "https://vault.example:8200",
    mapping={
        "app/api-key": "secret/data/app/api-key",
        "db/warehouse-ro": "database/creds/warehouse-ro",
    },
)
```

Stdlib HTTP against the Vault API; the token comes from the
constructor or `VAULT_TOKEN`, and never appears in errors or logs.

Two read shapes, chosen by path:

- KV v2 (`.../data/...`): the stored payload comes back. A single
  string value unwraps to a plain string.
- Dynamic secrets (path with `creds` as the second-to-last segment,
  or any path under `dynamic_prefixes`): the username and password
  come back as a dict, and Vault's own lease id is kept on the broker
  lease. `broker.revoke(...)` then revokes at Vault too, so the
  database credential dies at the source, not just in the broker.

This is the backend where the whole design pays off. Vault mints a
fresh, narrow credential per redeem and can kill it on demand. The
broker is the policy and scope layer in front of it.

## Writing your own

Any object with these two methods is a backend:

```python
def fetch(self, resource, tool=None) -> BackendResult: ...
def revoke(self, lease_ref) -> None: ...   # optional
```

`fetch` returns a `BackendResult(secret, lease_ref=None,
ttl_seconds=None)`. Raise `BackendError` when you cannot produce a
secret, and keep secret values out of the message.
