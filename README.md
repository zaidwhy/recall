# Recall — an AI with a photographic memory of your world

Point your phone camera at your space. Ask out loud "where did I leave my keys?" and get a spoken answer with the exact frame it saw them in.

Built on Gemini Live (push-to-talk voice), Gemini Flash (always-on vision), and a local ChromaDB vector store for offline semantic recall.

---

## How it works

```
┌──────────────────────────────────────────────────────────────────┐
│  Phone (HTTPS via cloudflared)                                   │
│                                                                  │
│  [Camera] ──2s frames──► [WebSocket] ──► [FastAPI backend]       │
│                                               │                  │
│                              ┌────────────────┴──────────────┐   │
│                              │  Ingestion pipeline           │   │
│                              │  has_scene_changed()          │   │
│                              │   └─ pixel diff (numpy)       │   │
│                              │  analyze_frame()              │   │
│                              │   └─ Gemini Flash (vision)    │   │
│                              │  log_observation()            │   │
│                              │   └─ ChromaDB (local)         │   │
│                              └───────────────────────────────┘   │
│                                               │                  │
│  [🎤 Hold to ask] ──mic audio──► [Gemini Live session]           │
│                                   └─ recall_memory() tool        │
│                                       └─ ChromaDB search         │
│                                           └─ spoken answer +     │
│                                              spotlight card       │
└──────────────────────────────────────────────────────────────────┘
```

- **Ingestion**: frames are pixel-diff'd against the last accepted scene; only changed scenes hit the vision API — prevents burning the free-tier quota on static views
- **Recall**: Gemini Live calls `recall_memory(query)` as a function; ChromaDB returns top-9 candidates, re-ranked with time decay (`score = distance + 0.25 × log(1 + hours_ago)`), top-3 returned
- **Confidence gate**: matches beyond L2 distance 1.4 are not surfaced — the model says "I haven't seen that yet" rather than hallucinating a location
- **Dedup**: same location seen within 60 s → updates existing memory in-place rather than growing the store
- **Embedding model**: `all-MiniLM-L6-v2` via ChromaDB default — local ONNX, no cloud calls, no cost

---

## Why this isn't just another AI wrapper

Most "AI + camera" projects pipe a frame to a vision model and echo the response. Recall does something different:

1. **Persistent spatial memory.** Descriptions are embedded into a local vector store that survives across sessions. The AI doesn't re-see your room — it *remembers* it.
2. **Time-decay re-ranking.** Recent sightings score higher than old ones. If your keys moved from the kitchen counter to your pocket, the recall reflects that.
3. **Gemini Live function calling.** The voice AI doesn't know where things are — it calls a tool. The tool searches the vector store. This is how you get a reliable answer instead of a hallucinated one.
4. **Free, local embeddings.** ChromaDB's default ONNX model runs entirely on-device. No embedding API, no third-party data retention.
5. **Quota-aware ingestion.** The ingest loop enforces a 120-second minimum between vision API calls and a daily budget counter visible on screen — so 20 free-tier calls last an entire demo session.

---

## Features

### Live recording experience
- **Auto-start recording** — camera opens and recording begins automatically; no second tap required
- **Scanning indicator** — when a Flash call fires, the recording pill turns blue ("Scanning…") and a sweep overlay appears on the video so you always know when a capture is happening
- **Countdown timer** — pill shows `· 87s` counting down to the next available scan, then `· ready` when the gap has elapsed
- **Budget indicator** — pill shows remaining daily calls (e.g. `· 14 calls left`); turns yellow when budget is exhausted
- **Dynamic header** — tagline updates live: "scanning…" during a Flash call, "next scan in Xs" between calls

### Memory timeline
- **Grouped by location** — memories are grouped by `location_label` (e.g. "kitchen counter", "desk"), sorted by most recent activity per group
- **Relative timestamps** — cards show "3m ago" / "2h ago" instead of a clock time; updates as you use the app
- **Slide-in animation** — new memory cards animate in from above when they arrive
- **Search** — filter across location, description, and object chips in real time
- **Lightbox** — tap any thumbnail to view it full-screen
- **Chip overflow** — cards with more than 4 object tags show "+N more" to keep cards compact
- **Document title** — browser tab shows `Recall (3)` with the current memory count

### Voice Q&A
- **Push-to-talk** — hold the circular button; release to send. Manual activity detection — no trailing silence required
- **Tap-to-ask** — tap once to start a 7-second auto-timed turn (useful when your hands are occupied)
- **Recalled spotlight** — when Recall finds a match, the exact thumbnail + location + time is surfaced as a card below the transcript
- **Haptic feedback** — phone vibrates when PTT is pressed (where supported)

