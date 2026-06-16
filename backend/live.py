"""Interaction path — a Gemini Live voice session relayed over the phone's WebSocket.

The phone streams mic audio (PCM16 @ 16 kHz) as binary WS frames; we forward them to a
Gemini Live session and stream the model's spoken reply (PCM @ 24 kHz) back as binary.
Transcripts (both sides) are sent as JSON for an on-screen caption.

Week 1 hello-world #3: prove the voice round-trip. The recall_memory function-calling
tool (the moat) gets wired into this same session in Week 3.
"""

from __future__ import annotations

import asyncio
import logging
import os

from google.genai import types

from .perception import _client  # reuse the cached genai client

log = logging.getLogger("recall")

LIVE_MODEL = os.environ.get("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")

SYSTEM = (
    "You are Recall, a warm, concise voice assistant that will eventually have a "
    "photographic memory of the user's physical world. Right now this is a voice "
    "round-trip test, so just chat naturally and briefly. Keep replies to one or two "
    "sentences unless asked for more."
)


async def run_live(websocket, audio_in: asyncio.Queue) -> None:
    """Open a Live session, pump mic audio in, stream audio + transcripts out.

    Runs until cancelled (on live_stop / disconnect); the async context closes the
    session cleanly on cancellation.
    """
    cfg = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=types.Content(parts=[types.Part(text=SYSTEM)]),
    )
    client = _client()
    async with client.aio.live.connect(model=LIVE_MODEL, config=cfg) as session:
        log.info("live session opened (%s)", LIVE_MODEL)
        await websocket.send_json({"type": "live_status", "state": "open"})

        async def pump_in() -> None:
            while True:
                chunk = await audio_in.get()
                if chunk is None:
                    break
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )

        in_task = asyncio.create_task(pump_in())
        try:
            async for r in session.receive():
                if r.data:
                    await websocket.send_bytes(r.data)  # PCM @ 24 kHz to the phone
                sc = getattr(r, "server_content", None)
                if sc:
                    ot = getattr(sc, "output_transcription", None)
                    if ot and ot.text:
                        await websocket.send_json(
                            {"type": "transcript", "role": "assistant", "text": ot.text}
                        )
                    it = getattr(sc, "input_transcription", None)
                    if it and it.text:
                        await websocket.send_json(
                            {"type": "transcript", "role": "user", "text": it.text}
                        )
        finally:
            in_task.cancel()
    log.info("live session closed")
