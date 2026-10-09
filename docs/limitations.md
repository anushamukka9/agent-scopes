# Honest limitations

What this library does not do, stated plainly so nobody finds out
the hard way.

- **The token is a bearer credential.** Whoever holds it can redeem
  it, for its scope, until it expires. Scope and TTL make a leaked
  token a small problem instead of a catastrophic one. They do not
  make it no problem. Bind tokens to a channel or caller identity in
  your gateway if you need more than this.
- **It is a library, not a daemon.** The broker runs in your
  process and trusts it. An agent that can read your process memory
  or call the broker with forged agent names gets what it asks for.
  Agent identity here is a string you supply; authenticating that
  the caller really is that agent is your harness's job (this pairs
  with agent-policy-kit approvals and agent-audit logs in my other
  repos).
- **The env-file backend cannot rotate or revoke at the source.**
  The underlying secret is long-lived; only the agent's window onto
  it is short. Vault dynamic secrets are the backend that fully
  delivers the design. See backends.md.
- **Expiry is lazy.** Nothing sweeps in the background. Expired
  leases fail at validate and redeem time, and `purge_expired()`
  drops the records when you call it. Run it on a timer if you keep
  a file store around.
- **The file store is single-writer.** JSON on disk, write-then-
  rename, fine for a CLI and a demo. Two processes issuing at once
  can race. Put leases behind one service process for real work;
  the in-memory store is per-process by the same token.
- **Policy is allow-list matching, not a policy language.** Globs,
  action lists, TTL caps. No conditions on arguments, time windows,
  or approval state. That is agent-policy-kit's job; this broker
  deliberately stays small.
- **Revocation of a redeemed secret is best-effort.** Once a secret
  has been handed to a tool, the broker cannot unhand it. Vault
  revoke kills the credential at the source; an env-file secret is
  out until you rotate the file. Short TTLs exist precisely because
  this window cannot be closed completely.

None of this makes the library useless. It makes it a window
shortener and a scope enforcer, which is the job most agent setups
actually need done. Claim more than that for it and you will be
disappointed in exactly the ways listed above.
