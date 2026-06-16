"""Episodic memory store (the moat) — ChromaDB wrapper.

Week 2 target. Local-only, persistent. Stores observation embeddings + metadata
(object, location_label, timestamp, thumbnail_path) and supports semantic + temporal recall.

Planned surface:
    log_observation(observation) -> id
    recall_memory(query: str, k: int = 3, since=None, until=None) -> list[Observation]
"""

from __future__ import annotations

# Intentionally empty for Week 1. See PLAN.md / DISCUSSION.md §6-7.
