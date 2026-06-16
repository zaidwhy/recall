"""Episodic memory store — ChromaDB wrapper.

Persistent, local-only. Uses the bundled ONNX embedding model (all-MiniLM-L6-v2)
so embeddings are free and offline. No Gemini embedding calls needed.
"""
from __future__ import annotations

import uuid
from functools import lru_cache
from pathlib import Path

import chromadb

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CHROMA_PATH = _DATA_DIR / "chroma"
_THUMBS_DIR = _DATA_DIR / "thumbnails"


@lru_cache(maxsize=1)
def _col() -> chromadb.Collection:
    _THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(_CHROMA_PATH))
    return client.get_or_create_collection("observations")


def log_observation(obs: dict, jpeg_bytes: bytes) -> str:
    """Store an observation + thumbnail. Returns the entry id."""
    col = _col()
    entry_id = str(uuid.uuid4())
    (_THUMBS_DIR / f"{entry_id}.jpg").write_bytes(jpeg_bytes)
    col.add(
        ids=[entry_id],
        documents=[obs["description"]],
        metadatas=[{
            "objects": ", ".join(obs["objects"]),
            "location_label": obs["location_label"],
            "timestamp": float(obs["timestamp"]),
        }],
    )
    return entry_id


def recall_memory(
    query: str,
    k: int = 3,
    since: float | None = None,
    until: float | None = None,
) -> list[dict]:
    """Semantic search over stored observations. Optionally filter by Unix timestamp range."""
    col = _col()
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
    )
    return _unpack(results["ids"][0], results["documents"][0], results["metadatas"][0])


def list_all(limit: int = 200) -> list[dict]:
    """All observations, newest first (for the timeline UI)."""
    col = _col()
    if col.count() == 0:
        return []
    res = col.get(limit=limit, include=["documents", "metadatas"])
    entries = _unpack(res["ids"], res["documents"], res["metadatas"])
    entries.sort(key=lambda x: x["timestamp"], reverse=True)
    return entries


def delete_observation(entry_id: str) -> bool:
    """Delete an observation and its thumbnail. Returns True if it existed."""
    col = _col()
    if not col.get(ids=[entry_id])["ids"]:
        return False
    (_THUMBS_DIR / f"{entry_id}.jpg").unlink(missing_ok=True)
    col.delete(ids=[entry_id])
    return True


def _unpack(ids: list, docs: list, metas: list) -> list[dict]:
    return [
        {
            "id": eid,
            "description": doc,
            "objects": [o.strip() for o in meta["objects"].split(",") if o.strip()],
            "location_label": meta["location_label"],
            "timestamp": meta["timestamp"],
        }
        for eid, doc, meta in zip(ids, docs, metas)
    ]
