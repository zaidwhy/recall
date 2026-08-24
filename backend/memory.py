"""Episodic memory store - ChromaDB wrapper.

Persistent, local-only. Uses the bundled ONNX embedding model (all-MiniLM-L6-v2)
so embeddings are free and offline. No Gemini embedding calls needed.
"""
from __future__ import annotations

import math
import time
import uuid
from functools import lru_cache
from pathlib import Path

import chromadb

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CHROMA_PATH = _DATA_DIR / "chroma"
_THUMBS_DIR = _DATA_DIR / "thumbnails"

# L2 distance threshold for "confident" recall (all-MiniLM-L6-v2, unit vectors → L2 ∈ [0,2]).
# 1.4 ≈ cosine similarity 0.02 - accepts any semantic overlap. Tune down to ~1.1 if false positives appear.
RECALL_MAX_DISTANCE = 1.4

# Recency blend: score = distance + DECAY_WEIGHT * log(1 + hours_ago).
# 0.25 means a 6-hour-old memory gets a +0.49 penalty vs. a fresh one at equal semantic distance.
DECAY_WEIGHT = 0.25

# Within this window, re-ingesting the same location UPDATES the existing entry instead of
# creating a new one. Keeps the timeline clean without losing the latest frame.
DEDUP_WINDOW_S = 60.0


def _time_penalty(timestamp: float) -> float:
    hours_ago = max(0.0, (time.time() - timestamp) / 3600)
    return DECAY_WEIGHT * math.log1p(hours_ago)


def _unpack(ids: list, docs: list, metas: list, distances: list | None = None) -> list[dict]:
    dists = distances if distances is not None else [None] * len(ids)
    return [
        {
            "id": eid,
            "description": doc,
            "objects": [o.strip() for o in meta["objects"].split(",") if o.strip()],
            "location_label": meta["location_label"],
            "timestamp": meta["timestamp"],
            "distance": dist,
        }
        for eid, doc, meta, dist in zip(ids, docs, metas, dists)
    ]


class MemoryStore:
    """One episodic memory store, bound to its own ChromaDB path and thumbnail directory.

    Each instance opens its own PersistentClient and holds its own collection handle, so
    multiple stores can be alive - and used - in the same process at once. The collection
    is created lazily on first use, not in __init__, to keep construction cheap.
    """

    def __init__(self, chroma_path: Path, thumbs_dir: Path):
        self.chroma_path = chroma_path
        self.thumbs_dir = thumbs_dir
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

    def _col(self) -> chromadb.Collection:
        if self._collection is None:
            self.thumbs_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.chroma_path))
            self._collection = self._client.get_or_create_collection("observations")
        return self._collection

    def close(self) -> None:
        """Release the underlying ChromaDB client handle.

        On Windows, PersistentClient holds an open sqlite file handle; a pytest tmp_path
        teardown raises WinError 32 if this isn't called first.
        """
        if self._client is not None:
            self._client.close()
        self._client = None
        self._collection = None

    def _find_recent_at_location(self, location_label: str, within_seconds: float = DEDUP_WINDOW_S) -> dict | None:
        """Return the most recent entry at this location within the window, or None."""
        col = self._col()
        if col.count() == 0:
            return None
        since = time.time() - within_seconds
        try:
            res = col.get(
                where={"$and": [
                    {"location_label": {"$eq": location_label}},
                    {"timestamp": {"$gte": since}},
                ]},
                include=["metadatas"],
            )
        except Exception:
            return None
        if not res["ids"]:
            return None
        pairs = sorted(zip(res["ids"], res["metadatas"]), key=lambda x: x[1]["timestamp"], reverse=True)
        eid, meta = pairs[0]
        return {"id": eid, **meta}

    def log_observation(self, obs: dict, jpeg_bytes: bytes) -> tuple[str, bool]:
        """Store or refresh an observation.

        If the same location was ingested within DEDUP_WINDOW_S, updates the existing
        entry (new description + fresh thumbnail) instead of appending a duplicate.

        Returns (entry_id, is_new) where is_new=False means an existing entry was refreshed.
        """
        col = self._col()
        recent = self._find_recent_at_location(obs["location_label"])

        if recent:
            col.update(
                ids=[recent["id"]],
                documents=[obs["description"]],
                metadatas=[{
                    "objects": ", ".join(obs["objects"]),
                    "location_label": obs["location_label"],
                    "timestamp": float(obs["timestamp"]),
                }],
            )
            (self.thumbs_dir / f"{recent['id']}.jpg").write_bytes(jpeg_bytes)
            return recent["id"], False

        entry_id = str(uuid.uuid4())
        (self.thumbs_dir / f"{entry_id}.jpg").write_bytes(jpeg_bytes)
        col.add(
            ids=[entry_id],
            documents=[obs["description"]],
            metadatas=[{
                "objects": ", ".join(obs["objects"]),
                "location_label": obs["location_label"],
                "timestamp": float(obs["timestamp"]),
            }],
        )
        return entry_id, True

    def recall_memory(
        self,
        query: str,
        k: int = 3,
        since: float | None = None,
        until: float | None = None,
    ) -> list[dict]:
        """Semantic search over stored observations. Optionally filter by Unix timestamp range."""
        col = self._col()
        count = col.count()
        if count == 0:
            return []

        where: dict | None = None
        if since is not None and until is not None:
            where = {"$and": [{"timestamp": {"$gte": since}}, {"timestamp": {"$lte": until}}]}
        elif since is not None:
            where = {"timestamp": {"$gte": since}}
        elif until is not None:
            where = {"timestamp": {"$lte": until}}

        results = col.query(
            query_texts=[query],
            n_results=min(k, count),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return _unpack(results["ids"][0], results["documents"][0], results["metadatas"][0], results["distances"][0])

    def find_by_object(
        self,
        object_name: str,
        limit: int = 9,
        since: float | None = None,
        until: float | None = None,
    ) -> list[dict]:
        """Return observations whose objects list contains object_name (case-insensitive substring).

        Complements semantic search: if the user asks "where are my keys?", this returns every
        observation that explicitly tagged "keys" in the objects field, newest first.
        """
        col = self._col()
        if col.count() == 0:
            return []
        where: dict | None = None
        if since is not None and until is not None:
            where = {"$and": [{"timestamp": {"$gte": since}}, {"timestamp": {"$lte": until}}]}
        elif since is not None:
            where = {"timestamp": {"$gte": since}}
        elif until is not None:
            where = {"timestamp": {"$lte": until}}
        kwargs: dict = {"include": ["documents", "metadatas"]}
        if where:
            kwargs["where"] = where
        res = col.get(**kwargs)
        entries = _unpack(res["ids"], res["documents"], res["metadatas"])
        q = object_name.lower()
        matches = [e for e in entries if any(q in o.lower() for o in e["objects"])]
        matches.sort(key=lambda x: x["timestamp"], reverse=True)
        return matches[:limit]

    def recall_for_tool(self, query: str, since: float | None = None, until: float | None = None) -> dict:
        """Semantic search + exact object-name matching, re-ranked by time decay.

        Strategy:
        1. Semantic search → up to 9 candidates.
        2. Exact object-name match → blend in any unique hits (synthetic distance 0.5).
        3. Re-rank by score = distance + time_penalty; return top 3.
        """
        candidates = self.recall_memory(query, k=9, since=since, until=until)
        seen_ids = {c["id"] for c in candidates}
        for e in self.find_by_object(query, limit=5, since=since, until=until):
            if e["id"] not in seen_ids:
                e["distance"] = 0.5  # exact name match - treat as high-confidence
                candidates.append(e)
                seen_ids.add(e["id"])
        for c in candidates:
            d = c["distance"] if c["distance"] is not None else 2.0
            c["score"] = d + _time_penalty(c["timestamp"])
        candidates.sort(key=lambda x: x["score"])
        matches = candidates[:3]
        confident = bool(matches) and matches[0]["distance"] is not None and matches[0]["distance"] <= RECALL_MAX_DISTANCE
        return {"matches": matches, "confident": confident}

    def list_all(self, limit: int = 200) -> list[dict]:
        """All observations, newest first (for the timeline UI)."""
        col = self._col()
        if col.count() == 0:
            return []
        res = col.get(limit=limit, include=["documents", "metadatas"])
        entries = _unpack(res["ids"], res["documents"], res["metadatas"])
        entries.sort(key=lambda x: x["timestamp"], reverse=True)
        return entries

    def delete_observation(self, entry_id: str) -> bool:
        """Delete an observation and its thumbnail. Returns True if it existed."""
        col = self._col()
        if not col.get(ids=[entry_id])["ids"]:
            return False
        (self.thumbs_dir / f"{entry_id}.jpg").unlink(missing_ok=True)
        col.delete(ids=[entry_id])
        return True

    def clear_all(self) -> int:
        """Delete every observation and thumbnail. Returns count deleted."""
        col = self._col()
        ids = col.get()["ids"]
        if not ids:
            return 0
        for eid in ids:
            (self.thumbs_dir / f"{eid}.jpg").unlink(missing_ok=True)
        col.delete(ids=ids)
        return len(ids)

    def stats(self) -> dict:
        """Aggregate stats for the /api/stats endpoint."""
        col = self._col()
        total = col.count()
        if total == 0:
            return {"total": 0, "distinct_locations": 0, "locations": [], "top_objects": [], "last_scan_ts": None}
        res = col.get(include=["metadatas"])
        metas = res["metadatas"]
        locations = sorted({m["location_label"] for m in metas})
        obj_counts: dict[str, int] = {}
        for m in metas:
            for o in m["objects"].split(","):
                o = o.strip()
                if o:
                    obj_counts[o] = obj_counts.get(o, 0) + 1
        top = sorted(obj_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        last_ts = max(m["timestamp"] for m in metas)
        return {
            "total": total,
            "distinct_locations": len(locations),
            "locations": locations,
            "top_objects": [{"name": n, "count": c} for n, c in top],
            "last_scan_ts": last_ts,
        }


@lru_cache(maxsize=1)
def get_default_store() -> MemoryStore:
    """The app-wide singleton store, reading data/chroma and data/thumbnails.

    backend/main.py and backend/tools.py both call the module-level functions below
    (e.g. memory.log_observation(...)) rather than constructing a MemoryStore themselves;
    those functions delegate here, which is what keeps those call sites unchanged.
    """
    return MemoryStore(_CHROMA_PATH, _THUMBS_DIR)


def log_observation(obs: dict, jpeg_bytes: bytes) -> tuple[str, bool]:
    return get_default_store().log_observation(obs, jpeg_bytes)


def recall_memory(query: str, k: int = 3, since: float | None = None, until: float | None = None) -> list[dict]:
    return get_default_store().recall_memory(query, k=k, since=since, until=until)


def find_by_object(
    object_name: str,
    limit: int = 9,
    since: float | None = None,
    until: float | None = None,
) -> list[dict]:
    return get_default_store().find_by_object(object_name, limit=limit, since=since, until=until)


def recall_for_tool(query: str, since: float | None = None, until: float | None = None) -> dict:
    return get_default_store().recall_for_tool(query, since=since, until=until)


def list_all(limit: int = 200) -> list[dict]:
    return get_default_store().list_all(limit=limit)


def delete_observation(entry_id: str) -> bool:
    return get_default_store().delete_observation(entry_id)


def clear_all() -> int:
    return get_default_store().clear_all()


def stats() -> dict:
    return get_default_store().stats()
