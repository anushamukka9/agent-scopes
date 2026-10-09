"""The broker: mints scoped, short-lived leases and redeems them.

The shape of a tool call with agent-scopes in the middle:

1. The agent (or the harness driving it) asks the broker for a
   credential: this agent, this tool, this resource, this action.
2. The broker checks policy. No matching rule, no credential.
3. Policy allows it, so the broker issues a lease: a random token
   bound to exactly that agent, tool, resource, and action set, with
   an expiry (five minutes by default, clamped to the rule's cap).
4. When the tool actually runs, the tool gateway redeems the token.
   Scope is checked again, expiry is checked, and only then does the
   backend hand over the real secret, just in time.
5. The lease dies on expiry, on revoke, or after one redeem when the
   rule says single-use.

The agent never sees the long-lived secret. It holds a token that is
useless for any other tool, any other resource, or after its window.
"""

from __future__ import annotations

import secrets
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from agent_scopes.backends import BackendError
from agent_scopes.policy import Policy
from agent_scopes.store import LeaseRecord, LeaseStore

__all__ = [
    "AgentScopesError",
    "AuditEvent",
    "Broker",
    "Lease",
    "LeaseExpired",
    "LeaseRevoked",
    "PolicyDenied",
    "ScopeMismatch",
    "UnknownLease",
]


class AgentScopesError(RuntimeError):
    """Base class for broker errors."""


class PolicyDenied(AgentScopesError):
    """No policy rule allows this request."""


class UnknownLease(AgentScopesError):
    """The token does not match any lease this broker issued."""


class LeaseExpired(AgentScopesError):
    """The lease window has closed."""


class LeaseRevoked(AgentScopesError):
    """The lease was revoked (or already consumed)."""


class ScopeMismatch(AgentScopesError):
    """The token was asked to do something outside its scope."""


@dataclass(frozen=True)
class AuditEvent:
    """One broker decision. Never carries tokens or secrets."""

    ts: float
    event: str
    agent: str
    tool: str
    resource: str
    action: str = ""
    lease_id: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "event": self.event,
            "agent": self.agent,
            "tool": self.tool,
            "resource": self.resource,
            "action": self.action,
            "lease_id": self.lease_id,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Lease:
    """Public view of an issued lease.

    `token` is populated only on the object returned by issue(). It is
    the credential. Treat it like a password for its short life: it is
    shown once, stored only as a hash, and redacted in repr.
    """

    lease_id: str
    agent: str
    tool: str
    resource: str
    actions: tuple[str, ...]
    issued_at: float
    expires_at: float
    single_use: bool = False
    token: str | None = field(default=None, repr=False)

    @property
    def ttl_seconds(self) -> float:
        return max(0.0, self.expires_at - self.issued_at)

    def is_expired(self, now: float | None = None) -> bool:
        return (time.time() if now is None else now) >= self.expires_at

    def time_remaining(self, now: float | None = None) -> float:
        return max(0.0, self.expires_at - (time.time() if now is None else now))

    def to_dict(self) -> dict:
        return {
            "lease_id": self.lease_id,
            "agent": self.agent,
            "tool": self.tool,
            "resource": self.resource,
            "actions": list(self.actions),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "single_use": self.single_use,
        }

    def __repr__(self) -> str:
        token = "<redacted>" if self.token else None
        return (
            f"Lease(lease_id={self.lease_id!r}, agent={self.agent!r}, "
            f"tool={self.tool!r}, resource={self.resource!r}, "
            f"actions={self.actions!r}, expires_at={self.expires_at!r}, token={token})"
        )


def _public(record: LeaseRecord, token: str | None = None) -> Lease:
    return Lease(
        lease_id=record.lease_id,
        agent=record.agent,
        tool=record.tool,
        resource=record.resource,
        actions=record.actions,
        issued_at=record.issued_at,
        expires_at=record.expires_at,
        single_use=record.single_use,
        token=token,
    )


