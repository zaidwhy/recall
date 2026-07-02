"""Ingestion path (cheap) - turn a sampled camera frame into a structured observation.

Uses standard Gemini Flash vision (generous free RPD), NOT the Live API, so ingestion
stays inside the free tier. Week 1 hello-world #2 proves the frame -> observation round-trip;
scene-change gating + the always-on ingestion loop come in Week 2.
"""

from __future__ import annotations

import io
import os
import time
from functools import lru_cache

import numpy as np
from PIL import Image
from google import genai
from google.genai import types
from pydantic import BaseModel

VISION_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")

_PROMPT = (
    "You are the perception module of a personal memory assistant that remembers where "
    "objects are in someone's physical space. Look at this camera frame and report what "
    "you see. List the notable, nameable physical objects (ignore walls/floor/ceiling). "
    "Give a short location label for the scene (e.g. 'kitchen counter', 'desk', 'sofa'). "
    "Keep the description to one factual sentence."
)

# Scene-change detection - compare downscaled grayscale frames.
_SCENE_THRESHOLD = 12.0  # mean absolute pixel diff (0–255 scale); tune if too noisy
_DOWNSCALE = (64, 48)
_last_gray: np.ndarray | None = None


class Observation(BaseModel):
    objects: list[str]
    location_label: str
    description: str


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set - add it to .env")
    return genai.Client(api_key=key)


def has_scene_changed(jpeg_bytes: bytes) -> bool:
    """True if this frame differs enough from the last accepted frame to warrant re-analysis."""
    global _last_gray
    img = Image.open(io.BytesIO(jpeg_bytes)).convert("L").resize(_DOWNSCALE, Image.BILINEAR)
    gray = np.array(img, dtype=np.float32)
    if _last_gray is None:
        _last_gray = gray
        return True
    diff = float(np.mean(np.abs(gray - _last_gray)))
    if diff >= _SCENE_THRESHOLD:
        _last_gray = gray
        return True
    return False


def analyze_frame(jpeg_bytes: bytes) -> dict:
    """Send one JPEG frame to Gemini Flash and return a structured observation.

    Returns {objects, location_label, description, timestamp, latency_ms}.
    """
    started = time.perf_counter()
    resp = _client().models.generate_content(
        model=VISION_MODEL,
        contents=[
            types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
            _PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Observation,
            temperature=0.2,
        ),
    )
    obs: Observation = resp.parsed
    return {
        "objects": obs.objects,
        "location_label": obs.location_label,
        "description": obs.description,
        "timestamp": time.time(),
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }
