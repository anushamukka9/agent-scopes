# Policies

A policy answers three questions for every tool call: may this agent
use this tool on this resource, for which actions, and for how long.
Deny by default. A request with no matching rule gets nothing.

## Shape

```json
{
  "max_ttl_seconds": 300,
  "rules": [
    {
      "name": "anything human-readable, optional",
      "agent": "data-analyst",
      "tool": "warehouse.query",
      "resource": "warehouse/*",
      "actions": ["read"],
      "max_ttl_seconds": 300,
      "single_use": false
    }
  ]
}
```

The same document works as YAML with the `yaml` extra installed.
`Policy.load("policy.json")` and `Policy.load("policy.yaml")` pick
the parser from the file extension.

## Fields

- `agent`, `tool`, `resource`: fnmatch globs. `warehouse/*` matches
  `warehouse/prod` and `warehouse/eu`, not `billing/prod`.
- `actions`: the actions this rule allows. One action or `"*"` for
  all. A lease asking for several actions needs one rule that covers
  every one of them; rules do not combine.
- `max_ttl_seconds` (per rule): the longest lease this rule will mint.
- `single_use` (per rule): the lease dies after its first redeem.
  Right for deploys, sends, and anything that should happen once.
- `max_ttl_seconds` (top level): a policy-wide cap that no rule can
  exceed in practice, because TTL is clamped to the smallest cap in
  play (see below).

## TTL clamping, exactly

When you issue a lease, the effective TTL is the smallest of:

1. the TTL you asked for (or the broker default, 300 seconds),
2. the broker's `max_ttl_seconds` (300 by default),
3. the policy's `max_ttl_seconds`,
4. the matched rule's `max_ttl_seconds`.

Asking for an hour on a five-minute rule quietly gives you five
minutes, and the lease says so in `expires_at`. Check the lease, not
your request, when the lifetime matters.

## Rules are checked in order

The first matching rule wins. Put narrow rules before broad ones.
Two rules for the same agent and tool with different resources are
fine; a lease still needs the one rule that covers its whole ask.

## What a lease binds

Policy matches with globs. The lease does not. A lease issued for
`warehouse/prod` redeems only for `warehouse/prod`, never for
`warehouse/eu`, even though the same rule would have allowed issuing
one for it. Globs open the door at issue time; the lease itself is
pinned to the concrete tool, resource, and actions it was minted for.
