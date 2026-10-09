# CLI

The CLI drives the same broker from the shell, for demos and for
harnesses that are not Python. Leases persist in a JSON store file
holding token hashes only, so issue in one process and redeem in the
next works fine.

```bash
# write a policy (see policies.md) and a .env with the dev secrets
agent-scopes issue --policy policy.json --store leases.json --env-file .env \
  --agent data-analyst --tool warehouse.query --resource warehouse/prod
# prints the lease plus the token, once

agent-scopes redeem --policy policy.json --store leases.json --env-file .env \
  --token asc_... --tool warehouse.query --resource warehouse/prod
agent-scopes validate --policy policy.json --store leases.json \
  --token asc_... --tool warehouse.query --resource warehouse/prod
agent-scopes revoke --policy policy.json --store leases.json asc_...
agent-scopes list --policy policy.json --store leases.json --active-only
agent-scopes purge --policy policy.json --store leases.json
```

Details that matter:

- `issue` prints the raw token exactly once, in its JSON output, and
  says so on stderr. If you lose it, the lease is unredeemable; revoke
  it and issue a new one.
- `--map warehouse/prod=WAREHOUSE_PASSWORD` binds a resource to an
  env var name (repeatable). Without it, names are derived.
- `redeem` prints the secret to stdout as JSON. That is the point of
  the command, and it means shell history and logs are your problem
  for exactly that output. Prefer the library in anything real.
- Exit codes: 0 ok, 2 policy denied at issue, 3 for an expired,
  revoked, unknown, or out-of-scope token (and for backend failures
  at redeem).
