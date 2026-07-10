"""Interaction path - a Gemini Live voice session relayed over the phone's WebSocket.

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
from . import tools

log = logging.getLogger("recall")

LIVE_MODEL = os.environ.get("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")

SYSTEM = (
    "You are Recall, a warm and precise voice assistant with perfect photographic memory of the "
    "user's physical space. You have been watching their home and know exactly where things are.\n\n"
    "RULES:\n"
    "1. For ANY question about where something is, where it was left, or when it was last seen: "
    "ALWAYS call recall_memory first - never guess or invent a location.\n"
    "2. When confident=true: give a natural, specific spoken answer. Lead with the location and "
    "time. Example: 'Your keys are on the kitchen counter - I saw them there about 3 minutes ago.'\n"
    "3. When confident=false or no matches: be honest and brief. Say you haven't seen it yet.\n"
    "4. One or two sentences max. No filler phrases like 'based on my data' or 'according to my "
    "records' - speak like a person who actually remembers, not a database.\n"
    "5. If multiple matches exist, mention the most recent one first."
)


async def run_live(websocket, audio_in: asyncio.Queue) -> None:
    """Open a Live session, pump mic audio in, stream audio + transcripts out.

    Runs until cancelled (on live_stop / disconnect); the async context closes the
    session cleanly on cancellation.
    """
    # Manual activity detection: the phone's push-to-talk button delimits each turn
    # (start on press, end on release). More reliable than automatic VAD, which won't
    # fire without trailing silence and can clip a speaker who pauses.
    cfg = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
        ),
        system_instruction=types.Content(parts=[types.Part(text=SYSTEM)]),
        tools=[tools.RECALL_TOOL],
    )
    client = _client()
    async with client.aio.live.connect(model=LIVE_MODEL, config=cfg) as session:
        log.info("live session opened (%s)", LIVE_MODEL)
        await websocket.send_json({"type": "live_status", "state": "open"})

        async def pump_in() -> None:
            # Queue items: b"..." audio | "start" | "end" | None (stop).
            try:
                while True:
                    item = await audio_in.get()
                    if item is None:
                        break
                    if item == "start":
                        await session.send_realtime_input(activity_start=types.ActivityStart())
                    elif item == "end":
                        await session.send_realtime_input(activity_end=types.ActivityEnd())
                    else:
                        await session.send_realtime_input(
                            audio=types.Blob(data=item, mime_type="audio/pcm;rate=16000")
                        )
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("live pump_in failed")

        in_task = asyncio.create_task(pump_in())
        try:
            async for r in session.receive():
                if r.data:
                    await websocket.send_bytes(r.data)  # PCM @ 24 kHz to the phone
                if getattr(r, "tool_call", None):
                    try:
                        responses = []
                        for fc in r.tool_call.function_calls:
                            result = await asyncio.to_thread(
                                tools.handle_tool_call, fc.name, dict(fc.args or {})
                            )
                            responses.append(
                                types.FunctionResponse(id=fc.id, name=fc.name, response=result)
                            )
                            if result.get("confident") and result.get("matches"):
                                top = result["matches"][0]
                                await websocket.send_json({
                                    "type": "recalled",
                                    "match": {**top, "thumbnail": f"/thumbnails/{top['id']}.jpg"},
                                })
                        await session.send_tool_response(function_responses=responses)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        log.exception("tool call handling failed")
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
