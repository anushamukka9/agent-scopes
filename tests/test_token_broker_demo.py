"""The token broker demo does what its walkthrough says it does.

The demo module lives in examples/, so it is loaded by path. Every
refusal the walkthrough promises is asserted here: cross-tool reuse,
out-of-task issues, the TTL clamp, and expiry.
"""

import importlib.util
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "examples" / "token_broker_demo.py"


def load_demo():
    spec = importlib.util.spec_from_file_location("token_broker_demo", DEMO)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_task_succeeds_and_everything_outside_it_fails():
    result = load_demo().run_demo()
    outcomes = result["outcomes"]
    assert outcomes["ticket_redeem"] == "ok"
    assert outcomes["order_redeem"] == "ok"
    assert outcomes["cross_tool_reuse"] == "scope_mismatch"
    assert outcomes["issue_billing.charge"] == "policy_denied"
    assert outcomes["issue_tickets.lookup"] == "policy_denied"
    assert outcomes["issue_crm.customers"] == "policy_denied"
    assert outcomes["expired_redeem"] == "lease_expired"


def test_demo_clamps_a_long_ask_to_five_minutes():
    outcomes = load_demo().run_demo()["outcomes"]
    assert outcomes["kb_ttl_seconds"] == "300"


def test_demo_transcript_names_the_task_and_leaks_no_real_secret_shape():
    transcript = "\n".join(load_demo().run_demo()["transcript"])
    assert "ticket 4821" in transcript
    assert "order 551" in transcript
    # Every secret printed in the demo is labelled fake in the file
    # itself, and the audit line promises no tokens or secrets.
    assert "no tokens or secrets in the log" in transcript
