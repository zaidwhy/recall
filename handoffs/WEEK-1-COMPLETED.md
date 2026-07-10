---
title: Recall — Week 1 Completed (Handoff)
date: 2026-06-16
project: recall
status: Week 1 complete (verified on phone); plan refined (PR #1); Week 2 unblocked (ChromaDB works on 3.14)
---

# Recall — Week 1 Completed ✅

> **Resume in one line:** "Load handoffs/WEEK-1-COMPLETED.md and start Week 2 — memory ingestion (ChromaDB store + scene-change sampling + timeline UI + record toggle)."

> **Repo:** `github.com/syzayd/recall` (**private**, default branch `master`). Plan refinement = **PR #1** (`refine-plan-mobile-first`), docs-only, ready to merge. `gh` is authed as `syzayd`.

Recall is a flagship portfolio project: an AI with a **photographic memory of your physical
world**. Your phone is the camera (laptop has no webcam → mobile-first, and portable is a
feature, not a workaround). It watches your space, builds an episodic memory of objects/places,
and answers "where/when did I…?" out loud.

---

## What we built (Week 1) — all verified on Zaid's phone

Two architectural paths, both proven end-to-end over a single cloudflared tunnel:

| # | Hello-world | What it does | Status |
|---|-------------|--------------|--------|
| 1 | **Capture** | Phone rear camera → Vite/React (`getUserMedia` `facingMode:'environment'`) → FastAPI `/ws` WebSocket. Samples a frame every 2s (~30 KB JPEG). | ✅ frames land server-side |
| 2 | **Vision (ingestion path, cheap)** | Tap "What am I looking at?" → frame → **Gemini Flash** (`gemini-2.5-flash`) → structured observation `{objects, location_label, description}` → shown on phone. ~3.7–4.3s. | ✅ correctly read a desk scene |
| 3 | **Voice (interaction path, on-demand)** | Push-to-talk → mic PCM16@16k → **Gemini Live** → spoken reply (PCM@24k) + live captions. | ✅ heard the reply on-device |

### The key design decision (free-tier safe + mobile)
**Single origin + one tunnel.** FastAPI serves the built frontend (`frontend/dist`) AND the
`/ws` WebSocket on **one port (8000)**, fronted by a cloudflared quick tunnel. The phone loads
an `https` page and the WebSocket upgrades to `wss` automatically — no mixed-content, no second
tunnel, and it's genuinely portable (demo from any phone, anywhere).

**Decoupled paths** keep us inside the Gemini free tier: cheap **Gemini Flash** for vision
(generous RPD), and a **Gemini Live** session only while the user is actively talking.
> ⚠️ **NEVER enable billing** on the Gemini project — it deletes the free tier entirely.

---

## Project structure (as of Week 1)

```
recall/
├── backend/
│   ├── main.py          # FastAPI: serves dist/, /ws (frames, analyze, live control), /health
│   ├── perception.py    # Gemini Flash → structured Observation (pydantic response_schema)
│   ├── live.py          # Gemini Live session relay (push-to-talk, manual activity detection)
│   ├── memory.py        # STUB — Week 2 (ChromaDB)
│   ├── tools.py         # STUB — Week 3 (recall_memory function-calling tool)
│   └── requirements.txt
├── frontend/
│   ├── public/pcm-worklet.js   # mic-capture AudioWorklet (real file, NOT a data: URL)
│   ├── src/
│   │   ├── App.jsx      # camera + analyze + push-to-talk voice UI
│   │   ├── audio.js     # resample 16k, Int16<->Float32, AudioPlayer (gapless 24k playback)
│   │   ├── App.css
│   │   └── main.jsx
│   ├── vite.config.js   # dev proxy /ws -> :8000
│   └── package.json
├── eval/benchmark.py    # STUB — Week 4 (recall@k + latency)
├── data/                # gitignored: last_frame.jpg, live_test.wav (debug artifacts)
├── .env                 # gitignored: GEMINI_API_KEY (billing OFF)
├── .env.example
└── DISCUSSION.md        # full decisions log
```

---

## How to run (the demo / mobile path)

> Toolchain note: on this machine **node** and **cloudflared** are NOT on the Git Bash PATH.
> Prepend: `export PATH="/c/Program Files/nodejs:/c/Program Files (x86)/cloudflared:$PATH"`

```bash
# 1. build the frontend (produces frontend/dist served by FastAPI)
cd frontend && npm install && npm run build && cd ..

# 2. start the backend (serves dist + /ws on one origin)
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 3. open a public HTTPS tunnel (free, no signup)
cloudflared tunnel --url http://localhost:8000
#    -> prints https://<random>.trycloudflare.com  (ephemeral; new URL each run)

# 4. open that URL on the PHONE:
#    Start camera → allow cam+mic → "What am I looking at?" / 🎙 Start voice → hold to talk
```

Backend deps for Week 1 (already installed): `fastapi uvicorn[standard] python-dotenv
websockets pillow google-genai`.

---

## Hard-won learnings (don't rediscover these)

- **Live model id:** use **`gemini-3.1-flash-live-preview`**. The `.env` placeholder
  `gemini-2.5-flash-live` does **not** exist. (List Live models via `client.models.list()`
  filtering `supported_actions` for `bidiGenerateContent`.)
- **Push-to-talk needs MANUAL activity detection:** set
  `RealtimeInputConfig(automatic_activity_detection=AutomaticActivityDetection(disabled=True))`
  and send `activity_start` on press / `activity_end` on release. Automatic VAD won't fire
  without trailing silence, so a naive relay returns no audio.
- **Audio formats:** mic in = PCM16 **16 kHz** mono (`Blob mime_type="audio/pcm;rate=16000"`);
  Gemini audio out = PCM **24 kHz**. Resample in the browser based on the actual AudioContext rate.
- **AudioWorklet on iOS Safari:** load it from a **real same-origin file** (`/pcm-worklet.js`
  in `public/`), NOT a Vite-inlined `data:` URL — iOS rejects `data:` URLs for `addModule`.
- **Camera/mic need a secure context:** phone-over-LAN (`http://192.168.x.x`) fails silently.
  Always use the `https://*.trycloudflare.com` tunnel URL.
- **Python 3.14 gotchas:** `audioop` was removed (resample manually). **chromadb 1.5.9 DOES
  install + run on 3.14** (verified — semantic query works; no 3.12 venv needed). It ships a
  local ONNX embedding model (`all-MiniLM-L6-v2`, cached in `~/.cache/chroma`) so embeddings
  are **free + offline** by default — no Gemini embedding calls required for Week 2.

---

## What's next

### Week 2 — Memory ingestion (the next session) — environment is READY
ChromaDB is installed + verified, so dive straight in:
1. `backend/memory.py`: wrap a `chromadb.PersistentClient(path="data/chroma")`. Implement
   `log_observation(obs) -> id` (store the Flash observation's `description` as the document
   for embedding, with metadata `{objects(joined), location_label, timestamp, thumbnail_path}`)
   and `recall_memory(query, k=3, since/until) -> [obs]` (semantic query + optional time filter
   via `where`). Default local ONNX embeddings are fine (free/offline).
2. Save a **thumbnail** per stored observation to `data/thumbnails/<id>.jpg` (reuse the frame
   already saved to `data/last_frame.jpg`); keep the path in metadata.
3. `backend/perception.py`: add **scene-change detection** (e.g. downscale + mean-abs-diff
   between consecutive frames over a threshold) so only changed frames are analyzed — an
   "always-on while recording" ingestion loop in `main.py`, quota-aware (throttle min seconds
   between Flash calls).
4. Frontend: a **record on/off toggle** (gate ingestion), a **memory timeline/gallery**
   (thumbnails + labels + time), and **delete** controls (privacy-by-design).
- Note: the WS already saves the latest frame server-side; the ingestion loop can analyze that.

### Week 3 — The magic (recall)
- `backend/tools.py`: wire **`recall_memory(query)`** as a function-calling tool into the Live
  session (`tools=` in LiveConnectConfig). Then: "Recall, where did I leave my charger?" →
  semantic + temporal search → spoken answer + the remembered frame.

### Week 4 — Credibility
- `eval/benchmark.py`: staged object placements → scripted questions → **recall@1/@3 + latency**,
  printed into the README.

### Weeks 5–6 — Polish + ship
- UI polish, accessibility mode (continuous narration), staged demo scenarios, record the **60s
  killer demo video** (the primary artifact), README with architecture diagram, LinkedIn
  build-in-public series.

---

## Open threads
- **Plan refinement = PR #1** (`refine-plan-mobile-first`, docs-only: `PLAN.md` added,
  `DISCUSSION.md` + `README.md` updated, mobile-first capture folded in, Live model id
  corrected to `gemini-3.1-flash-live-preview`). Review/merge into `master` when ready.
- Final product name still "Recall" (alternatives: Mnemo, Déjà, Total Recall).
- Live hosted demo vs. video-only — decide later; the **demo video is the priority artifact**.
