# Recall — Changelog

All notable changes to this project. Each entry maps to a dev session / week.

---

## Week 3 — Recall (2026-06-17)

### Added
- **`backend/memory.py`**
  - `recall_memory` now passes `include=["documents","metadatas","distances"]` to ChromaDB and returns L2 `distance` per result
  - `RECALL_MAX_DISTANCE = 1.0` — default confidence threshold (calibrate: log distances on a true hit vs. a never-recorded query, pick the boundary)
  - `recall_for_tool(query, since, until)` — wraps `recall_memory`, adds `confident` flag (`matches[0].distance <= RECALL_MAX_DISTANCE`)
  - `_unpack` updated to accept optional `distances` list; `list_all` path unaffected (no distances from `col.get()`)
- **`backend/tools.py`** — was a stub, now fully implemented
  - `RECALL_TOOL` — `types.Tool` with `recall_memory(query, minutes_ago?)` function declaration
  - `handle_tool_call(name, args)` — executes the tool call: calls `recall_for_tool`, trims payload to speakable fields + `minutes_ago`
- **`backend/live.py`**
  - `tools=[RECALL_TOOL]` wired into `LiveConnectConfig`
  - New SYSTEM prompt: model knows it has photographic memory, MUST call `recall_memory` for location/time questions, must not invent memories
  - `tool_call` handling in the receive loop: dispatches via `asyncio.to_thread` (ChromaDB is sync), sends `FunctionResponse` back to session, pushes `recalled` WS message to phone if confident
- **`frontend/src/App.jsx`**
  - `recalled` state for spotlight card
  - `recalled` WS message handler sets spotlight; cleared at `startTalk` (fresh query = fresh spotlight)
  - Spotlight card rendered above `.timeline` when `recalled` is set
- **`frontend/src/App.css`**
  - `.recalled` spotlight wrapper (accent border, slide-in animation)
  - `.recalled-badge`, `.recalled-x` dismiss button
  - Overrides inside `.recalled` to zero the inner `.memory-entry` border/padding, accent-color the time

### Key decisions
- ChromaDB dispatched via `asyncio.to_thread` — keeps the receive loop non-blocking during the sync embedding+query call
- `RECALL_MAX_DISTANCE` starts at 1.0 (L2, all-MiniLM-L6-v2) — must be calibrated on first phone test session
- Spotlight card clears on new talk press so it always reflects the current query's match

---

## Week 2 — Memory Ingestion (2026-06-16)

### Added
- **`backend/memory.py`** — ChromaDB wrapper (PersistentClient at `data/chroma/`)
  - `log_observation(obs, jpeg)` — stores description embedding + metadata, saves thumbnail to `data/thumbnails/<uuid>.jpg`
  - `recall_memory(query, k, since, until)` — semantic search with optional Unix timestamp range filter
  - `list_all(limit)` — all observations newest-first (for timeline UI)
  - `delete_observation(id)` — removes from ChromaDB + deletes thumbnail file
  - Local ONNX embeddings (`all-MiniLM-L6-v2`, cached in `~/.cache/chroma`) — free and offline, no Gemini embedding calls
- **`backend/perception.py`** — `has_scene_changed(jpeg)` scene-change detector
  - Downscales frame to 64×48 grayscale, computes mean absolute pixel diff vs. last accepted frame
  - Threshold: 12.0 (tune up to reduce sensitivity). First call always returns `True`.
- **`backend/main.py`** — always-on ingestion loop + new API
  - `record_start` / `record_stop` WS messages start/cancel `_ingest_loop` async task
  - Ingestion loop: polls `data/last_frame.jpg` every 5s → scene-change check → Gemini Flash → ChromaDB + thumbnail → sends `ingested` WS message to phone
  - `GET /memory` — returns all stored observations with thumbnail URLs
  - `DELETE /memory/{id}` — removes one observation and its thumbnail
  - `/thumbnails` static mount (registered before the `/` frontend catch-all — order matters)
- **`frontend/src/App.jsx`** — record toggle + memory timeline UI
  - "⏺ Record memory" / "⏹ Stop recording" toggle button
  - Fetches `/memory` on WS open to restore existing timeline across sessions
  - `ingested` WS message handler — prepends new cards to timeline in real-time
  - `record_status` WS message keeps toggle state in sync with server
  - Per-entry delete button (`DELETE /memory/:id`)
  - "Memories" counter in status grid
- **`frontend/src/App.css`** — new styles for record button, pulsing ingest status, memory entry cards, thumbnails, delete button

### Verified
- Three memory cards stored and displayed on phone after first recording session

---

## Week 1 — Capture + Vision + Voice (2026-06-15 / 2026-06-16)

### Added
- **`backend/main.py`** — FastAPI single-origin server: serves `frontend/dist` + `/ws` WebSocket on port 8000
  - `frame` message: accepts JPEG frames from phone, saves to `data/last_frame.jpg`
  - `analyze` message: on-demand Gemini Flash vision call
  - `live_start` / `live_stop` / `talk_start` / `talk_end`: Gemini Live relay
  - `/health` endpoint
- **`backend/perception.py`** — Gemini Flash structured observation via pydantic `response_schema`
  - Returns `{objects, location_label, description, timestamp, latency_ms}`
- **`backend/live.py`** — Gemini Live session relay
  - Manual activity detection (automatic VAD disabled) for push-to-talk
  - Audio in: PCM16 @ 16 kHz; audio out: PCM @ 24 kHz
  - Working model: `gemini-3.1-flash-live-preview`
- **`frontend/src/App.jsx`** — camera (rear, `facingMode:environment`) + WebSocket + analyze + push-to-talk voice
- **`frontend/src/audio.js`** — `AudioPlayer` (gapless 24 kHz playback), `downsampleTo16k`, `f32ToInt16`
- **`frontend/public/pcm-worklet.js`** — mic capture AudioWorklet (real file, not a data: URL — required for iOS Safari)
- **`frontend/vite.config.js`** — dev proxy `/ws` → `:8000`

### Key decisions
- Single-origin + one cloudflared tunnel: phone loads `https` and WS upgrades to `wss` automatically — no mixed-content, no second tunnel
- Decoupled paths: Gemini Flash for always-on ingestion (generous free RPD), Gemini Live only while user is actively talking — stays inside free tier
- **Never enable billing on the Gemini project** — it deletes the free tier

### Verified
- Phone rear camera → frames landing server-side ✅
- "What am I looking at?" → correct desk scene observation ✅
- Push-to-talk → spoken reply heard on-device ✅

---

## What's next

### Week 3 — Recall (the magic)
- `backend/tools.py`: wire `recall_memory(query)` as a function-calling tool into the Live session (`tools=` in `LiveConnectConfig`)
- "Recall, where did I leave my charger?" → semantic + temporal search → spoken answer + remembered frame

### Week 4 — Credibility
- `eval/benchmark.py`: staged object placements → scripted questions → recall@1/@3 + latency, printed into README

### Weeks 5–6 — Polish + ship
- UI polish, accessibility mode, staged demo scenarios
- 60-second killer demo video (primary artifact)
- README with architecture diagram
- LinkedIn build-in-public series
