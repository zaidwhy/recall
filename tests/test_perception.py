"""Offline tests for scene-change gating (backend/perception.py::has_scene_changed).

Pure image-diff logic, no Gemini/network calls - has_scene_changed() is checked before
any Flash call is made, so this is the gate that keeps the vision quota alive.
"""
import io

import pytest
from PIL import Image

from backend import perception


@pytest.fixture(autouse=True)
def _reset_last_frame(monkeypatch):
    monkeypatch.setattr(perception, "_last_gray", None)


def _solid_jpeg(gray_value: int, size=(64, 48)) -> bytes:
    img = Image.new("L", size, color=gray_value).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_first_frame_always_counts_as_a_scene_change():
    assert perception.has_scene_changed(_solid_jpeg(100)) is True


def test_identical_frame_is_not_a_scene_change():
    frame = _solid_jpeg(100)
    assert perception.has_scene_changed(frame) is True   # first frame
    assert perception.has_scene_changed(frame) is False  # same frame again


def test_a_sufficiently_different_frame_is_a_scene_change():
    assert perception.has_scene_changed(_solid_jpeg(20)) is True
    assert perception.has_scene_changed(_solid_jpeg(220)) is True  # large brightness jump


def test_a_slightly_different_frame_under_threshold_is_not_a_scene_change():
    assert perception.has_scene_changed(_solid_jpeg(100)) is True
    # threshold is a mean abs diff of 12.0 on a 0-255 scale - a 2-value jitter should not trip it
    assert perception.has_scene_changed(_solid_jpeg(102)) is False
