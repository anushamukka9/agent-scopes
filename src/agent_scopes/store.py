"""Lease storage: who holds what token, until when.

Only token hashes are stored, never raw tokens and never secrets.
If this file leaks, the tokens in it are useless: the raw token is
shown once at issue time and never kept.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class LeaseRecord:
    """Internal record for one issued lease."""

    lease_id: str
    token_hash: str
    agent: str
    tool: str
    resource: str
    actions: tuple[str, ...]
    issued_at: float
    expires_at: float
    single_use: bool = False
    revoked: bool = False
    redeem_count: int = 0
    backend_lease_ref: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["actions"] = list(self.actions)
        data.pop("token_hash", None)
        return data

    def storage_dict(self) -> dict:
        data = asdict(self)
        data["actions"] = list(self.actions)
        return data

    @classmethod
    def from_storage_dict(cls, data: dict) -> LeaseRecord:
        return cls(
            lease_id=str(data["lease_id"]),
            token_hash=str(data["token_hash"]),
            agent=str(data["agent"]),
            tool=str(data["tool"]),
            resource=str(data["resource"]),
            actions=tuple(str(a) for a in data["actions"]),
            issued_at=float(data["issued_at"]),
            expires_at=float(data["expires_at"]),
            single_use=bool(data.get("single_use", False)),
            revoked=bool(data.get("revoked", False)),
            redeem_count=int(data.get("redeem_count", 0)),
            backend_lease_ref=data.get("backend_lease_ref"),
        )


@dataclass
class LeaseStore:
    """In-memory store with optional JSON file persistence for the CLI."""

    records: dict[str, LeaseRecord] = field(default_factory=dict)
    _path: Path | None = field(default=None, repr=False)
    _by_id: dict[str, LeaseRecord] = field(default_factory=dict, repr=False)

    def add(self, record: LeaseRecord) -> None:
        self.records[record.token_hash] = record
        self._by_id[record.lease_id] = record
        self.save()

    def get_by_token(self, token: str) -> LeaseRecord | None:
        return self.records.get(hash_token(token))

    def get_by_id(self, lease_id: str) -> LeaseRecord | None:
        return self._by_id.get(lease_id)

    def all(self) -> list[LeaseRecord]:
        return list(self._by_id.values())

    def remove(self, record: LeaseRecord) -> None:
        self.records.pop(record.token_hash, None)
        self._by_id.pop(record.lease_id, None)
        self.save()

    def save(self) -> None:
        if self._path is None:
            return
        payload = [r.storage_dict() for r in self._by_id.values()]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    @classmethod
    def load(cls, path: str | Path) -> LeaseStore:
        p = Path(path)
        store = cls(_path=p)
        if not p.exists():
            return store
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return store
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    record = LeaseRecord.from_storage_dict(item)
                    store.records[record.token_hash] = record
                    store._by_id[record.lease_id] = record
        return store

    @classmethod
    def file_backed(cls, path: str | Path) -> LeaseStore:
        return cls.load(path)
