"""Offline tests for the episodic memory store (backend/memory.py).

Each test gets its own MemoryStore, constructed directly against a pytest tmp_path - no
monkeypatching of module globals, no shared cache. No Gemini/network calls anywhere here.
"""
import time

import pytest

from backend import memory


@pytest.fixture
def store(tmp_path):
    s = memory.MemoryStore(tmp_path / "chroma", tmp_path / "thumbnails")
    yield s
    s.close()  # PersistentClient holds an open handle; must close before tmp_path teardown (Windows: WinError 32)


def _obs(location="desk", description="a mug and a phone", objects=None, timestamp=None):
    return {
        "location_label": location,
        "description": description,
        "objects": objects or ["mug", "phone"],
        "timestamp": timestamp if timestamp is not None else time.time(),
    }


def test_time_penalty_is_zero_at_zero_hours_and_grows_with_age():
    assert memory._time_penalty(time.time()) == pytest.approx(0.0, abs=1e-6)
    now = time.time()
    penalty_1h = memory._time_penalty(now - 3600)
    penalty_6h = memory._time_penalty(now - 6 * 3600)
    assert 0.0 < penalty_1h < penalty_6h


def test_find_recent_at_location_respects_the_window(store):
    obs = _obs(timestamp=time.time() - 100)
    store.log_observation(obs, b"fake-jpeg-bytes")

    # 100s ago is outside a 60s window ...
    assert store._find_recent_at_location("desk", within_seconds=60) is None
    # ... but inside a 200s window.
    found = store._find_recent_at_location("desk", within_seconds=200)
    assert found is not None
    assert found["location_label"] == "desk"


def test_log_observation_creates_a_new_entry(store):
    entry_id, is_new = store.log_observation(_obs(), b"jpeg-1")
    assert is_new is True
    assert (store.thumbs_dir / f"{entry_id}.jpg").read_bytes() == b"jpeg-1"
    assert store._col().count() == 1


def test_log_observation_dedups_the_same_location_within_the_window(store):
    first_id, first_is_new = store.log_observation(_obs(description="mug only"), b"jpeg-1")
    second_id, second_is_new = store.log_observation(_obs(description="mug and keys"), b"jpeg-2")

    assert first_is_new is True
    assert second_is_new is False
    assert second_id == first_id
    assert store._col().count() == 1  # updated in place, not duplicated
    assert (store.thumbs_dir / f"{first_id}.jpg").read_bytes() == b"jpeg-2"  # thumbnail refreshed


def test_log_observation_different_locations_create_separate_entries(store):
    store.log_observation(_obs(location="desk"), b"jpeg-1")
    store.log_observation(_obs(location="kitchen counter"), b"jpeg-2")
    assert store._col().count() == 2


def test_delete_observation_removes_entry_and_thumbnail(store):
    entry_id, _ = store.log_observation(_obs(), b"jpeg-1")
    assert store.delete_observation(entry_id) is True
    assert store._col().count() == 0
    assert not (store.thumbs_dir / f"{entry_id}.jpg").exists()


def test_delete_observation_missing_id_returns_false(store):
    assert store.delete_observation("does-not-exist") is False


def test_clear_all_removes_everything_and_returns_the_count(store):
    store.log_observation(_obs(location="desk"), b"jpeg-1")
    store.log_observation(_obs(location="kitchen counter"), b"jpeg-2")
    assert store.clear_all() == 2
    assert store._col().count() == 0
    assert store.clear_all() == 0  # idempotent on an empty store


def test_stats_on_empty_store(store):
    assert store.stats() == {
        "total": 0, "distinct_locations": 0, "locations": [], "top_objects": [], "last_scan_ts": None,
    }


def test_stats_aggregates_locations_and_top_objects(store):
    store.log_observation(_obs(location="desk", objects=["mug", "phone"]), b"jpeg-1")
    store.log_observation(_obs(location="kitchen counter", objects=["keys", "phone"]), b"jpeg-2")

    stats = store.stats()
    assert stats["total"] == 2
    assert stats["distinct_locations"] == 2
    assert stats["locations"] == ["desk", "kitchen counter"]
    counts = {o["name"]: o["count"] for o in stats["top_objects"]}
    assert counts["phone"] == 2
    assert counts["mug"] == 1
    assert counts["keys"] == 1


def test_recall_memory_on_empty_store_returns_empty_list(store):
    assert store.recall_memory("keys") == []


def test_find_by_object_matches_case_insensitive_substring(store):
    store.log_observation(_obs(location="desk", objects=["Car Keys", "mug"]), b"jpeg-1")
    store.log_observation(_obs(location="sofa", objects=["remote"]), b"jpeg-2")

    matches = store.find_by_object("keys")
    assert len(matches) == 1
    assert matches[0]["location_label"] == "desk"
    assert store.find_by_object("nonexistent-object") == []


def test_list_all_sorted_newest_first(store):
    now = time.time()
    store.log_observation(_obs(location="desk", timestamp=now - 3600), b"jpeg-1")
    store.log_observation(_obs(location="kitchen counter", timestamp=now), b"jpeg-2")

    entries = store.list_all()
    assert [e["location_label"] for e in entries] == ["kitchen counter", "desk"]


def test_two_independent_stores_coexist_in_one_process(tmp_path):
    """Acceptance check for the injectable-store refactor: two MemoryStore instances, against
    two different directories, alive and used at the same time - no monkeypatching, no cache
    clearing. Each store must see only what was written into it."""
    store_a = memory.MemoryStore(tmp_path / "store-a" / "chroma", tmp_path / "store-a" / "thumbnails")
    store_b = memory.MemoryStore(tmp_path / "store-b" / "chroma", tmp_path / "store-b" / "thumbnails")
    try:
        store_a.log_observation(_obs(location="desk", objects=["mug"]), b"jpeg-a")
        store_b.log_observation(_obs(location="sofa", objects=["remote"]), b"jpeg-b")

        assert store_a.stats()["total"] == 1
        assert store_b.stats()["total"] == 1
        assert [e["location_label"] for e in store_a.list_all()] == ["desk"]
        assert [e["location_label"] for e in store_b.list_all()] == ["sofa"]
        assert store_a.find_by_object("remote") == []
        assert store_b.find_by_object("mug") == []
    finally:
        store_a.close()
        store_b.close()


def test_module_level_functions_delegate_to_the_default_store(tmp_path, monkeypatch):
    """backend/main.py and backend/tools.py call memory.log_observation(...) etc. directly on
    the module - this is the backwards-compatibility guarantee those call sites depend on."""
    monkeypatch.setattr(memory, "_CHROMA_PATH", tmp_path / "chroma")
    monkeypatch.setattr(memory, "_THUMBS_DIR", tmp_path / "thumbnails")
    memory.get_default_store.cache_clear()
    try:
        entry_id, is_new = memory.log_observation(_obs(location="hallway"), b"jpeg-1")
        assert is_new is True
        assert memory.recall_memory("mug")[0]["id"] == entry_id
        assert memory.find_by_object("mug")[0]["id"] == entry_id
        assert memory.recall_for_tool("mug")["matches"][0]["id"] == entry_id
        assert memory.list_all()[0]["id"] == entry_id
        assert memory.stats()["total"] == 1
        assert memory.delete_observation(entry_id) is True
        assert memory.clear_all() == 0
    finally:
        memory.get_default_store().close()
        memory.get_default_store.cache_clear()
