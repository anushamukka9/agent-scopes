# agent-scopes

Short-lived scoped credentials for AI agents. A tool call gets a
credential valid for that tool, that resource, and five minutes.
Then it dies. The agent never holds the long-lived secret.

## Why this exists

Every agent I run needs secrets. The warehouse password, the tickets
API key, the deploy token. And the way we usually hand those over is
awful: the whole key goes into the agent's environment or its prompt
context, where it sits for the entire session, usable for anything,
readable by anything the agent reads, and one prompt injection away
from leaving the building.

I kept coming back to how we solved this for people. Nobody gives an
employee the root database password. They get a scoped login that
expires. Agents deserve the same treatment, and mostly they do not
get it, because there was no small library in the middle. So I built
the middle.

agent-scopes is a broker. The agent asks: may I use this tool, on
this resource, for this action? Policy answers yes or no. If yes, the
agent gets a random token bound to exactly that ask, good for five
minutes by default. The real secret moves once, at the moment the
tool actually runs, when the tool gateway redeems the token. Wrong
tool, wrong resource, expired token: no secret moves.

It pairs with my other repos: llm-sentinel guards what goes into the
model, agent-policy-kit decides what the agent may do,
agent-audit keeps the tamper-evident record, and agent-scopes makes
sure the credential behind an allowed action is small and short.

## Quickstart

```bash
pip install agent-scopes
```

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

Thirty seconds, start to finish. The agent held a token; the secret
moved inside the tool call. See [docs/quickstart.md](docs/quickstart.md),
[examples/quickstart.py](examples/quickstart.py), and
[examples/example_policy.json](examples/example_policy.json).

## Policy packs

Copy-paste starting points for the roles I keep writing by hand: a
read-only data analyst, a deploy bot whose staging deploys need a
human-approved one-shot lease, and a customer-support bot that stays
away from raw PII and money movement. Each pack names what it
deliberately leaves out and why. See
[examples/policies/](examples/policies/).

## What it does

**Scoped leases.** One lease binds one agent, one tool, one concrete
resource, and a set of actions. Policy matches with globs at issue
time; the lease itself is pinned to the exact values it was minted
for. A lease for `warehouse/prod` never redeems for `warehouse/eu`.

**Short lives, clamped.** Five minutes by default. The effective TTL
is the smallest of your request, the broker cap, the policy cap, and
the rule cap, so a broad rule can never quietly mint a long lease.
Rules can also demand single-use: the lease dies after one redeem.

**Pluggable backends.** Where the secret actually lives is your
choice (details in [docs/backends.md](docs/backends.md)):

- `InMemoryBackend` for tests and demos.
- `EnvFileBackend` for local dev: reads a `.env` file or the process
  environment. The broker shortens the agent's window; the secret
  itself stays long-lived, and the docs say so plainly.
- `VaultBackend` for production: HashiCorp Vault KV v2 reads and
  dynamic database credentials over plain HTTP, no extra
  dependencies. When Vault mints its own lease, broker revoke takes
  it back at Vault too.

**Audit trail.** Every issue, redeem, denial, and revoke lands in
`broker.audit_log` (or your sink). Tokens and secrets never appear
in it.

**A CLI** for shell-driven harnesses and demos, with a file store
that keeps token hashes only. See [docs/cli.md](docs/cli.md).

## Benchmarks

Measured on this machine (see [benchmarks/results.md](benchmarks/results.md)
for the setup). The broker is in-process dict work plus a hash; the
interesting number is how cheap scope enforcement is per tool call.

| Benchmark | Result |
|---|---|
| Issue lease | 63,383 ops/sec |
| Redeem lease (in-memory backend) | 174,305 ops/sec |
| Validate token | 147,622 ops/sec |

Real runs against a network backend are bound by that backend, not
by this library.

## Honest limitations

- The token is a bearer credential for its short life. Scope and TTL
  shrink a leak; they do not erase it.
- This is a library, not a daemon. It trusts the process it runs in,
  and the agent name you pass it. Authenticating the agent is your
  harness's job.
- The env-file backend cannot rotate or revoke the underlying
  secret. Vault dynamic secrets are the backend that fully delivers
  the design.
- Expiry is checked lazily at redeem time. Nothing sweeps in the
  background unless you call `purge_expired()`.

Full list in [docs/limitations.md](docs/limitations.md). Read it
before you rely on this.

## Companions

- [llm-sentinel](https://github.com/anushamukka9/llm-sentinel) guards prompts going in.
- [agent-policy-kit](https://github.com/anushamukka9/agent-policy-kit) decides what agents may do.
- [agent-audit](https://github.com/anushamukka9/agent-audit) keeps the tamper-evident record.
- [mcp-audit](https://github.com/anushamukka9/mcp-audit) audits MCP server surfaces.
- [output-contracts](https://github.com/anushamukka9/output-contracts) guards tool outputs coming out.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Small and focused stays
small and focused: new backends need adversarial tests, every
feature documents what it cannot do, and there are no em-dashes in
this repo.

## License

MIT. See [LICENSE](LICENSE).