### Robustness
- **WS reconnect banner** — if the tunnel drops, a yellow banner appears with a one-tap reconnect button
- **Empty recording state** — when recording has started but no scenes exist yet, shows a helpful prompt instead of a blank screen
- **Rate-limit backoff** — on 429 errors the backend parses the retry delay from Gemini's response and sleeps exactly that long
- **Daily budget guard** — ingest loop and analyze handler share a counter; stops at 18/20 to keep 2 in reserve

---

## Quick start

**Prerequisites:** Python 3.11+, Node 18+, a Gemini API key (free tier, no billing required), cloudflared.

```bash
# 1. Backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Add your key to .env
echo GEMINI_API_KEY=your_key_here > .env

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
# First log line should say: Vision model: gemini-2.5-flash | min gap: 120s

# 2. Tunnel  (gives the phone an HTTPS URL — required for camera + mic)
cloudflared tunnel --url http://localhost:8000

# 3. Frontend  (only needed once, or after UI changes)
cd frontend && npm install && npm run build

# 4. Open the tunnel URL on your phone → Start camera → recording begins automatically
```

> **Free tier note:** `gemini-2.5-flash` has 20 vision calls per day on the free tier. The recording pill shows how many calls remain. Quota resets at midnight. Do **not** enable billing — it removes the free tier.

---

## Eval Results

*Last run: 2026-06-17 — 20 observations (10 targets + 10 distractors)*

| Metric | Value |
|--------|-------|
| Recall@1 | 10/10 (100%) |
| Recall@3 | 10/10 (100%) |
| Median latency | 149.3 ms |
| P95 latency | 166.9 ms |
| Corpus | 20 observations |

<details>
<summary>Per-case breakdown</summary>

| # | Test case | Query | @1 | @3 | Dist | ms |
|---|-----------|-------|----|----|------|----|
| 1 | keys / kitchen counter | `where are my keys` | ✓ | ✓ | 0.885 | 167.3 |
| 2 | phone charger / bedroom desk | `where is my phone charger` | ✓ | ✓ | 0.893 | 147.9 |
| 3 | passport / desk drawer | `where is my passport` | ✓ | ✓ | 0.943 | 150.7 |
| 4 | laptop / couch | `where did I leave my laptop` | ✓ | ✓ | 1.132 | 143.5 |
| 5 | glasses / bathroom sink | `where are my glasses` | ✓ | ✓ | 0.924 | 152.0 |
| 6 | TV remote / coffee table | `where is the TV remote` | ✓ | ✓ | 0.680 | 145.9 |
| 7 | backpack / front door | `where is my backpack` | ✓ | ✓ | 0.839 | 147.9 |
| 8 | book / nightstand | `where is the book I was reading` | ✓ | ✓ | 1.104 | 144.8 |
| 9 | water bottle / kitchen table | `where did I leave my water bottle` | ✓ | ✓ | 1.062 | 157.8 |
| 10 | headphones / office desk | `where are my headphones` | ✓ | ✓ | 0.840 | 166.9 |

To reproduce: `python -m eval.benchmark` (creates an isolated temp ChromaDB — never touches production data).

</details>

---

## Privacy

- **What leaves your device:** JPEG frames (sent to Gemini Flash for analysis), mic audio (streamed to Gemini Live during voice sessions)
- **What stays local:** all memory descriptions, embeddings, and thumbnails — stored in `data/` on your machine, never uploaded
- **Embeddings:** generated locally via ONNX (`all-MiniLM-L6-v2`) — no embedding API calls
- **To delete everything:** `rm -rf data/` — the ChromaDB collection and all thumbnails are gone

---

## Stack

| Layer | Technology |
|-------|-----------|
| Voice | Gemini Live (`gemini-3.1-flash-live-preview`) — push-to-talk, function calling |
| Vision | Gemini Flash (`gemini-2.5-flash`) — structured JSON output, scene analysis |
| Embeddings | `all-MiniLM-L6-v2` via ChromaDB (local ONNX, no API cost) |
| Vector store | ChromaDB (persistent local store, L2 distance, time-decay re-ranking) |
| Backend | FastAPI + WebSocket (single server for both frontend and WS) |
| Frontend | React + Vite 4 (pinned — Vite 5 native binary blocked on some Windows setups) |
| Tunnel | cloudflared (HTTPS for phone camera + mic permissions) |

---

## Project status

| Week | Focus | Status |
|------|-------|--------|
| 1 | Camera → vision → push-to-talk voice round-trip | ✅ Done |
| 2 | Always-on ingestion → ChromaDB → timeline UI | ✅ Done |
| 3 | `recall_memory` tool → spoken recall + spotlight card | ✅ Done |
| 4 | `eval/benchmark.py` → recall@1/@3 + latency report | ✅ Done |
| 5 | UI polish — PTT button, tap-to-ask, search, groups, lightbox | ✅ Done |
| 6 | Demo video + LinkedIn build-in-public series | ⬜ Planned |