class Broker:
    """Issues and redeems scoped, short-lived credential leases."""

    def __init__(
        self,
        policy: Policy,
        backend,
        store: LeaseStore | None = None,
        clock: Callable[[], float] = time.time,
        default_ttl_seconds: int = 300,
        max_ttl_seconds: int = 300,
        audit_sink: Callable[[AuditEvent], None] | None = None,
    ) -> None:
        if default_ttl_seconds <= 0 or max_ttl_seconds <= 0:
            raise ValueError("TTL values must be positive")
        self._policy = policy
        self._backend = backend
        self._store = store if store is not None else LeaseStore()
        self._clock = clock
        self._default_ttl = default_ttl_seconds
        self._max_ttl = max_ttl_seconds
        self._audit_sink = audit_sink
        self.audit_log: list[AuditEvent] = []

    # -- internal helpers -------------------------------------------------

    def _audit(self, event: str, record_or_req, action: str = "", detail: str = "") -> None:
        if isinstance(record_or_req, LeaseRecord):
            agent, tool, resource = record_or_req.agent, record_or_req.tool, record_or_req.resource
            lease_id = record_or_req.lease_id
        else:
            agent, tool, resource = record_or_req
            lease_id = ""
        entry = AuditEvent(
            ts=self._clock(),
            event=event,
            agent=agent,
            tool=tool,
            resource=resource,
            action=action,
            lease_id=lease_id,
            detail=detail,
        )
        self.audit_log.append(entry)
        if self._audit_sink is not None:
            self._audit_sink(entry)

    def _resolve(self, token: str) -> LeaseRecord:
        record = self._store.get_by_token(token)
        if record is None:
            raise UnknownLease("this token does not match any lease")
        if record.revoked:
            raise LeaseRevoked(f"lease {record.lease_id} was revoked")
        if self._clock() >= record.expires_at:
            raise LeaseExpired(f"lease {record.lease_id} expired")
        return record

    @staticmethod
    def _check_scope(record: LeaseRecord, tool: str, resource: str, action: str) -> None:
        if tool != record.tool:
            raise ScopeMismatch(f"lease is for tool {record.tool!r}, not {tool!r}")
        if resource != record.resource:
            raise ScopeMismatch(f"lease is for resource {record.resource!r}, not {resource!r}")
        if action not in record.actions:
            raise ScopeMismatch(f"lease does not allow action {action!r}")

    # -- public API -------------------------------------------------------

    def issue(
        self,
        agent: str,
        tool: str,
        resource: str,
        actions: str | tuple[str, ...] = "read",
        ttl_seconds: int | None = None,
        single_use: bool | None = None,
    ) -> Lease:
        """Issue a lease. Returns a Lease carrying the one-time token.

        TTL is clamped to the smallest of: what you asked for, the
        rule's cap, the policy cap, and this broker's cap. Five
        minutes is the default everywhere, on purpose.
        """
        action_tuple = (actions,) if isinstance(actions, str) else tuple(actions)
        if not action_tuple:
            raise PolicyDenied("a lease needs at least one action")
        rule = self._policy.authorize(agent, tool, resource, action_tuple)
        if rule is None:
            self._audit(
                "denied",
                (agent, tool, resource),
                action=",".join(action_tuple),
                detail="no matching policy rule",
            )
            raise PolicyDenied(
                f"no policy rule allows agent {agent!r} to use {tool!r} on {resource!r}"
            )
        caps = [self._max_ttl, self._policy.max_ttl_seconds, rule.max_ttl_seconds]
        if ttl_seconds is not None:
            if ttl_seconds <= 0:
                raise ValueError("ttl_seconds must be positive")
            caps.append(int(ttl_seconds))
        else:
            caps.append(self._default_ttl)
        ttl = min(caps)
        now = self._clock()
        token = "asc_" + secrets.token_urlsafe(32)
        record = LeaseRecord(
            lease_id="lease_" + uuid.uuid4().hex[:16],
            token_hash=_hash(token),
            agent=agent,
            tool=tool,
            resource=resource,
            actions=action_tuple,
            issued_at=now,
            expires_at=now + ttl,
            single_use=rule.single_use if single_use is None else bool(single_use),
        )
        self._store.add(record)
        self._audit("issued", record, action=",".join(action_tuple), detail=f"ttl {ttl}s")
        return _public(record, token=token)

    def validate(self, token: str, tool: str, resource: str, action: str) -> Lease:
        """Check a token without fetching the secret or consuming it."""
        record = self._resolve(token)
        self._check_scope(record, tool, resource, action)
        self._audit("validated", record, action=action)
        return _public(record)

    def redeem(self, token: str, tool: str, resource: str, action: str) -> str | dict:
        """Exchange a token for the real secret, just in time.

        This is the moment the backend is touched. For Vault dynamic
        secrets, this is when Vault mints its own lease, and the id
        is kept so revoke() can take it back at the source.
        """
        record = self._resolve(token)
        try:
            self._check_scope(record, tool, resource, action)
        except ScopeMismatch:
            self._audit("scope_mismatch", record, action=action)
            raise
        try:
            result = self._backend.fetch(record.resource, tool=record.tool)
        except BackendError:
            self._audit("backend_error", record, action=action)
            raise
        record.redeem_count += 1
        if result.lease_ref:
            record.backend_lease_ref = result.lease_ref
        self._store.save()
        self._audit("redeemed", record, action=action)
        if record.single_use:
            self._revoke_record(record, detail="single-use consumed")
        return result.secret

    def _revoke_record(self, record: LeaseRecord, detail: str = "") -> None:
        if record.revoked:
            return
        record.revoked = True
        self._store.save()
        if record.backend_lease_ref and hasattr(self._backend, "revoke"):
            try:
                self._backend.revoke(record.backend_lease_ref)
            except BackendError:
                self._audit("backend_revoke_failed", record, detail=detail)
        self._audit("revoked", record, detail=detail)

    def revoke(self, token_or_lease_id: str) -> bool:
        """Revoke by raw token or by lease id. True when a lease died."""
        record = self._store.get_by_token(token_or_lease_id)
        if record is None:
            record = self._store.get_by_id(token_or_lease_id)
        if record is None or record.revoked:
            return False
        self._revoke_record(record, detail="revoked by caller")
        return True

    def revoke_all(self, agent: str | None = None, tool: str | None = None) -> int:
        """Revoke every live lease for an agent (or tool). The kill switch."""
        count = 0
        for record in self._store.all():
            if record.revoked:
                continue
            if agent is not None and record.agent != agent:
                continue
            if tool is not None and record.tool != tool:
                continue
            self._revoke_record(record, detail="revoke_all")
            count += 1
        return count

    def purge_expired(self) -> int:
        """Drop expired lease records. Returns how many were dropped."""
        now = self._clock()
        expired = [r for r in self._store.all() if now >= r.expires_at]
        for record in expired:
            self._store.remove(record)
        return len(expired)

    def list_leases(self, agent: str | None = None, active_only: bool = False) -> list[Lease]:
        now = self._clock()
        out: list[Lease] = []
        for record in self._store.all():
            if agent is not None and record.agent != agent:
                continue
            if active_only and (record.revoked or now >= record.expires_at):
                continue
            out.append(_public(record))
        return sorted(out, key=lambda lease: lease.issued_at)

    @contextmanager
    def credential(
        self,
        agent: str,
        tool: str,
        resource: str,
        action: str = "read",
        ttl_seconds: int | None = None,
    ) -> Iterator[str | dict]:
        """Issue, redeem, and revoke around one tool call.

        The secret exists in your process for exactly the block. The
        lease is revoked on exit even when the block raises.
        """
        lease = self.issue(agent, tool, resource, actions=(action,), ttl_seconds=ttl_seconds)
        assert lease.token is not None  # issue() always sets it
        try:
            yield self.redeem(lease.token, tool=tool, resource=resource, action=action)
        finally:
            self.revoke(lease.token)


def _hash(token: str) -> str:
    from agent_scopes.store import hash_token

    return hash_token(token)
