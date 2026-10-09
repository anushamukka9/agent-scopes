import pytest

from agent_scopes.backends import (
    BackendError,
    EnvFileBackend,
    InMemoryBackend,
    VaultBackend,
)


def test_inmemory_fetch_and_missing():
    backend = InMemoryBackend({"warehouse/prod": "fake-secret"})
    assert backend.fetch("warehouse/prod").secret == "fake-secret"
    with pytest.raises(BackendError):
        backend.fetch("warehouse/missing")


def test_env_file_parsing(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nWAREHOUSE_PROD='fake-warehouse-secret'\n\nexport API_KEY=\"fake-api\"\n",
        encoding="utf-8",
    )
    backend = EnvFileBackend(path=str(env), environ={})
    assert backend.fetch("warehouse/prod").secret == "fake-warehouse-secret"
    assert backend.fetch("api/key").secret == "fake-api"


def test_env_file_mapping_and_derivation(tmp_path):
    env = tmp_path / ".env"
    env.write_text("MY_DB=fake-db-secret\nWAREHOUSE_PROD=fake-wh\n", encoding="utf-8")
    backend = EnvFileBackend(
        path=str(env), mapping={"db/main": "MY_DB", "warehouse/*": "WAREHOUSE_PROD"}, environ={}
    )
    assert backend.fetch("db/main").secret == "fake-db-secret"
    assert backend.fetch("warehouse/eu").secret == "fake-wh"
    derived = EnvFileBackend(path=str(env), environ={})
    assert derived.fetch("warehouse/prod").secret == "fake-wh"


def test_env_environ_fallback():
    backend = EnvFileBackend(environ={"SEARCH_KEY": "fake-search"})
    assert backend.fetch("search/key").secret == "fake-search"


def test_env_missing_names_variable_not_value():
    backend = EnvFileBackend(environ={})
    with pytest.raises(BackendError) as excinfo:
        backend.fetch("warehouse/prod")
    assert "WAREHOUSE_PROD" in str(excinfo.value)
    assert "secret" not in str(excinfo.value).lower().split("warehouse_prod")[0][-20:]


def test_env_missing_file(tmp_path):
    with pytest.raises(BackendError):
        EnvFileBackend(path=str(tmp_path / "nope.env"), environ={})


class FakeVaultTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        assert headers["X-Vault-Token"] == "fake-vault-token"
        if url.endswith("/v1/secret/data/app/api-key"):
            return 200, {"data": {"data": {"value": "fake-api-key-value"}}}
        if url.endswith("/v1/database/creds/readonly"):
            return 200, {
                "data": {"username": "fake-user", "password": "fake-pass"},
                "lease_id": "database/creds/readonly/abc123",
                "lease_duration": 300,
            }
        if url.endswith("/v1/sys/leases/revoke"):
            return 204, {}
        return 404, {"errors": ["no handler"]}


def test_vault_kv_v2_single_value():
    transport = FakeVaultTransport()
    backend = VaultBackend(
        "https://vault.example:8200",
        token="fake-vault-token",
        mapping={"app/api-key": "secret/data/app/api-key"},
        transport=transport,
    )
    result = backend.fetch("app/api-key")
    assert result.secret == "fake-api-key-value"
    assert result.lease_ref is None


def test_vault_dynamic_secret_and_revoke():
    transport = FakeVaultTransport()
    backend = VaultBackend(
        "https://vault.example:8200",
        token="fake-vault-token",
        mapping={"db/readonly": "database/creds/readonly"},
        transport=transport,
    )
    result = backend.fetch("db/readonly")
    assert result.secret == {"username": "fake-user", "password": "fake-pass"}
    assert result.lease_ref == "database/creds/readonly/abc123"
    assert result.ttl_seconds == 300
    backend.revoke(result.lease_ref)
    assert transport.calls[-1][1].endswith("/v1/sys/leases/revoke")


def test_vault_error_does_not_leak_token():
    def bad_transport(method, url, headers, body):
        return 500, {"errors": ["boom"]}

    backend = VaultBackend(
        "https://vault.example:8200", token="fake-vault-token", transport=bad_transport
    )
    with pytest.raises(BackendError) as excinfo:
        backend.fetch("secret/data/app/api-key")
    assert "fake-vault-token" not in str(excinfo.value)
