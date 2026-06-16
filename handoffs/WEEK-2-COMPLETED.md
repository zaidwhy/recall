---
title: Recall — Week 2 Completed (Handoff)
date: 2026-06-16
project: recall
status: Week 2 complete (verified on phone — 3 memory cards stored); Week 3 unblocked
---

# Recall — Week 2 Completed ✅

> **Resume in one line:** "Load handoffs/WEEK-2-COMPLETED.md and start Week 3 — wire recall_memory as a function-calling tool into the Gemini Live session."

> **Repo:** `github.com/syzayd/recall` (now **public**, default branch `master`). All Week 2 changes committed and pushed.

Recall is a flagship portfolio project: an AI with a **photographic memory of your physical world**. Phone is the camera (mobile-first, portable is a feature). It watches your space, builds an episodic memory of objects/places, and answers "where/when did I…?" out loud.

---

## What we built (Week 2) — verified on Zaid's phone

| # | Feature | What it does | Status |
|---|---------|--------------|--------|
| 4 | **Scene-change detection** | `has_scene_changed(jpeg)` in `perception.py` — 64×48 grayscale MAD, threshold 12.0 | ✅ |
| 5 | **ChromaDB memory store** | `backend/memory.py` — PersistentClient at `data/chroma/`, local ONNX embeddings (free/offline) | ✅ |
| 6 | **Always-on ingestion loop** | `record_start`/`record_stop` WS → `_ingest_loop` task in `main.py`, polls `data/last_frame.jpg` every 5s | ✅ |
| 7 | **Thumbnail gallery** | Thumbnails saved to `data/thumbnails/<uuid>.jpg`, served at `/thumbnails/<id>.jpg` | ✅ |
| 8 | **Timeline UI** | Record toggle, memory cards (thumb + label + description + chips + time), delete controls | ✅ 3 cards on phone |

---

## Project structure (as of Week 2)

```
recall/
├── backend/
│   ├── main.py          # FastAPI: /ws (frame/analyze/live/record), /memory GET+DELETE, /thumbnails static
│   ├── perception.py    # analyze_frame (Gemini Flash) + has_scene_changed (MAD diff)
│   ├── live.py          # Gemini Live session relay (push-to-talk, manual activity detection)
│   ├── memory.py        # ChromaDB wrapper: log_observation, recall_memory, list_all, delete_observation
│   ├── tools.py         # STUB — Week 3 (recall_memory function-calling tool)
│   └── requirements.txt
├── frontend/
│   ├── public/pcm-worklet.js   # mic-capture AudioWorklet (real file, NOT data: URL)
│   ├── src/
│   │   ├── App.jsx      # camera + analyze + push-to-talk + record toggle + memory timeline
│   │   ├── audio.js     # resample 16k, Int16<->Float32, AudioPlayer (gapless 24k)
│   │   ├── App.css
│   │   └── main.jsx
│   ├── vite.config.js
│   └── package.json
├── eval/benchmark.py    # STUB — Week 4
├── handoffs/
│   ├── WEEK-1-COMPLETED.md
│   └── WEEK-2-COMPLETED.md  ← this file
├── CHANGELOG.md         # full session-by-session log
├── data/                # gitignored: chroma/, thumbnails/, last_frame.jpg
├── .env                 # gitignored: GEMINI_API_KEY (billing OFF)
└── DISCUSSION.md
```

---

## How to run

> Node and cloudflared are NOT on the PowerShell PATH by default.

```powershell
# Terminal 1 — build frontend (only needed when JSX/CSS changes)
cd C:\Users\Asus\projects\recall\frontend
npm run build

# Terminal 2 — start backend
cd C:\Users\Asus\projects\recall
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Terminal 3 — tunnel
$env:PATH += ";C:\Program Files (x86)\cloudflared"
cloudflared tunnel --url http://localhost:8000
# → prints https://<random>.trycloudflare.com  (ephemeral; new URL each run)

# Open that URL on the phone:
# Start camera → allow cam+mic → tap "⏺ Record memory" → move to new scene
# → wait ~5s → memory card appears with thumbnail
```

---

## Architecture decisions (don't re-derive)

### Memory store
- **ChromaDB PersistentClient** at `data/chroma/` — local, no server, no billing
- **Embeddings**: local ONNX model `all-MiniLM-L6-v2` (cached in `~/.cache/chroma`) — free and offline
- **Thumbnails**: `data/thumbnails/<uuid>.jpg`, served via FastAPI `/thumbnails` static mount
- **Static mount order** matters: `/thumbnails` is mounted BEFORE the `/` frontend catch-all, otherwise the SPA catch-all intercepts thumbnail requests

### Ingestion loop
- Runs as an `asyncio.create_task` per WebSocket connection (started/stopped by `record_start`/`record_stop`)
- Polls `data/last_frame.jpg` (written by the `frame` WS handler) — no second WS path needed
- 5s minimum interval between Flash calls (quota guard)
- Scene-change gate before every Flash call — saves free-tier quota significantly
- First `has_scene_changed` call always returns `True` (initializes the baseline)

### Timeline restore
- `GET /memory` is fetched in the WS `onopen` handler → existing memories shown immediately on camera start
- `ingested` WS messages prepend new cards in real-time without polling

---

## Hard-won learnings (Week 2)

- **ChromaDB `n_results` must be ≤ `col.count()`** — guard with `if count == 0: return []` and `n_results=min(k, count)`
- **Static mount order** in FastAPI/Starlette: first matching mount wins. Always register specific paths (`/thumbnails`) before the SPA catch-all (`/`)
- **`data/` is gitignored** — ChromaDB files, thumbnails, and `last_frame.jpg` never commit. That's intentional (privacy-by-design, local-only memory)

---

## What's next

### Week 3 — The magic (recall) ← START HERE

Wire `recall_memory` as a **function-calling tool** into the Gemini Live session:

1. **`backend/tools.py`**: define a `recall_memory` tool declaration for the Live API
   ```python
   RECALL_TOOL = types.Tool(function_declarations=[types.FunctionDeclaration(
       name="recall_memory",
       description="Search Recall's visual memory for objects or scenes",
       parameters=types.Schema(
           type=types.Type.OBJECT,
           properties={"query": types.Schema(type=types.Type.STRING)},
           required=["query"],
       ),
   )])
   ```
2. **`backend/live.py`**: pass `tools=[RECALL_TOOL]` in `LiveConnectConfig`. Handle `tool_call` turns from Gemini: call `memory.recall_memory(query)`, send `tool_response` back. Optionally include a thumbnail URL in the response so the UI can show it.
3. **Frontend**: handle a new `recalled` WS message type to highlight the matched memory card in the timeline.

End-to-end goal: "Recall, where did I leave my charger?" → Gemini calls the tool → semantic search → spoken answer naming location + time.

### Week 4 — Credibility
- `eval/benchmark.py`: staged object placements → scripted questions → recall@1/@3 + latency, printed into README

### Weeks 5–6 — Polish + ship
- 60-second killer demo video (primary artifact)
- README with architecture diagram
- LinkedIn build-in-public series

---

## Checkpoint / restore

All Week 2 code is committed and pushed to `github.com/syzayd/recall` (public, master).
To restore to this exact state:
```bash
git clone https://github.com/syzayd/recall
git checkout master  # Week 2 tip
```
The `data/` directory (ChromaDB + thumbnails) is local-only and not versioned — that's intentional.
