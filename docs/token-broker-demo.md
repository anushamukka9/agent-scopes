# Token broker demo walkthrough

This is the demo from my talk, as code. It lives at
`examples/token_broker_demo.py` and runs with no setup beyond
installing the package:

```bash
python examples/token_broker_demo.py
```

## The setup

A support bot gets one job: answer a question about ticket 4821
and order 551. The policy behind the broker allows exactly three
things for that bot, each read-only and each capped at five
minutes:

- `tickets.lookup` on `tickets/*`
- `orders.status` on `orders/*`
- `kb.search` on `kb/*`

Nothing else exists in the policy. That is the whole point. The
bot does not start with a broad credential and get watched. It
starts with nothing and asks, step by step.

## What happens, step by step

1. The broker mints a ticket lease for `tickets/4821`, read only,
   good for 300 seconds, and single use. The bot holds a token,
   not the ticket record. The record moves only when the tool
   gateway redeems the token inside the tool call.
2. The demo then tries to reuse a ticket token for the orders
   tool. The broker refuses with a scope mismatch, before any
   secret moves. A token for one tool is not a pass for another.
3. The order step gets its own separate lease for `orders/551`
   and redeems it. Two steps, two credentials, neither reusable
   for the other step.
4. Three out-of-task asks are refused at issue time, so no token
   is ever minted: charging billing, writing to the ticket, and
   reading the CRM. Policy denial at issue time is cheaper than
   catching misuse later.
5. The bot asks for a one-hour knowledge base lease. Policy
   quietly clamps it to 300 seconds. The demo advances its fake
   clock by 301 seconds and the redeem then fails as expired.
   A leaked token has a short useful life by construction.

The audit log at the end lists what the broker decided, with no
tokens and no secrets in it.

## What this does not prove

- It does not authenticate the bot. The harness passes the agent
  name in, and authenticating that name is the harness job, as
  the limitations doc says.
- The fake clock makes expiry deterministic for a demo. Real
  runs use wall time.
- The backend here is an in-memory dict with fake records. In
  production that slot is Vault, where redeem is also the moment
  a dynamic secret gets minted at the source.

## Try changing it

- Add a rule for a new tool and watch only that one new ask pass.
- Ask for `tickets/9999` and note that the glob allows it. If a
  task should pin one exact ticket, write the resource without
  the glob. Scope is only as tight as the policy you write.
