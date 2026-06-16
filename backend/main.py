"""Recall backend — FastAPI app.

Single-origin design (the key to mobile capture): this one server both serves the
built frontend (frontend/dist) AND exposes the /ws WebSocket. When fronted by a
cloudflared quick tunnel, the phone loads an https page and the WebSocket upgrades
to wss automatically — no mixed-content, no second tunnel.

Week 1 scope: prove the phone -> WS-over-tunnel path. The /ws endpoint just accepts
frames and acks them. Gemini ingestion/Live wiring lands in later phases.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from . import perception  # noqa: E402  (after load_dotenv so GEMINI_API_KEY is available)
from .live import run_live  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("recall")

app = FastAPI(title="Recall", version="0.1.0")

DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def _decode_frame(payload: str) -> bytes:
    if "," in payload:
        payload = payload.split(",", 1)[1]
    return base64.b64decode(payload, validate=False)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "frontend_built": DIST_DIR.is_dir()})


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


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    """Phone <-> backend channel.

    JSON text messages: frame / analyze / ping / live_start / live_stop.
    Binary messages: mic audio (PCM16 @ 16 kHz) for an active Live session.
    Binary out: Gemini Live audio (PCM @ 24 kHz). See live.py.
    """
    await websocket.accept()
    peer = websocket.client.host if websocket.client else "?"
    log.info("WS connected from %s", peer)
    frames = 0
    total_bytes = 0
    live: dict = {"task": None, "queue": None}
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            # Binary frame = mic audio for the Live session.
            if message.get("bytes") is not None:
                q = live.get("queue")
                if q is not None:
                    q.put_nowait(message["bytes"])
                continue

            raw = message.get("text")
            if raw is None:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "invalid json"})
                continue

            if msg.get("type") == "live_start":
                if live.get("task") is None:
                    q: asyncio.Queue = asyncio.Queue()
                    live["queue"] = q

                    async def _runner() -> None:
                        try:
                            await run_live(websocket, q)
                        except asyncio.CancelledError:
                            pass
                        except Exception as e:
                            log.exception("live session error")
                            try:
                                await websocket.send_json({"type": "error", "detail": f"live: {e}"})
                            except Exception:
                                pass

                    live["task"] = asyncio.create_task(_runner())
                    log.info("live_start")
            elif msg.get("type") == "live_stop":
                log.info("live_stop")
                await _stop_live(live, websocket)
            elif msg.get("type") == "frame":
                try:
                    data = _decode_frame(msg.get("data", ""))
                except Exception:
                    data = b""
                nbytes = len(data)
                frames += 1
                total_bytes += nbytes
                if data:
                    (DATA_DIR / "last_frame.jpg").write_bytes(data)  # for debugging / standalone tests
                log.info("frame #%d  %d bytes  (total %.1f KB)", frames, nbytes, total_bytes / 1024)
                await websocket.send_json(
                    {"type": "ack", "frame": frames, "bytes": nbytes, "ts": msg.get("ts")}
                )
            elif msg.get("type") == "analyze":
                # On-demand Gemini Flash vision (quota-safe: only when the user taps).
                try:
                    data = _decode_frame(msg.get("data", ""))
                    log.info("analyze: %d bytes -> Gemini Flash", len(data))
                    obs = await asyncio.to_thread(perception.analyze_frame, data)
                    log.info("observation (%dms): %s @ %s", obs["latency_ms"], obs["objects"], obs["location_label"])
                    await websocket.send_json({"type": "observation", **obs})
                except Exception as e:
                    log.exception("analyze failed")
                    await websocket.send_json({"type": "error", "detail": f"analyze failed: {e}"})
            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({"type": "error", "detail": "unknown message type"})
    except WebSocketDisconnect:
        pass
    finally:
        await _stop_live(live, websocket)
        log.info("WS disconnected from %s after %d frames (%.1f KB)", peer, frames, total_bytes / 1024)


# Serve the built frontend from the same origin (mounted last so /ws and /health win).
# During dev you usually run Vite separately; this matters for the mobile/demo path.
if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")
else:
    log.warning("frontend/dist not found — run `npm run build` in frontend/ for the mobile path")

    @app.get("/")
    async def no_build() -> JSONResponse:
        return JSONResponse(
            {
                "status": "backend up, frontend not built",
                "hint": "cd frontend && npm install && npm run build, then reload",
            }
        )
