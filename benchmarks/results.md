# Benchmark results

Measured on the build machine (this VM, Python 3.12) with
`python benchmarks/bench.py`: median of 5 rounds, 10,000 iterations
per round. Two consecutive runs agreed within a few percent.

| Benchmark | Result |
|---|---|
| Issue lease | 63,383 ops/sec |
| Redeem lease (in-memory backend) | 174,305 ops/sec |
| Validate token | 147,622 ops/sec |

## What this measures, and what it does not

The broker is in-process work: policy matching (fnmatch over a small
rule list), a SHA-256 of the token, dict lookups, and an audit
record. These numbers say scope enforcement will never be the slow
part of a tool call. They say nothing about a real backend: a Vault
redeem is an HTTPS round trip and will be bound by your network and
your Vault, and an env-file redeem is a file/env read. Measure your
backend in your deployment; this library will not be your bottleneck.

The CI smoke test (`python -m agent_scopes.benchmark`) uses fewer
iterations and only checks that the path runs and stays fast enough
to notice a regression, not that these exact numbers hold.

Safe to reproduce the measurement:

```bash
pip install -e .
python benchmarks/bench.py
```
