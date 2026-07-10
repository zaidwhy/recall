"""Recall backend - FastAPI app.

Single-origin design (the key to mobile capture): this one server both serves the
built frontend (frontend/dist) AND exposes the /ws WebSocket. When fronted by a
cloudflared quick tunnel, the phone loads an https page and the WebSocket upgrades
to wss automatically - no mixed-content, no second tunnel.

Week 2 additions: always-on ingestion loop (record_start / record_stop), ChromaDB
memory store, /memory GET+DELETE endpoints, /thumbnails static serving.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from . import memory, perception  # noqa: E402  (after load_dotenv so GEMINI_API_KEY is available)
from .live import run_live  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("recall")

app = FastAPI(title="Recall", version="0.2.0")

DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
THUMBS_DIR = DATA_DIR / "thumbnails"
DATA_DIR.mkdir(exist_ok=True)
THUMBS_DIR.mkdir(exist_ok=True)

# Poll interval for the ingest loop. Flash is only called when the scene actually
# changes AND the minimum gap has elapsed - so this is the check frequency, not the call rate.
INGEST_INTERVAL_S = 5

# Hard floor between Gemini Flash calls (vision + analyze combined).
# gemini-2.5-flash free tier: 20 RPD. 120s floor → max 1 call/2 min → 10 calls in a 20-min demo session.
FLASH_MIN_GAP_S = 120

# Tracks the last time we made a Gemini Flash call - shared across ingest loop and analyze handler.
_last_flash_call: float = 0.0
_next_scan_at: float = 0.0           # earliest wall-clock time the next Flash call is allowed
_flash_calls_today: int = 0          # resets on server restart; used for on-screen budget display
FLASH_DAILY_BUDGET = 18              # stop at 18 to keep 2 in reserve

log.info("Vision model: %s  |  min gap between Flash calls: %ds", perception.VISION_MODEL, FLASH_MIN_GAP_S)


def _flash_blocked() -> str | None:
    """Return a human-readable reason if a Flash call is not allowed right now, else None."""
    if _flash_calls_today >= FLASH_DAILY_BUDGET:
        return f"Daily vision budget ({FLASH_DAILY_BUDGET} calls) reached. Resets at midnight."
    gap = time.time() - _last_flash_call
    if gap < FLASH_MIN_GAP_S:
        wait = int(FLASH_MIN_GAP_S - gap) + 1
        return f"Rate guard: wait {wait}s before next Flash call"
    return None


def _charge_flash() -> None:
    """Mark a Flash call as used and advance the next-scan timer."""
    global _last_flash_call, _next_scan_at, _flash_calls_today
    _last_flash_call = time.time()
    _next_scan_at = _last_flash_call + FLASH_MIN_GAP_S
    _flash_calls_today += 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_frame(payload: str) -> bytes:
    if "," in payload:
        payload = payload.split(",", 1)[1]
    return base64.b64decode(payload, validate=False)


# ---------------------------------------------------------------------------
# API routes (must be registered before static mounts)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "frontend_built": DIST_DIR.is_dir(),
        "vision_model": perception.VISION_MODEL,
        "flash_calls_today": _flash_calls_today,
        "flash_budget": FLASH_DAILY_BUDGET,
        "next_scan_in_s": max(0, round(_next_scan_at - time.time())) if _next_scan_at > 0 else 0,
    })


@app.get("/memory")
async def get_memory() -> JSONResponse:
    entries = await asyncio.to_thread(memory.list_all)
    for e in entries:
        e["thumbnail"] = f"/thumbnails/{e['id']}.jpg"
    return JSONResponse(entries)


@app.delete("/memory")
async def clear_memory() -> JSONResponse:
    n = await asyncio.to_thread(memory.clear_all)
    return JSONResponse({"cleared": n})


@app.delete("/memory/{entry_id}")
async def delete_memory(entry_id: str) -> JSONResponse:
    found = await asyncio.to_thread(memory.delete_observation, entry_id)
    if not found:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"deleted": entry_id})


@app.get("/api/stats")
async def api_stats() -> JSONResponse:
    s = await asyncio.to_thread(memory.stats)
    s["flash_calls_today"] = _flash_calls_today
    s["flash_budget"] = FLASH_DAILY_BUDGET
    s["next_scan_in_s"] = max(0, round(_next_scan_at - time.time())) if _next_scan_at > 0 else 0
    return JSONResponse(s)


@app.get("/api/search")
async def api_search(q: str = "") -> JSONResponse:
    """Recall search from the UI - returns top 3 matches with thumbnails."""
    if not q.strip():
        return JSONResponse({"error": "q is required"}, status_code=400)
    result = await asyncio.to_thread(memory.recall_for_tool, q.strip())
    for m in result["matches"]:
        m["thumbnail"] = f"/thumbnails/{m['id']}.jpg"
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# WebSocket helpers
# ---------------------------------------------------------------------------

async def _stop_live(live: dict, websocket: WebSocket) -> None:
    task = live.get("task")
    if task is not None:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        live["task"] = None
        live["queue"] = None
        try:
            await websocket.send_json({"type": "live_status", "state": "closed"})
        except Exception:
            pass


async def _stop_ingest(ingest: dict, websocket: WebSocket | None = None) -> None:
    task = ingest.get("task")
    if task is not None:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        ingest["task"] = None
    if websocket is not None:
        try:
            await websocket.send_json({"type": "record_status", "recording": False})
        except Exception:
            pass


async def _ingest_loop(websocket: WebSocket) -> None:
    """Always-on ingestion: sample last_frame.jpg every INGEST_INTERVAL_S seconds,
    run scene-change detection, and only call Gemini Flash when something changed."""
    global _last_flash_call, _next_scan_at, _flash_calls_today
    try:
        await websocket.send_json({
            "type": "record_status",
            "recording": True,
            "flash_calls": _flash_calls_today,
            "flash_budget": FLASH_DAILY_BUDGET,
            "next_scan_at": _next_scan_at,
        })
    except Exception:
        return

    while True:
        await asyncio.sleep(INGEST_INTERVAL_S)
        frame_path = DATA_DIR / "last_frame.jpg"
        if not frame_path.exists():
            continue
        try:
            jpeg = frame_path.read_bytes()
        except OSError:
            continue
        try:
            changed = await asyncio.to_thread(perception.has_scene_changed, jpeg)
            if not changed:
                continue
            reason = _flash_blocked()
            if reason:
                if _flash_calls_today >= FLASH_DAILY_BUDGET:
                    log.warning("daily Flash budget (%d) reached - pausing ingestion", FLASH_DAILY_BUDGET)
                    await asyncio.sleep(300)
                else:
                    log.debug("flash gated: %s", reason)
                continue
            try:
                await websocket.send_json({"type": "scanning"})
            except Exception:
                pass
            _charge_flash()
            log.info("flash call #%d/%d", _flash_calls_today, FLASH_DAILY_BUDGET)
            obs = await asyncio.to_thread(perception.analyze_frame, jpeg)
            entry_id, is_new = await asyncio.to_thread(memory.log_observation, obs, jpeg)
            action = "ingested" if is_new else "updated"
            log.info("%s %s @ %s…", action, obs["location_label"], entry_id[:8])
            await websocket.send_json({
                "type": action,
                "id": entry_id,
                "thumbnail": f"/thumbnails/{entry_id}.jpg",
                "objects": obs["objects"],
                "location_label": obs["location_label"],
                "description": obs["description"],
                "timestamp": obs["timestamp"],
                "latency_ms": obs["latency_ms"],
                "flash_calls": _flash_calls_today,
                "flash_budget": FLASH_DAILY_BUDGET,
                "next_scan_at": _next_scan_at,
            })
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                # Parse retry delay from error message; default to 60s
                import re
                m = re.search(r"retry in (\d+)", msg, re.IGNORECASE)
                wait = int(m.group(1)) + 5 if m else 65
                log.warning("rate limited by Gemini (%s quota); sleeping %ds", perception.VISION_MODEL, wait)
                try:
                    await websocket.send_json({"type": "error", "detail": f"Rate limited - pausing ingestion for {wait}s"})
                except Exception:
                    pass
                await asyncio.sleep(wait)
            else:
                log.exception("ingestion error (will retry next interval)")


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    """Phone <-> backend channel.

    JSON text messages: frame / analyze / ping / live_start / live_stop /
                        record_start / record_stop / talk_start / talk_end.
    Binary messages: mic audio (PCM16 @ 16 kHz) for an active Live session.
    Binary out: Gemini Live audio (PCM @ 24 kHz). See live.py.
    """
    await websocket.accept()
    peer = websocket.client.host if websocket.client else "?"
    log.info("WS connected from %s", peer)
    frames = 0
    total_bytes = 0
    live: dict = {"task": None, "queue": None}
    ingest: dict = {"task": None}
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            # Binary frame = mic audio for the Live session.
            if message.get("bytes") is not None:
                audio_q = live.get("queue")
                if audio_q is not None:
                    audio_q.put_nowait(message["bytes"])
                continue

            raw = message.get("text")
            if raw is None:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "invalid json"})
                continue

            mtype = msg.get("type")

            if mtype == "record_start":
                if ingest.get("task") is None:
                    ingest["task"] = asyncio.create_task(_ingest_loop(websocket))
                    log.info("ingestion started")

            elif mtype == "record_stop":
                log.info("ingestion stopped")
                await _stop_ingest(ingest, websocket)

            elif mtype == "live_start":
                if live.get("task") is None:
                    new_q: asyncio.Queue = asyncio.Queue()
                    live["queue"] = new_q

                    async def _runner(q: asyncio.Queue = new_q) -> None:
                        while True:
                            try:
                                await run_live(websocket, q)
                                log.info("live session ended cleanly; reconnecting")
                            except asyncio.CancelledError:
                                break
                            except Exception as e:
                                log.exception("live session error; reconnecting in 2s")
                                try:
                                    await websocket.send_json({"type": "error", "detail": f"live: {e}"})
                                except Exception:
                                    pass
                                await asyncio.sleep(2)
                            # Drain stale activity_start/end signals before reconnect
                            while not q.empty():
                                try:
                                    q.get_nowait()
                                except asyncio.QueueEmpty:
                                    break

                    live["task"] = asyncio.create_task(_runner())
                    log.info("live_start")

            elif mtype == "live_stop":
                log.info("live_stop")
                await _stop_live(live, websocket)

            elif mtype in ("talk_start", "talk_end"):
                q = live.get("queue")
                if q is not None:
                    q.put_nowait("start" if mtype == "talk_start" else "end")

            elif mtype == "frame":
                try:
                    data = _decode_frame(msg.get("data", ""))
                except Exception:
                    data = b""
                nbytes = len(data)
                frames += 1
                total_bytes += nbytes
                if data:
                    (DATA_DIR / "last_frame.jpg").write_bytes(data)
                log.info("frame #%d  %d bytes  (total %.1f KB)", frames, nbytes, total_bytes / 1024)
                await websocket.send_json(
                    {"type": "ack", "frame": frames, "bytes": nbytes, "ts": msg.get("ts")}
                )

            elif mtype == "analyze":
                try:
                    reason = _flash_blocked()
                    if reason:
                        await websocket.send_json({"type": "error", "detail": reason})
                        continue
                    data = _decode_frame(msg.get("data", ""))
                    _charge_flash()
                    log.info("analyze: %d bytes -> Flash #%d/%d (%s)", len(data), _flash_calls_today, FLASH_DAILY_BUDGET, perception.VISION_MODEL)
                    obs = await asyncio.to_thread(perception.analyze_frame, data)
                    log.info("observation (%dms): %s @ %s", obs["latency_ms"], obs["objects"], obs["location_label"])
                    await websocket.send_json({"type": "observation", **obs})
                except Exception as e:
                    log.exception("analyze failed")
                    await websocket.send_json({"type": "error", "detail": f"analyze failed: {e}"})

            elif mtype == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json({"type": "error", "detail": "unknown message type"})

    except WebSocketDisconnect:
        pass
    finally:
        await _stop_live(live, websocket)
        await _stop_ingest(ingest)
        log.info("WS disconnected from %s after %d frames (%.1f KB)", peer, frames, total_bytes / 1024)


# ---------------------------------------------------------------------------
# Static mounts (order matters: specific paths before the catch-all "/")
# ---------------------------------------------------------------------------

app.mount("/thumbnails", StaticFiles(directory=str(THUMBS_DIR)), name="thumbnails")

if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")
else:
    log.warning("frontend/dist not found - run `npm run build` in frontend/ for the mobile path")

    @app.get("/")
    async def no_build() -> JSONResponse:
        return JSONResponse(
            {
                "status": "backend up, frontend not built",
                "hint": "cd frontend && npm install && npm run build, then reload",
            }
        )
