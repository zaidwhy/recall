"""Offline tests for the Gemini Flash rate guard (backend/main.py::_flash_blocked /
_charge_flash) - the vision-quota engineering (daily budget + minimum call gap) that
keeps ingestion inside the free tier. Pure module-global state, no network calls.
"""
import time

import pytest

from backend import main


@pytest.fixture(autouse=True)
def _reset_flash_state(monkeypatch):
    monkeypatch.setattr(main, "_last_flash_call", 0.0)
    monkeypatch.setattr(main, "_next_scan_at", 0.0)
    monkeypatch.setattr(main, "_flash_calls_today", 0)


def test_a_fresh_server_allows_the_first_call():
    assert main._flash_blocked() is None


def test_a_call_within_the_minimum_gap_is_blocked():
    main._charge_flash()
    reason = main._flash_blocked()
    assert reason is not None
    assert "wait" in reason.lower()


def test_a_call_after_the_gap_has_elapsed_is_allowed(monkeypatch):
    main._charge_flash()
    # Simulate the gap having passed without sleeping in the test.
    monkeypatch.setattr(main, "_last_flash_call", time.time() - main.FLASH_MIN_GAP_S - 1)
    assert main._flash_blocked() is None


def test_the_daily_budget_blocks_further_calls(monkeypatch):
    monkeypatch.setattr(main, "_flash_calls_today", main.FLASH_DAILY_BUDGET)
    reason = main._flash_blocked()
    assert reason is not None
    assert "budget" in reason.lower()


def test_charge_flash_increments_the_daily_count_and_advances_the_gap():
    before = time.time()
    main._charge_flash()
    assert main._flash_calls_today == 1
    assert main._last_flash_call >= before
    assert main._next_scan_at == pytest.approx(main._last_flash_call + main.FLASH_MIN_GAP_S)
