# Policy packs

Real-world starting points I actually use. Copy one, rename the
agent, tighten the resource globs to your names, and you have a
least-privilege credential policy for that role. Every pack follows
the same discipline: deny by default, the smallest TTL the job
allows, single-use for anything dangerous, and a comment block naming
what is deliberately absent and why.

| Pack | Agent | Idea |
|---|---|---|
| [read-only-data-analyst.yaml](read-only-data-analyst.yaml) | `data-analyst` | Reads the warehouse and its own export sandbox. No write rule exists anywhere, so writes fail closed. |
| [deploy-bot.yaml](deploy-bot.yaml) | `deploy-bot` | Reads CI, artifacts, and dry-run plans freely. Staging deploys are single-use, sixty-second leases issued only after a human approves the plan. Prod is a separate policy. |
| [customer-support.yaml](customer-support.yaml) | `support-bot` | Ticket lookups, KB search, refund quotes, order status. Raw-PII tools and money movement are absent by design. |

## Loading a pack

```python
from agent_scopes import Policy

policy = Policy.load("examples/policies/deploy-bot.yaml")
# .json works too; the parser is picked from the extension.
```

YAML packs need the yaml extra: `pip install "agent-scopes[yaml]"`.

## Adapting a pack

1. Copy the file next to your service code and rename it.
2. Rename the `agent:` values to your agent identities.
3. Replace the `resource:` globs with your real resource names
   (`warehouse/prod` becomes whatever your warehouse calls itself).
4. Point the broker at your backend (`InMemoryBackend` for a spike,
   `VaultBackend` when it matters; see `docs/backends.md`).
5. Read the "Deliberately absent" block at the bottom of each file
   before you add anything to it. If you find yourself adding the
   thing the block warns about, that is the moment to stop and think
   about whether you need a second agent identity instead.

## Two honest boundaries

**Approval lives in your harness, not in the policy.** The deploy-bot
pack assumes a human approves the plan before the harness mints the
deploy lease. agent-scopes makes that lease one-shot and short; it
does not run your approval queue. If you want policy-driven approval
workflows, pair this with
[agent-policy-kit](https://github.com/anushamukka9/agent-policy-kit).

**Masking lives in your tools, not in the policy.** The
customer-support pack keeps the bot away from raw-PII tools, but the
tools it can reach must mask PII themselves. Policy controls who
reaches what; the tool decides what the response contains. If you
need output-side guarantees too, that is what
[output-contracts](https://github.com/anushamukka9/output-contracts)
is for.
