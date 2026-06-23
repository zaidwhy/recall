# Recall — Master Project Log

**Project:** Recall — AI with photographic memory of the physical world  
**Repo:** github.com/syzayd/recall  
**Stack:** FastAPI · Gemini Flash (vision) · Gemini Live (voice) · ChromaDB · Vite/React  
**Started:** 2026-06-16 · **Last updated:** 2026-06-23  

---

## Table of Contents

1. [Project Genesis — Planning Session (2026-06-16)](#1-project-genesis--planning-session-2026-06-16)
2. [Week 1 — Capture + Vision + Voice (2026-06-15/16)](#2-week-1--capture--vision--voice-2026-06-1516)
3. [Week 2 — Memory Ingestion (2026-06-16)](#3-week-2--memory-ingestion-2026-06-16)
4. [Week 3 — Recall Tool / The Magic (2026-06-17)](#4-week-3--recall-tool--the-magic-2026-06-17)
5. [Bug-Fix + Model Crisis Session (2026-06-17 evening)](#5-bug-fix--model-crisis-session-2026-06-17-evening)
6. [UX + Rate-Limit Infrastructure Session (2026-06-18)](#6-ux--rate-limit-infrastructure-session-2026-06-18)
7. [Week 3 Refinement (2026-06-19)](#7-week-3-refinement-2026-06-19)
8. [Week 4 — Object-Centric Memory + Search API (2026-06-22)](#8-week-4--object-centric-memory--search-api-2026-06-22)
9. [UI Overhaul — Premium Redesign (2026-06-23)](#9-ui-overhaul--premium-redesign-2026-06-23)
10. [Architecture Overview (current)](#10-architecture-overview-current)
10. [Permanent Rules and Constraints](#10-permanent-rules-and-constraints)
11. [File-by-File Ownership](#11-file-by-file-ownership)
12. [Dead Ends — Never Retry](#12-dead-ends--never-retry)
13. [Pending / Next Steps](#13-pending--next-steps)

---

## 1. Project Genesis — Planning Session (2026-06-16)

**Date:** 2026-06-16 ~14:38 IST  
**Handoff:** `handoffs/HANDOFF-2026-06-16-1438.md`

### What happened
- Evaluated 4 project directions for a flagship AI portfolio piece:
  - Autonomous coding agent
  - Eval platform
  - Real-time multimodal agent
  - Multi-agent swarm
- **Selected:** Real-time multimodal agent — specifically "Recall", an AI with episodic photographic memory of the user's physical space.
- **Positioning angle:** physical-world spatial memory (camera), NOT screen/audio capture (Rewind/Limitless). The moat is the episodic memory system (ChromaDB + embeddings + semantic/temporal retrieval via function calling).

### Key decisions made
| Decision | Rationale |
|----------|-----------|
| Gemini Live API over OpenAI Realtime | Cheaper, free tier, native video+audio+function-calling, ~200ms latency |
| ChromaDB (local) for memory | Free, persistent, no cloud calls for embeddings |
| FastAPI + Vite/React | Familiar Python async, WebSocket support |
| Decoupled ingestion (Flash) vs interaction (Live) | Flash = generous free RPD for background watching; Live = only during active voice Q&A. Critical for free-tier survival |
| Single-origin, single cloudflared tunnel | Phone loads HTTPS; WS upgrades to WSS automatically — no mixed-content, no second tunnel |
| "Never enable billing" rule | Enabling billing on the Gemini project permanently removes the free tier — all calls become paid |
| 6-week flagship scope | Depth + polish + measurable metrics (recall@k, latency) = recruiter-grade anchor piece |

### What was rejected
- Always-on Gemini Live for continuous ingestion — free-tier session caps + rate limits make it infeasible
- Generic "JARVIS" desktop assistant — overdone in portfolios
- Interview coach, fitness form coach — not novel enough

### Files created
- `README.md` (initial stub)
- `DISCUSSION.md` (all research, decisions, architecture)
- `.env.example`
- `.gitignore`
- Project skeleton: `backend/`, `frontend/`, `eval/`
- `handoffs/HANDOFF-2026-06-16-1438.md`

---

## 2. Week 1 — Capture + Vision + Voice (2026-06-15/16)

**Git tag:** `week-1` (approximately)  
**Handoff:** `handoffs/WEEK-1-COMPLETED.md`

### Goal
Prove the three primitives work end-to-end on a real phone:
1. Phone rear camera → backend WebSocket
2. Frame → Gemini Flash → structured observation
3. Mic audio → Gemini Live → spoken reply on phone

### What was built

#### `backend/main.py`
- FastAPI app serving `frontend/dist` + `/ws` WebSocket on port 8000 (single origin)
- `frame` WS message: accepts JPEG from phone, saves to `data/last_frame.jpg`, sends `ack`
- `analyze` WS message: on-demand Gemini Flash call → sends `observation` back
- `live_start` / `live_stop` / `talk_start` / `talk_end`: relay control for Gemini Live session
- `ping` / `pong` keepalive
- `/health` endpoint

#### `backend/perception.py`
- `analyze_frame(jpeg_bytes)` → calls Gemini Flash with pydantic `response_schema`
- Returns `{objects, location_label, description, timestamp, latency_ms}`
- `VISION_MODEL = gemini-2.5-flash` (default; overridable via env)

#### `backend/live.py`
- `run_live(websocket, audio_in)` — opens a Gemini Live session, relays PCM audio both directions
- Manual activity detection: `automatic_activity_detection=disabled`, sends `ActivityStart`/`ActivityEnd` on push-to-talk
- Audio in: PCM16 @ 16 kHz; audio out: PCM @ 24 kHz
- Working model: `gemini-3.1-flash-live-preview`

#### `frontend/src/App.jsx`
- Rear camera (`getUserMedia {facingMode: 'environment', audio: true}`)
- Sends frames every 2s via WebSocket
- "Analyze" button → on-demand Flash call
- Push-to-talk button → hold sends mic audio, release stops

#### `frontend/src/audio.js`
- `AudioPlayer` — gapless 24 kHz PCM playback via Web Audio API
- `downsampleTo16k` — resamples mic audio
- `f32ToInt16` — converts Float32Array to Int16Array

#### `frontend/public/pcm-worklet.js`
- Mic capture AudioWorklet (real same-origin file — required for iOS Safari; `data:` URLs are blocked)

#### `frontend/vite.config.js`
- Dev-mode proxy: `/ws` → `localhost:8000`

### Verified on phone
- Phone rear camera → frames arriving server-side ✅
- "What am I looking at?" → correct desk scene observation from Gemini Flash ✅
- Push-to-talk → spoken reply heard on phone ✅

### Critical discovery
- `gemini-2.5-flash-live` does NOT exist. Correct Live model: `gemini-3.1-flash-live-preview`
- AudioWorklet on iOS Safari MUST load from a real same-origin file, not a `data:` URL

---

## 3. Week 2 — Memory Ingestion (2026-06-16)

**Git tag:** `week-2`  
**Handoff:** `handoffs/WEEK-2-COMPLETED.md`

### Goal
Build the always-on memory ingestion system: scene-change detection → Gemini Flash → ChromaDB + thumbnails → timeline UI.

### What was built

#### `backend/memory.py` (new file)
- `_col()` — `@lru_cache` ChromaDB PersistentClient at `data/chroma/`, collection `observations`
- Local ONNX embeddings: `all-MiniLM-L6-v2`, cached in `~/.cache/chroma` — free and offline, no Gemini embedding API calls
- `log_observation(obs, jpeg_bytes)` — stores description embedding + `{objects, location_label, timestamp}` metadata; saves thumbnail to `data/thumbnails/<uuid>.jpg`
- `recall_memory(query, k, since, until)` — semantic search with optional Unix timestamp range filter
- `list_all(limit)` — all observations newest-first
- `delete_observation(id)` — removes from ChromaDB and deletes thumbnail file
- **Dedup window:** same location ingested within 60s → UPDATE existing entry instead of INSERT (keeps timeline clean)
- `DEDUP_WINDOW_S = 60.0`, `DECAY_WEIGHT = 0.25`

#### `backend/perception.py` additions
- `has_scene_changed(jpeg_bytes)` — downsales frame to 64×48 grayscale, computes mean absolute pixel diff vs. last accepted frame; threshold: 12.0

#### `backend/main.py` additions
- `record_start` / `record_stop` WS messages start/cancel `_ingest_loop` async task
- `_ingest_loop`: polls `data/last_frame.jpg` every 5s → scene-change → Gemini Flash → ChromaDB + thumbnail → sends `ingested` or `updated` WS message to phone
- `GET /memory` — returns all stored observations with thumbnail URLs
- `DELETE /memory/{entry_id}` — removes one observation + thumbnail
- `/thumbnails` static mount (registered BEFORE the `/` frontend catch-all — order matters)

#### `frontend/src/App.jsx` additions
- "⏺ Record memory" / "⏹ Stop recording" toggle button
- Fetches `/memory` on WS open to restore existing timeline across sessions
- `ingested` WS handler → prepends new cards to timeline in real-time
- `updated` WS handler → refreshes existing card in-place
- `record_status` WS message keeps toggle state in sync with server
- Per-entry delete button (calls `DELETE /memory/:id`)

#### `frontend/src/App.css` additions
- Record button, pulsing ingest status, memory entry cards, thumbnail styles, delete button

### Verified on phone
- Three memory cards stored and displayed after first recording session ✅
- ChromaDB confirmed working on Python 3.14 (chromadb 1.5.9) ✅

---

## 4. Week 3 — Recall Tool / The Magic (2026-06-17)

**Git tag:** `week-3`  
**Handoffs:** `handoffs/WEEK-3-PLAN-HANDOFF.md`, `handoffs/WEEK-3-COMPLETED.md`, `handoffs/HANDOFF-2026-06-17-1904.md`

### Goal
Wire `recall_memory` as a function-calling tool into the Gemini Live session so the user can ask voice questions and get spoken answers with remembered frames.

### What was built

#### `backend/memory.py` additions
- `recall_memory` now passes `include=["documents","metadatas","distances"]` to ChromaDB — returns L2 distance per result
- `RECALL_MAX_DISTANCE = 1.4` — confidence threshold (L2 for all-MiniLM-L6-v2; just under √2 = fully orthogonal. Accepts anything with semantic overlap)
- `recall_for_tool(query, since, until)` — wraps `recall_memory`, returns `{"matches": [...], "confident": bool}`
- `_unpack` updated to accept optional `distances` list; `list_all` path unaffected

#### `backend/tools.py` (was a stub, now fully implemented)
- `RECALL_TOOL = types.Tool(function_declarations=[...])` — declares `recall_memory(query, minutes_ago?)` to Gemini
- `handle_tool_call(name, args)` — dispatches tool calls, calls `recall_for_tool`, returns speakable result dict with `{confident, matches}`
- Distance logging: server prints `top_dist=X.XXX confident=True/False (threshold=1.4)` per query for ongoing calibration

#### `backend/live.py` additions
- `tools=[tools.RECALL_TOOL]` wired into `LiveConnectConfig`
- New SYSTEM prompt: model has photographic memory identity, MUST call `recall_memory` for location/time questions, MUST NOT invent memories
- `tool_call` handling in the receive loop: dispatches via `asyncio.to_thread` (ChromaDB is sync), sends `FunctionResponse` back, pushes `recalled` WS message to phone if confident
- Try/except around the tool block — bad FunctionResponse can't crash the receive loop

#### `frontend/src/App.jsx` additions
- `recalled` state for spotlight card
- `recalled` WS message handler sets spotlight; cleared at `startTalk` (fresh query = fresh spotlight)
- Spotlight card rendered above timeline when `recalled` is set

#### `frontend/src/App.css` additions
- `.recalled` spotlight wrapper (accent border, slide-in animation)
- `.recalled-badge`, `.recalled-x` dismiss button

### Bug fixes (discovered during phone testing, same session)

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Voice drops after first Q&A | `session.receive()` exhausts after a complete tool-call round-trip (Gemini Live behavior with manual activity detection + tools) | `_runner` in `main.py` now loops: drains stale queue signals, reconnects immediately |
| False negatives (real objects not recalled) | `RECALL_MAX_DISTANCE = 1.0` maps to cosine similarity ≥ 0.5 — too strict for question-vs-observation semantic gap | Raised to 1.4 |
| Tool call crashes receive loop | No error handling around `FunctionResponse` construction | Wrapped in try/except |

### Key decision: asyncio.to_thread for ChromaDB
ChromaDB is a synchronous blocking library. Running it inline would stall audio delivery from the receive loop. All ChromaDB calls dispatched via `asyncio.to_thread`.

---

## 5. Bug-Fix + Model Crisis Session (2026-06-17 evening)

**Handoff:** `handoffs/HANDOFF-2026-06-17-2307.md`

### Model crisis — which Gemini Flash works for free?

| Model | Status |
|-------|--------|
| `gemini-2.5-flash` | ✅ 20 RPD free tier — the ONLY working option |
| `gemini-1.5-flash` | ❌ deprecated, 404 |
| `gemini-2.0-flash` | ❌ `limit: 0` on free tier (requires billing) |

**Final answer as of June 2026:** `gemini-2.5-flash` is the only Flash model that supports `generateContent` on a no-billing API key.

### Rate limiting infrastructure added to `main.py`
- `FLASH_MIN_GAP_S = 120` — 2-minute hard floor between any Flash call (was 30s)
- `FLASH_DAILY_BUDGET = 18` — hard stop before hitting the real 20 RPD limit; keeps 2 in reserve
- `_flash_calls_today` counter — incremented in both ingest loop and analyze handler; resets on server restart (Google's counter does not reset on restart)
- Budget exhaustion: ingest loop sleeps 5 minutes, analyze handler returns error message to phone
- 429 backoff: parses retry delay from error string, sleeps that many seconds + 5

### Recalled spotlight field-name bug (critical fix)
`tools.py` sends: `location`, `scene_description`, `objects_visible`, `time_ago`  
`App.jsx` was reading: `location_label`, `description`, `objects`, `minutes_ago`  
→ `recalled.objects.map()` threw TypeError on first voice query, crashing the React render.  
**Fixed:** All four field names corrected in App.jsx. Added `??[]` null guard on `objects_visible`.

### Other fixes
- `video.play()` AbortError on camera start: React re-render replaces `srcObject` before `play()` resolves — harmless race, now caught silently
- Stale log message "gemini-1.5-flash quota" updated to use `perception.VISION_MODEL` dynamically
- `import time` was missing from `main.py`
- `global _next_scan_at` declared after first use → SyntaxError; moved to top of `_ingest_loop`

### Flash budget indicator (frontend)
- `flashCalls` / `flashBudget` state (default 0/18)
- Updated on every `ingested` or `updated` WS message from backend
- Recording pill shows `· N calls left` when `flashCalls > 0`
- Pill turns yellow when budget exhausted (`.budget-warn` CSS class)

---

## 6. UX + Rate-Limit Infrastructure Session (2026-06-18)

**Handoff:** `handoffs/HANDOFF-2026-06-18-0000.md`

### New UX features

**Recording experience:**
- Auto-start recording — WS `onopen` sends `record_start` after 2s delay; no second tap needed
- `scanning` WS event sent before every Flash call → frontend shows blue "Scanning…" pill + blue sweep overlay on video
- Countdown timer — `nextScanAt` state, 1-second `setInterval`, shows `· 47s` in the pill
- Dynamic header tagline — updates to "scanning…" / "next scan in Xs" while recording
- Empty recording state — pulsing 👁 with guidance shown when `recording && timeline.length === 0 && !scanning`

**Timeline:**
- `fmtRelative(ts)` — "just now" / "3m ago" / "2h ago" / "Jun 17"
- Chip overflow — `entry.objects.slice(0, 4)` + "+N more" chip
- `@keyframes slide-in` — new cards animate in from above (0.28s ease-out)
- `document.title` effect — "Recall (3)" with live count

**Grouped timeline:**
- Entries grouped by `location_label`
- Groups sorted by most recent entry
- Location group header with dot + count badge

**Lightbox:**
- Click any thumbnail → full-screen lightbox with dismiss on backdrop click or × button

**Search:**
- Search input in timeline header — real-time client-side filter across `location_label`, `description`, `objects`

**Debug panel:**
- Flash calls: N/18
- Next scan countdown

**Backend `/health` additions:**
- Returns `vision_model`, `flash_calls_today`, `flash_budget`, `next_scan_in_s`

### Vite 4 downgrade
- Vite 5 ships Rollup 4 which uses a native `.node` binary blocked by Windows Application Control in Claude Code's process context
- Downgraded to Vite `^4.5.0` (Rollup 3 = pure JS, no native binary)
- This is permanent — do not upgrade to Vite 5 without verifying Rollup binary is unblocked

### Windows App Control
- Was blocking compiled `.pyd`/`.dll`/`.node` extensions in Claude Code's Bash
- User turned it off — backend can now run from any terminal

---

## 7. Week 3 Refinement (2026-06-19)

**Git tag:** `week-3-refine`  
**Handoff:** `handoffs/HANDOFF-2026-06-19-2352.md`

### Goal
Refactor duplicated rate-guard logic, add memory stats/clear-all, add a second voice tool, and polish the frontend.

### Backend changes

#### `backend/memory.py`
- `clear_all()` — deletes every ChromaDB entry and thumbnail; returns count deleted
- `stats()` — returns `{total, distinct_locations, locations[], top_objects[], last_scan_ts}`

#### `backend/main.py`
- Extracted `_flash_blocked() → str | None` — single authoritative check; returns human message when gated, `None` when clear. Eliminates copy-paste between `_ingest_loop` and `analyze` handler
- Extracted `_charge_flash()` — one place to advance `_last_flash_call`, `_next_scan_at`, `_flash_calls_today`
- `DELETE /memory` (no ID) → `clear_memory()` — clears all, returns `{"cleared": N}`
- `GET /api/stats` → `api_stats()` — memory stats + flash budget overlay

**Important: static mount order** — `/thumbnails` and `/api/stats` routes MUST be registered BEFORE `app.mount("/", StaticFiles(...))` or StaticFiles intercepts them and returns 403.

#### `backend/tools.py`
- Added `list_locations` function declaration to `RECALL_TOOL` — answers "what have you seen?", "what locations do you know?"
- Added `list_locations` branch in `handle_tool_call` — calls `memory.stats()`, returns `{locations, count, summary}` as a speakable sentence

### Frontend changes

#### `frontend/src/App.jsx`
- `distinctLocations` derived with `useMemo` (Set of unique `location_label` values)
- `clearAll` callback — native confirm dialog → `DELETE /memory` → clear timeline + `recalled` + `ingestCount`
- Stats bar rendered between header and camera when `timeline.length > 0`: "N memories · M locations"
- "Clear" button in timeline header
- `useEffect` on `error` — auto-clears after 8s

#### `frontend/src/App.css`
- `.stats-bar`, `.stats-dot` — centered muted mini-bar, reuses `slide-in` keyframe
- `.clear-all` — ghost pill with danger-color hover

### Verified
- `/health` → 200, `/api/stats` → 200, `/memory` → 200
- Frontend builds cleanly (Vite 4, 160 KB JS, 12 KB CSS)

---

## 8. Week 4 — Object-Centric Memory + Search API (2026-06-22)

**Handoff:** this session  
**Branch:** master

### Goal
Implement the object-centric memory backlog item and wire a REST-based memory search into the UI so users can query memories without voice.

### Backend changes

#### `backend/memory.py`
- **`find_by_object(object_name, limit, since, until)`** — new function; case-insensitive substring match against the `objects` metadata field; returns all matching observations newest-first
- **`recall_for_tool` enhanced** — now runs both semantic search (k=9) AND `find_by_object` (k=5); merges unique hits with a synthetic distance of `0.5` (treated as high-confidence exact match); then re-ranks everything by time-decay score. Voice queries like "where are my keys?" now surface exact object-name matches even when semantic similarity is low

#### `backend/main.py`
- **`GET /api/search?q=...`** — new endpoint; calls `recall_for_tool`, returns top 3 matches with thumbnail URLs. Registered before static mounts so it's never intercepted.

### Frontend changes

#### `frontend/src/App.jsx`
- `manualRecall` state — stores the top hit from a REST-driven search
- `searching` state — loading indicator for the search button
- `searchMemory` callback — calls `/api/search?q={searchQuery}`, sets `manualRecall`
- Search input `onKeyDown` — pressing Enter triggers `searchMemory`
- **"Ask" button** — appears in timeline header next to the search input; disabled when box is empty; shows "…" while loading
- **Manual recall card** — shows top hit (thumbnail, location, description, chips, relative time) with a dismiss ×; shows "No memory found" message if no matches
- `clearAll` now also clears `manualRecall`
- Search input `onChange` clears `manualRecall` (stale result disappears when query changes)

#### `frontend/src/App.css`
- `.search-ask` — accent-colored ghost pill button matching the header row height
- `.manual-recall` — panel card with slide-in animation
- `.manual-recall.mr-empty` — flex row for the "not found" state

### Also in this session: eval/benchmark.py
The benchmark harness was built in a prior session and is fully functional:
- 10 test cases (keys, charger, passport, laptop, glasses, TV remote, backpack, book, water bottle, headphones)
- 10 distractors (overlapping vocabulary, wrong locations)
- Isolated temp ChromaDB per run — production data never touched
- Metrics: Recall@1, Recall@3, median latency, P95 latency
- Updates `README.md` automatically unless `--dry-run` flag

**To run:** (in user's own PowerShell, not Claude Code Bash — onnxruntime blocked in sandboxed context)
```powershell
py -m eval.benchmark          # runs + updates README
py -m eval.benchmark --dry-run  # print only
```

---

## 9. UI Overhaul — Premium Redesign (2026-06-23)

**Branch:** master

### Goal
Make the UI dramatically more impressive for demo video and recruiter portfolio view — while keeping all existing functionality identical.

### Changes

#### `frontend/src/App.css` (complete rewrite)
- **Background**: dual radial gradients (blue top, purple side) — deep navy, not flat black
- **Header**: `.header-brand` flex wrapper with `.header-icon` (38px rounded square, accent border + shadow) and 2.5rem 900-weight gradient title (white→blue→purple) with `drop-shadow` glow
- **Status chip**: top-right Live/Offline pill; pulsing green dot when WS is connected
- **Stats bar**: values wrapped in `.stats-value` (accent blue), self-centered pill style
- **Camera viewfinder**: L-shaped corner markers (`.vf-corner`) with 0.55 opacity at rest; animated glow when scanning via `.stage--scanning`
- **Scan overlay**: rewritten as a moving scan-line sweep (`::after` pseudo-element sweeping top to bottom at 1.8s)
- **Recording pill**: centered (not left-anchored), colored border glow per state (red/amber/blue)
- **PTT orb**: 124px, purple when active, two `::before`/`::after` ring-pulse animations (`.ring-out`) radiating outward
- **Waveform bars**: 7 `.wave-bar` divs with blue→purple gradient and staggered `wave` animation, shown above PTT when talking
- **Transcript**: removed container panel; user message = left-aligned glass bubble; Recall answer = right-aligned purple gradient bubble
- **Voice button**: purple gradient + glow; purple accent throughout voice section
- **Recalled spotlight**: gradient background, dual-layer box-shadow, scale+translateY entrance
- **Memory cards**: hover lift animation; thumbnail scales on hover; location-group dot glows
- **Lightbox**: stronger blur (18px) + shadow + blue-tint border
- **Animations**: `float` (empty state), `ring-out` (PTT), `wave` (waveform), `corner-glow` (viewfinder), `scan-line` (camera sweep)

#### `frontend/src/App.jsx`
- Header wrapped in `.header-brand` + `.header-icon` + `.status-chip` (Live/Offline)
- Stats numbers wrapped in `.stats-value`
- Stage div gets `.stage--scanning` class
- 4 viewfinder corner divs rendered when `running`
- Waveform bars rendered above PTT when `talking` (7 bars with `--i` CSS custom property for stagger delay)
- Transcript `<p>` tags get `.t-bubble` class for chat-bubble layout

### Build result
- CSS: 12 KB → 18 KB gzip-4.6 KB
- JS: 161 KB (unchanged)
- Build time: 838 ms ✅

---

## 10. Architecture Overview (current)

```
Phone (HTTPS via cloudflared quick tunnel)
  │
  ├─ JPEG frames every 2s ──────────────────► data/last_frame.jpg
  │                                                │
  │                                    _ingest_loop (every 5s)
  │                                         ├─ has_scene_changed() [64×48 numpy MAD diff, threshold=12]
  │                                         ├─ _flash_blocked() [120s gap + 18/day budget]
  │                                         ├─ → "scanning" WS event to phone
  │                                         ├─ analyze_frame() → gemini-2.5-flash (structured JSON)
  │                                         └─ log_observation() → ChromaDB + thumbnail
  │                                              (dedup: same location within 60s → UPDATE)
  │
  ├─ PCM16 @ 16kHz mic audio ───────────────► live.py
  │                                         └─ Gemini Live (gemini-3.1-flash-live-preview)
  │                                              └─ recall_memory tool:
  │                                                   ├─ semantic search (all-MiniLM-L6-v2 ONNX)
  │                                                   ├─ exact object-name match (find_by_object)
  │                                                   └─ time-decay re-rank (DECAY_WEIGHT=0.25)
  │
  ├─ GET /api/search?q= ────────────────────► recall_for_tool() → top 3 matches + thumbnails
  │
  └─ WS messages (phone ← backend):
       scanning / ingested / updated / recalled / transcript / record_status / live_status / error

Data flow for memory retrieval:
  Voice query → Gemini Live → tool_call → handle_tool_call
    → recall_for_tool(query):
        1. ChromaDB semantic search, k=9
        2. find_by_object exact name match, k=5 (synthetic distance=0.5)
        3. merge unique results
        4. re-rank: score = distance + DECAY_WEIGHT * log(1 + hours_ago)
        5. top 3 → confident = (best_distance ≤ RECALL_MAX_DISTANCE=1.4)
    → FunctionResponse → Gemini speaks answer
    → "recalled" WS event → spotlight card on phone
```

---

## 11. Permanent Rules and Constraints

| Rule | Reason |
|------|--------|
| **NEVER enable billing on the Gemini API project** | Enabling billing removes the free tier permanently — all calls become paid from the first token |
| `gemini-2.5-flash` for vision | Only Flash model with free-tier `generateContent` access as of June 2026 |
| `gemini-3.1-flash-live-preview` for Live | `gemini-2.5-flash-live` does not exist |
| Always `py`, never `python` | `python` resolves to Python 3.12 (no project deps); `py` = Python 3.14.6 with all deps |
| Node/cloudflared not on PATH | Add: `$env:PATH += ";C:\Program Files\nodejs;C:\Program Files (x86)\cloudflared"` |
| Vite `^4.5.0` pinned | Vite 5/Rollup 4 uses a native `.node` binary blocked by Windows App Control |
| Static mounts after API routes | `/thumbnails` and all `/api/*` routes must be registered BEFORE `app.mount("/", ...)` |
| Run backend in user's PowerShell | Windows App Control (when ON) blocks compiled `.pyd` in Claude Code's sandbox |
| `FLASH_DAILY_BUDGET = 18` | Hard stop at 18/20 RPD to keep 2 calls in reserve for unexpected overhead |

---

## 12. File-by-File Ownership

| File | Purpose | Key constants/functions |
|------|---------|------------------------|
| `backend/main.py` | FastAPI app, WebSocket, ingestion loop, API routes | `FLASH_MIN_GAP_S=120`, `FLASH_DAILY_BUDGET=18`, `_flash_blocked()`, `_charge_flash()`, `_ingest_loop()` |
| `backend/perception.py` | Gemini Flash vision analysis, scene-change detection | `VISION_MODEL`, `analyze_frame()`, `has_scene_changed()`, `_SCENE_THRESHOLD=12.0` |
| `backend/memory.py` | ChromaDB wrapper, all memory operations | `RECALL_MAX_DISTANCE=1.4`, `DECAY_WEIGHT=0.25`, `DEDUP_WINDOW_S=60`, `log_observation()`, `recall_for_tool()`, `find_by_object()`, `stats()`, `clear_all()` |
| `backend/tools.py` | Gemini function-calling tool declarations + handlers | `RECALL_TOOL` (recall_memory + list_locations), `handle_tool_call()` |
| `backend/live.py` | Gemini Live session relay, push-to-talk, tool dispatch | `LIVE_MODEL`, `SYSTEM` prompt, `run_live()` |
| `frontend/src/App.jsx` | Full mobile UI | All state, WS setup, camera, voice, timeline, search, recall card |
| `frontend/src/App.css` | Dark-theme mobile styles | All component styles |
| `frontend/src/audio.js` | Web Audio API helpers | `AudioPlayer`, `downsampleTo16k`, `f32ToInt16` |
| `frontend/public/pcm-worklet.js` | Mic capture AudioWorklet | Must be a real file (iOS Safari rejects data: URLs) |
| `eval/benchmark.py` | Offline recall accuracy harness | `run_benchmark()`, `build_report()`, `update_readme()` |
| `CHANGELOG.md` | Session-by-session change log | Human-readable, updated each major session |
| `DISCUSSION.md` | Full research + decisions archive | Original architecture decisions, positioning, free-tier research |

---

## 12. Dead Ends — Never Retry

| Approach | Why it fails |
|----------|-------------|
| Always-on Gemini Live for background ingestion | Free-tier session caps + rate limits — instantly exhausted |
| `gemini-1.5-flash` | Deprecated, returns 404 |
| `gemini-2.0-flash` | `limit: 0` on free (no-billing) key |
| `python -m uvicorn ...` (instead of `py`) | `python` = Python 3.12, no project deps installed |
| Vite 5 / npm run build in Claude Code Bash | Rollup 4's `.node` binary blocked by Windows App Control → `ERR_DLOPEN_FAILED` |
| `@rollup/rollup-win32-x64-msvc` delete for WASM fallback | Rollup 4 has no actual WASM fallback — throws `MODULE_NOT_FOUND` |
| `RECALL_MAX_DISTANCE = 1.0` | Too strict (cosine ≥ 0.5) for question-vs-observation semantic gap; real hits come in at 1.0–1.3 |
| AudioWorklet via `data:` URL | iOS Safari blocks it; must load from same-origin file at `/pcm-worklet.js` |

---

## 13. Pending / Next Steps

### Immediate (can do anytime)
- [ ] **Phone-test `list_locations` tool** — ask "What have you seen?" with voice → verify spoken sentence lists locations correctly, no clash with `recall_memory` dispatch — **MED**
- [ ] **Phone-test the "Ask" button** — type a query in search box, press Enter or "Ask", verify manual recall card appears with correct thumbnail + fields — **MED**
- [ ] **Run eval benchmark** — in user's own PowerShell: `py -m eval.benchmark` → results printed into README — **MED**

### Calibration
- [ ] **`RECALL_MAX_DISTANCE = 1.4`** — watch server `top_dist=` logs during real use; tune down toward 1.1 if wrong objects start appearing — **LOW**
- [ ] **`GEMINI_VISION_MODEL` in `.env`** — no `.env` file exists currently; code defaults to `gemini-2.5-flash` which is correct. If a `.env` is ever added, confirm `GEMINI_VISION_MODEL=gemini-2.5-flash` — **LOW**

### Week 5 — Polish + Demo
- [ ] UI polish pass — accessibility, animation refinements
- [ ] Staged demo scenarios (keys on kitchen counter, charger on desk, book on coffee table, glasses on bathroom sink)
- [ ] **Record 60-second demo video** (the primary portfolio artifact)
- [ ] Embed demo video in README

### Week 6 — Ship the Story
- [ ] README final pass: architecture diagram, demo GIF, metrics table, "why not another AI wrapper" section
- [ ] LinkedIn build-in-public series
- [ ] Optional: free hosted deploy (Render/HF Spaces)

### Backlog
- [ ] Auto-expiry / TTL retention controls (privacy-by-design)
- [ ] Richer temporal language: "this morning", "yesterday" → date-range filters
- [ ] Memory de-duplication: merge near-identical consecutive scenes at ingestion

---

## How to Run (current)

```powershell
# 1. Build frontend (only when JSX/CSS changes)
cd C:\Users\Asus\projects\recall\frontend
npm run build

# 2. Backend (serves dist + /ws on one origin)
cd C:\Users\Asus\projects\recall
py -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
# First log line should be: Vision model: gemini-2.5-flash  |  min gap between Flash calls: 120s

# 3. Tunnel (new terminal — add cloudflared to PATH first)
$env:PATH += ";C:\Program Files (x86)\cloudflared"
cloudflared tunnel --url http://localhost:8000
# Open the printed https://*.trycloudflare.com URL on the PHONE
```

---

*Last updated: 2026-06-22 — Week 4 session (object-centric memory + /api/search + "Ask" UI)*
