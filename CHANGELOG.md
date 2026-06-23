# Recall — Changelog

All notable changes to this project. Each entry maps to a dev session / week.

---

## UI Overhaul (2026-06-23)

### Changed — `frontend/src/App.css` (complete redesign)
- Background: richer deep-navy with dual radial gradients (blue top, purple side-pocket)
- Header: `header-brand` flex wrapper with `header-icon` (rounded square) + wider gradient title (white → blue → purple); `filter: drop-shadow` glow on h1
- Status chip: top-right live/offline indicator with pulsing green dot when WebSocket is open
- Stats bar: values highlighted with `.stats-value` (accent blue), pill becomes self-centered
- Camera `stage`: subtle outer glow + stronger shadow; scan overlay rewritten as moving scan line sweep (absolute pseudo-element)
- Viewfinder corners (`.vf-corner .vf-tl/tr/bl/br`): L-shaped corner markers in camera HUD style; glow and pulse when scanning (`.stage--scanning`)
- Recording pill: now centered (left:50% transform:translateX(-50%)) with colored glow on border
- Voice `voice-start` button: purple gradient + purple glow hover
- PTT orb: enlarged to 124px, purple active state, two animated `::before`/`::after` ring-pulse rings when listening
- Waveform bars (`.waveform` / `.wave-bar`): 7-bar equalizer with blue→purple gradient, staggered wave animation; shown above PTT when talking
- Transcript: removed container panel; each message is now an independent chat bubble (`.t-bubble`) — user text aligns left, Recall answers align right with purple glass background
- Recalled spotlight: stronger gradient background, drop-shadow glow on both border and container; scale entrance animation
- Memory cards: hover lift (`box-shadow + border-color` transition); thumbnail scale-on-hover; location-group dot now has glow
- Chips: darker glass background
- Lightbox: stronger blur and shadow, blue-tint close button
- Animations: `float` (empty state), `ring-out` (PTT rings), `wave` (waveform bars), `corner-glow` (viewfinder), `scan-line` (camera sweep); all polished with cubic-bezier easing

### Changed — `frontend/src/App.jsx`
- Header: replaced plain `<h1>` with `.header-brand` (icon + title); added `.status-chip` (Live/Offline pill, hidden before camera starts)
- Stats bar: numbers wrapped in `.stats-value` spans for accent-color highlighting
- Stage: added `.stage--scanning` class to drive CSS viewfinder animation; added 4 `.vf-corner` divs (shown only while running)
- Waveform: 7 `.wave-bar` divs (with `--i` CSS custom property for stagger) rendered above PTT when `talking === true`
- Transcript: added `.t-bubble` class to both `<p>` tags so they render as chat bubbles

### Build
- CSS: 12 KB → 18 KB (gzip 4.6 KB) — all new visual effects
- JS: unchanged 161 KB

---

## Week 3 Refinement (2026-06-19)

### Added
- **`backend/memory.py`**
  - `clear_all()` — deletes every ChromaDB entry and thumbnail; returns count deleted
  - `stats()` — aggregate snapshot: `total`, `distinct_locations`, `locations[]`, `top_objects[]`, `last_scan_ts`
- **`backend/main.py`**
  - `_flash_blocked()` helper — single place that decides whether a Flash call is allowed; returns a human message or `None`
  - `_charge_flash()` helper — advances `_last_flash_call`, `_next_scan_at`, `_flash_calls_today`; eliminates the previous copy-paste between `_ingest_loop` and `analyze`
  - `DELETE /memory` — clears all memories (returns `{"cleared": N}`)
  - `GET /api/stats` — returns memory stats + flash budget info; tested live against running server
- **`backend/tools.py`**
  - `list_locations` function declaration added to `RECALL_TOOL` — answers "what have you seen?", "what locations do you know?"
  - `handle_tool_call` — new `list_locations` branch: calls `memory.stats()`, returns `{locations, count, summary}` as a speakable sentence
- **`frontend/src/App.jsx`**
  - `distinctLocations` derived state (Set of unique location labels from timeline)
  - `clearAll` callback — confirms, calls `DELETE /memory`, clears timeline + recalled state
  - Stats bar rendered below header when memories exist: "N memories · M locations"
  - "Clear" button in timeline header triggers `clearAll`
  - Auto-dismiss `error` after 8 s (useEffect on `error` state)
- **`frontend/src/App.css`**
  - `.stats-bar` — centered muted mini-bar with slide-in animation
  - `.stats-dot` — divider between stats items
  - `.clear-all` — ghost pill button with danger-color hover

### Verified
- Server started cleanly with Python 3.14 (`py -m uvicorn ...`)
- `/health` → 200, `/api/stats` → 200 (`total:0` on empty store), `/memory` → 200 `[]`
- Frontend builds cleanly (`vite build`, 160 KB JS, 12 KB CSS)

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

### Bug fixes (same session — post-phone-test)
- **`RECALL_MAX_DISTANCE` raised 1.0 → 1.4** — 1.0 maps to cosine similarity ≥ 0.5, too strict for question-vs-observation matching ("where is my charger" vs. "desk scene with electronic accessories"). 1.4 is just under √2 (fully orthogonal vectors), accepting anything with semantic overlap while still rejecting genuinely unrelated queries
- **Voice auto-restarts after tool call** — Gemini Live `session.receive()` exhausts after a complete tool-call round-trip; `_runner` now loops: drains stale queue signals and reconnects immediately, keeping voice alive across multiple questions without needing stop/start
- **Tool call block wrapped in try/except** in `live.py` — prevents a bad `FunctionResponse` or `send_tool_response` error from crashing the entire receive loop
- **Distance logging** added to `tools.py` — server console prints `top_dist=X.XXX confident=True/False (threshold=1.4)` per query for ongoing calibration

### Key decisions
- ChromaDB dispatched via `asyncio.to_thread` — keeps the receive loop non-blocking during the sync embedding+query call
- `RECALL_MAX_DISTANCE = 1.4` (L2, all-MiniLM-L6-v2) — calibrate down toward 1.1 if false positives appear
- Spotlight card clears on new talk press so it always reflects the current query's match
- Auto-restart in `_runner` (not in `run_live`) — keeps the queue alive between sessions so audio pump continuity is preserved

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
