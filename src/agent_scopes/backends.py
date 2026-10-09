"""Backends: where the real secret actually lives.

The broker never stores secrets. At redeem time it asks a backend for
the secret behind a resource name, hands it to the caller, and (for
backends that mint their own leases, like Vault dynamic secrets) keeps
the backend lease id so revoke can take the secret back at the source.

Three backends ship in the box:
- InMemoryBackend, for tests and demos. Secrets live in a dict.
- EnvFileBackend, for local dev. Secrets live in a .env file or the
  process environment. Honest warning: the underlying secret is still
  long-lived. The broker only shortens the window in which the agent
  holds it.
- VaultBackend, for production. Secrets live in HashiCorp Vault, KV v2
  reads and dynamic database credentials, with lease revocation.
"""

from __future__ import annotations

import fnmatch
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


class BackendError(RuntimeError):
    """Raised when a backend cannot produce (or revoke) a secret.

    Messages never include secret values.
    """


@dataclass(frozen=True)
class BackendResult:
    """A secret fetched from a backend, plus backend lease bookkeeping."""

    secret: str | dict
    lease_ref: str | None = None
    ttl_seconds: int | None = None


class InMemoryBackend:
    """Dict-backed backend. Tests and demos only."""

    def __init__(self, secrets: dict[str, str | dict]) -> None:
        self._secrets = dict(secrets)
        self.revoked: list[str] = []

    def fetch(self, resource: str, tool: str | None = None) -> BackendResult:
        if resource not in self._secrets:
            raise BackendError(f"no secret stored for resource {resource!r}")
        return BackendResult(secret=self._secrets[resource])

    def revoke(self, lease_ref: str) -> None:
        self.revoked.append(lease_ref)


def _parse_env_file(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _derive_env_name(resource: str) -> str:
    chars = [c.upper() if c.isalnum() else "_" for c in resource]
    return "".join(chars).strip("_") or "SECRET"


class EnvFileBackend:
    """Read secrets from a .env file, falling back to os.environ.

    `mapping` maps a resource (exact name or glob) to the environment
    variable that holds its secret. Without a mapping entry, the name
    is derived: `warehouse/prod` becomes `WAREHOUSE_PROD`.
    """

    def __init__(
        self,
        path: str | None = None,
        mapping: dict[str, str] | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        self._file_values: dict[str, str] = {}
        if path is not None:
            try:
                text = open(path, encoding="utf-8").read()
            except OSError as exc:
                raise BackendError(f"cannot read env file: {exc.filename}") from exc
            self._file_values = _parse_env_file(text)
        self._mapping = dict(mapping or {})
        self._environ = os.environ if environ is None else environ

    def _env_name(self, resource: str) -> str:
        if resource in self._mapping:
            return self._mapping[resource]
        for pattern, name in self._mapping.items():
            if fnmatch.fnmatchcase(resource, pattern):
                return name
        return _derive_env_name(resource)

    def fetch(self, resource: str, tool: str | None = None) -> BackendResult:
        name = self._env_name(resource)
        if name in self._file_values:
            return BackendResult(secret=self._file_values[name])
        if name in self._environ:
            return BackendResult(secret=self._environ[name])
        raise BackendError(f"environment variable {name} is not set for resource {resource!r}")

    def revoke(self, lease_ref: str) -> None:
        # Nothing to revoke at the source: the secret in the env file is
        # long-lived by nature. Broker-side revocation still works, the
        # token dies, but the env value itself does not rotate. Documented
        # honestly in docs/backends.md.
        return None


class VaultBackend:
    """HashiCorp Vault over plain HTTP, stdlib only.

    `mapping` maps a resource (exact name or glob) to a Vault path:
    - `secret/data/app/api-key` style paths are read as KV v2 and the
      `data` object comes back as the secret.
    - `database/creds/readonly` style paths are treated as dynamic
      secrets: the username/password pair comes back, and Vault's own
      lease id is kept so broker revoke revokes at Vault too.

    A path is read as dynamic when its second-to-last segment is
    `creds`, or when you pass `dynamic_prefixes`. `transport` is
    injectable for tests: a callable (method, url, headers, body) that
    returns (status, parsed_json).
    """

    def __init__(
        self,
        addr: str,
        token: str | None = None,
        mapping: dict[str, str] | None = None,
        dynamic_prefixes: tuple[str, ...] = (),
        transport=None,
        timeout: float = 10.0,
    ) -> None:
        self._addr = addr.rstrip("/")
        self._token = token if token is not None else os.environ.get("VAULT_TOKEN", "")
        self._mapping = dict(mapping or {})
        self._dynamic_prefixes = tuple(dynamic_prefixes)
        self._transport = transport
        self._timeout = timeout

    def _path_for(self, resource: str) -> str:
        if resource in self._mapping:
            return self._mapping[resource]
        for pattern, path in self._mapping.items():
            if fnmatch.fnmatchcase(resource, pattern):
                return path
        return resource

    def _is_dynamic(self, path: str) -> bool:
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[-2] == "creds":
            return True
        return any(path.startswith(prefix) for prefix in self._dynamic_prefixes)

    def _request(self, method: str, path: str, body: dict | None = None):
        url = f"{self._addr}/v1/{path.lstrip('/')}"
        headers = {"X-Vault-Token": self._token, "Accept": "application/json"}
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        if self._transport is not None:
            status, parsed = self._transport(method, url, headers, payload)
            if status >= 400:
                raise BackendError(f"Vault {method} {path} failed with status {status}")
            return parsed
        req = urllib.request.Request(url, data=payload, method=method)
        for key, value in headers.items():
            req.add_header(key, value)
        if payload is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise BackendError(f"Vault {method} {path} failed with status {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise BackendError(f"Vault {method} {path} could not connect") from exc

    def fetch(self, resource: str, tool: str | None = None) -> BackendResult:
        path = self._path_for(resource)
        parsed = self._request("GET", path)
        data = parsed.get("data") if isinstance(parsed, dict) else None
        if not isinstance(data, dict):
            raise BackendError(f"Vault path {path} returned no data object")
        if self._is_dynamic(path):
            secret = {k: data[k] for k in ("username", "password") if k in data} or dict(data)
            return BackendResult(
                secret=secret,
                lease_ref=parsed.get("lease_id") or data.get("lease_id"),
                ttl_seconds=parsed.get("lease_duration") or data.get("lease_duration"),
            )
        inner = data.get("data")
        if isinstance(inner, dict):
            # KV v2 wraps the payload one level down.
            secret = inner
        else:
            secret = data
        if len(secret) == 1:
            only = next(iter(secret.values()))
            if isinstance(only, str):
                return BackendResult(secret=only)
        return BackendResult(secret=dict(secret))

    def revoke(self, lease_ref: str) -> None:
        self._request("PUT", "sys/leases/revoke", {"lease_id": lease_ref})
