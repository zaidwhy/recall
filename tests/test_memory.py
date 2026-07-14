"""Offline tests for the episodic memory store (backend/memory.py).

Each test gets its own ChromaDB, isolated by monkeypatching the module's storage
paths to a pytest tmp_path and clearing the @lru_cache'd collection handle so a
fresh client opens against the new path. No Gemini/network calls anywhere here.
"""
import time

import pytest

from backend import memory


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "_CHROMA_PATH", tmp_path / "chroma")
    monkeypatch.setattr(memory, "_THUMBS_DIR", tmp_path / "thumbnails")
    memory._col.cache_clear()
    yield
    memory._col.cache_clear()


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


def test_find_recent_at_location_respects_the_window():
    obs = _obs(timestamp=time.time() - 100)
    memory.log_observation(obs, b"fake-jpeg-bytes")

    # 100s ago is outside a 60s window ...
    assert memory._find_recent_at_location("desk", within_seconds=60) is None
    # ... but inside a 200s window.
    found = memory._find_recent_at_location("desk", within_seconds=200)
    assert found is not None
    assert found["location_label"] == "desk"


def test_log_observation_creates_a_new_entry():
    entry_id, is_new = memory.log_observation(_obs(), b"jpeg-1")
    assert is_new is True
    assert (memory._THUMBS_DIR / f"{entry_id}.jpg").read_bytes() == b"jpeg-1"
    assert memory._col().count() == 1


def test_log_observation_dedups_the_same_location_within_the_window():
    first_id, first_is_new = memory.log_observation(_obs(description="mug only"), b"jpeg-1")
    second_id, second_is_new = memory.log_observation(_obs(description="mug and keys"), b"jpeg-2")

    assert first_is_new is True
    assert second_is_new is False
    assert second_id == first_id
    assert memory._col().count() == 1  # updated in place, not duplicated
    assert (memory._THUMBS_DIR / f"{first_id}.jpg").read_bytes() == b"jpeg-2"  # thumbnail refreshed


def test_log_observation_different_locations_create_separate_entries():
    memory.log_observation(_obs(location="desk"), b"jpeg-1")
    memory.log_observation(_obs(location="kitchen counter"), b"jpeg-2")
    assert memory._col().count() == 2


def test_delete_observation_removes_entry_and_thumbnail():
    entry_id, _ = memory.log_observation(_obs(), b"jpeg-1")
    assert memory.delete_observation(entry_id) is True
    assert memory._col().count() == 0
    assert not (memory._THUMBS_DIR / f"{entry_id}.jpg").exists()


def test_delete_observation_missing_id_returns_false():
    assert memory.delete_observation("does-not-exist") is False


def test_clear_all_removes_everything_and_returns_the_count():
    memory.log_observation(_obs(location="desk"), b"jpeg-1")
    memory.log_observation(_obs(location="kitchen counter"), b"jpeg-2")
    assert memory.clear_all() == 2
    assert memory._col().count() == 0
    assert memory.clear_all() == 0  # idempotent on an empty store


def test_stats_on_empty_store():
    assert memory.stats() == {
        "total": 0, "distinct_locations": 0, "locations": [], "top_objects": [], "last_scan_ts": None,
    }


def test_stats_aggregates_locations_and_top_objects():
    memory.log_observation(_obs(location="desk", objects=["mug", "phone"]), b"jpeg-1")
    memory.log_observation(_obs(location="kitchen counter", objects=["keys", "phone"]), b"jpeg-2")

    stats = memory.stats()
    assert stats["total"] == 2
    assert stats["distinct_locations"] == 2
    assert stats["locations"] == ["desk", "kitchen counter"]
    counts = {o["name"]: o["count"] for o in stats["top_objects"]}
    assert counts["phone"] == 2
    assert counts["mug"] == 1
    assert counts["keys"] == 1


def test_recall_memory_on_empty_store_returns_empty_list():
    assert memory.recall_memory("keys") == []


def test_find_by_object_matches_case_insensitive_substring():
    memory.log_observation(_obs(location="desk", objects=["Car Keys", "mug"]), b"jpeg-1")
    memory.log_observation(_obs(location="sofa", objects=["remote"]), b"jpeg-2")

    matches = memory.find_by_object("keys")
    assert len(matches) == 1
    assert matches[0]["location_label"] == "desk"
    assert memory.find_by_object("nonexistent-object") == []


def test_list_all_sorted_newest_first():
    now = time.time()
    memory.log_observation(_obs(location="desk", timestamp=now - 3600), b"jpeg-1")
    memory.log_observation(_obs(location="kitchen counter", timestamp=now), b"jpeg-2")

    entries = memory.list_all()
    assert [e["location_label"] for e in entries] == ["kitchen counter", "desk"]
