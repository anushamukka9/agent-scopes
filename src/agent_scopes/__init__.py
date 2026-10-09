"""agent-scopes: short-lived scoped credentials for AI agents.

A tool call gets a credential valid for that tool, that resource, and
five minutes. Then it dies. The agent never holds the long-lived secret.
"""

from agent_scopes.backends import (
    BackendError,
    BackendResult,
    EnvFileBackend,
    InMemoryBackend,
    VaultBackend,
)
from agent_scopes.broker import (
    AgentScopesError,
    AuditEvent,
    Broker,
    Lease,
    LeaseExpired,
    LeaseRevoked,
    PolicyDenied,
    ScopeMismatch,
    UnknownLease,
)
from agent_scopes.policy import Policy, PolicyError, PolicyRule
from agent_scopes.store import LeaseStore

__version__ = "0.1.0"

__all__ = [
    "AgentScopesError",
    "AuditEvent",
    "BackendError",
    "BackendResult",
    "Broker",
    "EnvFileBackend",
    "InMemoryBackend",
    "Lease",
    "LeaseExpired",
    "LeaseRevoked",
    "LeaseStore",
    "Policy",
    "PolicyDenied",
    "PolicyError",
    "PolicyRule",
    "ScopeMismatch",
    "UnknownLease",
    "VaultBackend",
]
