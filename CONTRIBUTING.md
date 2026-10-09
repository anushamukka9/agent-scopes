# Contributing to agent-scopes

Thanks for considering a contribution. This is a small, focused library
and we want to keep it that way.

## What fits here

- New backends with adversarial tests: show the failure mode that must
  not leak a secret alongside the happy path that must work.
- Policy matching people actually need, with docs and tests.
- Docs, examples, and benchmark additions.

## What does not fit

- A network service, a hosted dashboard, or anything that phones home.
  The broker is a library on purpose.
- Dependencies in the core. It is stdlib-only and it should stay that
  way. YAML support rides an optional extra, and that is the model
  for anything similar.
- Anything that stores secrets. The broker stores token hashes and
  lease metadata. A contribution that persists secret values, in any
  file, cache, or log, will be declined regardless of intent.

## How to contribute

1. Fork the repo and create a branch: `git checkout -b fix/short-desc`.
2. Add your change plus tests. Backend work needs adversarial tests:
   the near-miss that must not fire alongside the shape that must.
3. Run the gates: `pytest` and `ruff check` / `ruff format --check`.
   Both must be clean.
4. Write your feature's limitations honestly. Every part of this
   library documents what it cannot do. That is a requirement, not a
   suggestion.
5. Open a PR with a short description: what it does, why, and the test
   evidence. Keep the human voice: plain sentences, no hype.

## A note on example secrets

GitHub's secret scanner blocks pushes containing real provider key
formats, even obviously fake ones. If a test fixture or example needs
a secret-shaped value, keep it clearly fake (`fake-...` values, or a
value built in code) and never in a real provider's exact format.
Do not disable push protection to land a fixture.

## Style

- Python 3.10+, `src/` layout, type hints on public APIs.
- Line length 100, ruff-enforced.
- No em-dashes anywhere. This is a hard rule for this repo.
- Commit messages in imperative mood: `fix: clamp TTL to the rule cap`,
  not `fixed TTL clamping`.
