"""Command line interface: the `agent-scopes` console script.

The CLI is a thin shell over the broker for the demo and for shell
driven harnesses. Leases persist in a JSON store file (token hashes
only, no secrets, no raw tokens), so issue in one process and redeem
in another works. The raw token prints exactly once, at issue time.
"""

from __future__ import annotations

import argparse
import json
import sys

from agent_scopes import __version__
from agent_scopes.backends import BackendError, EnvFileBackend
from agent_scopes.broker import AgentScopesError, Broker, PolicyDenied
from agent_scopes.policy import Policy, PolicyError
from agent_scopes.store import LeaseStore

EXIT_OK = 0
EXIT_DENIED = 2
EXIT_DEAD = 3


def _parse_maps(pairs: list[str] | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"--map expects RESOURCE=ENV_VAR, got {pair!r}")
        key, _, value = pair.partition("=")
        mapping[key] = value
    return mapping


def _broker(args: argparse.Namespace, need_backend: bool) -> Broker:
    try:
        policy = Policy.load(args.policy)
    except (OSError, PolicyError) as exc:
        raise SystemExit(f"cannot load policy: {exc}") from exc
    backend = EnvFileBackend(
        path=getattr(args, "env_file", None),
        mapping=_parse_maps(getattr(args, "map", None)),
    )
    store = LeaseStore.file_backed(args.store)
    return Broker(policy, backend, store=store)


def _lease_json(obj) -> str:
    return json.dumps(obj, indent=2)


def cmd_issue(args: argparse.Namespace) -> int:
    broker = _broker(args, need_backend=False)
    actions = tuple(a.strip() for a in args.action.split(",") if a.strip())
    try:
        lease = broker.issue(
            agent=args.agent,
            tool=args.tool,
            resource=args.resource,
            actions=actions,
            ttl_seconds=args.ttl,
            single_use=args.single_use,
        )
    except PolicyDenied as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_DENIED
    payload = lease.to_dict()
    payload["token"] = lease.token
    print(_lease_json(payload))
    print("token shown once. store it like a password, briefly.", file=sys.stderr)
    return EXIT_OK


def cmd_redeem(args: argparse.Namespace) -> int:
    broker = _broker(args, need_backend=True)
    try:
        secret = broker.redeem(
            args.token, tool=args.tool, resource=args.resource, action=args.action
        )
    except AgentScopesError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_DEAD
    except BackendError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_DEAD
    print(_lease_json({"secret": secret}))
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    broker = _broker(args, need_backend=False)
    try:
        lease = broker.validate(
            args.token, tool=args.tool, resource=args.resource, action=args.action
        )
    except AgentScopesError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_DEAD
    print(_lease_json(lease.to_dict()))
    return EXIT_OK


def cmd_revoke(args: argparse.Namespace) -> int:
    broker = _broker(args, need_backend=False)
    died = broker.revoke(args.token_or_lease_id)
    print(_lease_json({"revoked": died}))
    return EXIT_OK if died else EXIT_DEAD


def cmd_list(args: argparse.Namespace) -> int:
    broker = _broker(args, need_backend=False)
    leases = broker.list_leases(agent=args.agent, active_only=args.active_only)
    print(_lease_json([lease.to_dict() for lease in leases]))
    return EXIT_OK


def cmd_purge(args: argparse.Namespace) -> int:
    broker = _broker(args, need_backend=False)
    count = broker.purge_expired()
    print(_lease_json({"purged": count}))
    return EXIT_OK


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--policy", required=True, help="policy JSON (or YAML with the yaml extra)")
    p.add_argument("--store", default="agent-scopes-leases.json", help="lease store file")
    p.add_argument("--env-file", default=None, help=".env file for the env backend")
    p.add_argument(
        "--map", action="append", default=[], help="resource to env var, RESOURCE=ENV_VAR"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-scopes",
        description="Short-lived scoped credentials for AI agents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_issue = sub.add_parser("issue", help="issue a scoped lease, prints the token once")
    _add_common(p_issue)
    p_issue.add_argument("--agent", required=True)
    p_issue.add_argument("--tool", required=True)
    p_issue.add_argument("--resource", required=True)
    p_issue.add_argument("--action", default="read", help="comma separated actions")
    p_issue.add_argument("--ttl", type=int, default=None)
    p_issue.add_argument("--single-use", action="store_true")
    p_issue.set_defaults(func=cmd_issue)

    p_redeem = sub.add_parser("redeem", help="exchange a token for the real secret")
    _add_common(p_redeem)
    p_redeem.add_argument("--token", required=True)
    p_redeem.add_argument("--tool", required=True)
    p_redeem.add_argument("--resource", required=True)
    p_redeem.add_argument("--action", default="read")
    p_redeem.set_defaults(func=cmd_redeem)

    p_validate = sub.add_parser("validate", help="check a token without redeeming it")
    _add_common(p_validate)
    p_validate.add_argument("--token", required=True)
    p_validate.add_argument("--tool", required=True)
    p_validate.add_argument("--resource", required=True)
    p_validate.add_argument("--action", default="read")
    p_validate.set_defaults(func=cmd_validate)

    p_revoke = sub.add_parser("revoke", help="revoke by token or lease id")
    _add_common(p_revoke)
    p_revoke.add_argument("token_or_lease_id")
    p_revoke.set_defaults(func=cmd_revoke)

    p_list = sub.add_parser("list", help="list leases in the store")
    _add_common(p_list)
    p_list.add_argument("--agent", default=None)
    p_list.add_argument("--active-only", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_purge = sub.add_parser("purge", help="drop expired leases from the store")
    _add_common(p_purge)
    p_purge.set_defaults(func=cmd_purge)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
