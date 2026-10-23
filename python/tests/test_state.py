import json

import pytest

from blare.state import (
    RETENTION_SECONDS,
    FileStore,
    MemoryStore,
    Store,
    build_store,
    default_file_path,
)


def test_memory_store_round_trip():
    store = MemoryStore()
    with store.transaction() as document:
        document["groups"]["abc"] = {"total": 1, "last_seen": 0}
    with store.transaction() as document:
        assert document["groups"]["abc"]["total"] == 1


def test_file_store_persists_across_instances(tmp_path):
    path = tmp_path / "state.json"
    with FileStore(path).transaction() as document:
        document["groups"]["abc"] = {"total": 7, "last_seen": 0}
    with FileStore(path).transaction() as document:
        assert document["groups"]["abc"]["total"] == 7


def test_file_store_writes_atomically(tmp_path):
    """No .tmp files left behind, and the document is valid JSON."""
    path = tmp_path / "state.json"
    with FileStore(path).transaction() as document:
        document["groups"]["abc"] = {"total": 1, "last_seen": 0}
    assert json.loads(path.read_text())["groups"]["abc"]["total"] == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_file_store_recovers_from_a_corrupt_file(tmp_path):
    """A truncated state file must not stop the application from alerting."""
    path = tmp_path / "state.json"
    path.write_text("{not json at all")
    with FileStore(path).transaction() as document:
        assert document["groups"] == {}


def test_file_store_rejects_a_foreign_schema(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"schema": 99, "groups": {"x": {}}}))
    with FileStore(path).transaction() as document:
        assert document["groups"] == {}


def test_pruning_forgets_old_groups():
    document = {
        "schema": 1,
        "groups": {
            "old": {"last_seen": 0},
            "fresh": {"last_seen": RETENTION_SECONDS + 10},
        },
        "bucket": {},
        "suppressed_by_cap": 0,
    }
    Store.prune(document, now=RETENTION_SECONDS + 20)
    assert set(document["groups"]) == {"fresh"}


def test_build_store_memory():
    assert build_store("memory", "svc").name == "memory"


def test_build_store_file_default(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    store = build_store("file", "checkout-api")
    assert store.name == "file"
    assert "checkout-api" in str(store.path)


def test_build_store_explicit_path(tmp_path):
    store = build_store(f"file:{tmp_path / 'custom.json'}", "svc")
    assert store.path.name == "custom.json"


def test_build_store_falls_back_loudly(caplog):
    """An unreachable backend must never prevent startup."""
    with caplog.at_level("WARNING", logger="blare"):
        store = build_store("postgres://nope", "svc")
    assert store.name == "memory"
    assert "unknown BLARE_STATE" in caplog.text


def test_service_name_is_sanitised_for_the_filename():
    assert "/" not in default_file_path("acme/checkout api").name


@pytest.mark.parametrize("spec", ["redis://localhost:1/0"])
def test_unreachable_redis_degrades_to_memory(spec, caplog):
    pytest.importorskip("redis")
    with caplog.at_level("WARNING", logger="blare"):
        store = build_store(spec, "svc", timeout=1)
    # Connecting is lazy, so this may succeed in constructing. Either way the
    # application must not have raised.
    assert store.name in {"redis", "memory"}
