"""Recall backend — FastAPI app.

Single-origin design (the key to mobile capture): this one server both serves the
built frontend (frontend/dist) AND exposes the /ws WebSocket. When fronted by a
cloudflared quick tunnel, the phone loads an https page and the WebSocket upgrades
to wss automatically — no mixed-content, no second tunnel.

Week 1 scope: prove the phone -> WS-over-tunnel path. The /ws endpoint just accepts
frames and acks them. Gemini ingestion/Live wiring lands in later phases.
"""

from __future__ import annotations

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


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    """Receive sampled camera frames from the phone and ack them.

    Messages are JSON: {"type": "frame", "ts": <ms>, "data": "<base64 jpeg>"}.
    For Week 1 we only count + measure; later this feeds the perception pipeline.
    """
    await websocket.accept()
    peer = websocket.client.host if websocket.client else "?"
    log.info("WS connected from %s", peer)
    frames = 0
    total_bytes = 0
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "invalid json"})
                continue

            if msg.get("type") == "frame":
                payload = msg.get("data", "")
                # strip data-url prefix if present
                if "," in payload:
                    payload = payload.split(",", 1)[1]
                try:
                    nbytes = len(base64.b64decode(payload, validate=False))
                except Exception:
                    nbytes = 0
                frames += 1
                total_bytes += nbytes
                log.info("frame #%d  %d bytes  (total %.1f KB)", frames, nbytes, total_bytes / 1024)
                await websocket.send_json(
                    {"type": "ack", "frame": frames, "bytes": nbytes, "ts": msg.get("ts")}
                )
            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({"type": "error", "detail": "unknown message type"})
    except WebSocketDisconnect:
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
