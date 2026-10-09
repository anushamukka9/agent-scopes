"""Packaging tests. No tomllib: version is read with a regex fallback
so this file runs unchanged on Python 3.10."""

import re
from pathlib import Path

import agent_scopes

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_text() -> str:
    return (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_version_matches_pyproject():
    text = _pyproject_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None, "no version line found in pyproject.toml"
    assert agent_scopes.__version__ == match.group(1)


def test_console_script_declared():
    text = _pyproject_text()
    assert 'agent-scopes = "agent_scopes.cli:main"' in text


def test_requires_python_310():
    text = _pyproject_text()
    assert 'requires-python = ">=3.10"' in text


def test_public_exports_importable():
    for name in agent_scopes.__all__:
        assert getattr(agent_scopes, name, None) is not None, name


def test_benchmark_smoke():
    from agent_scopes.benchmark import bench_issue, bench_redeem

    assert bench_issue(iterations=200) > 0
    assert bench_redeem(iterations=200) > 0
