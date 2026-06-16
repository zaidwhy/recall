"""Ingestion path (cheap) — turn a sampled camera frame into a structured observation.

Week 2 target. Uses standard Gemini Flash vision (generous free RPD), NOT the Live API,
so continuous ingestion stays inside the free tier. Scene-change detection decides which
frames are worth analysing.

Planned surface:
    detect_scene_change(prev_frame, frame) -> bool
    extract_observation(frame_jpeg: bytes) -> Observation
        {objects: [...], location_label: str, description: str, timestamp, thumbnail_path}
"""

from __future__ import annotations

# Intentionally empty for Week 1. See PLAN.md / DISCUSSION.md §7.
