---
title: Recall — Week 3 Plan Handoff (Execute in a fresh session)
date: 2026-06-17
project: recall
status: Week 1 & 2 complete + verified on phone. Week 3 NOT started — this is the execution plan.
---

# Recall — Week 3 Plan Handoff: "The Magic" (Recall via Voice)

> **Resume in one line:** "Load handoffs/WEEK-3-PLAN-HANDOFF.md and execute Week 3 — wire
> recall_memory as a function-calling tool into the Gemini Live session, with a confidence
> gate, temporal filter, and a remembered-frame spotlight card."

This document is **self-contained**. You do not need any prior chat context to execute it.

---

## 0. What Recall is (30-second context)

Recall is a flagship portfolio project — **an AI with a photographic memory of your physical
world**. Your **phone is the camera** (mobile-first; the dev laptop has no webcam, and being
portable is a feature). It watches your space, builds an episodic memory of objects/places,
and answers "where/when did I…?" out loud.

- **Repo:** `github.com/syzayd/recall` (public, default branch `master`). `gh` authed as `syzayd`.
- **Git identity:** Zaid Ali Syed / sidzaid72@gmail.com.
- **Free-tier rule (CRITICAL):** the Gemini project must keep **billing OFF** — enabling it
  deletes the free tier and every call becomes paid. Manage quota with smart sampling, never billing.
- **The demo moment we're building toward (DISCUSSION.md §4):**
  > "Recall, where did I leave my charger?" → *"On the kitchen counter, next to the kettle —
  > about 10 minutes ago."* (and it shows the remembered frame.)

---

## 1. Current state (Weeks 1 & 2 — done & verified on phone)

### Architecture (the key decision — don't change it)
FastAPI serves the built `frontend/dist` **and** the `/ws` WebSocket on **one port (8000)**,
fronted by a single **cloudflared quick tunnel**. The phone loads an `https` page and the WS
upgrades to `wss` automatically — no mixed-content, no second tunnel, portable from any phone.

**Decoupled paths keep us in the free tier:** cheap **Gemini Flash** vision for ingestion
(generous RPD); a **Gemini Live** session only while the user is actively talking.

### What already works
- **Week 1:** phone rear camera (`getUserMedia facingMode:'environment'`) → `/ws`; on-demand
  Gemini Flash vision ("What am I looking at?"); Gemini Live push-to-talk voice round-trip.
- **Week 2:** scene-change detection, ChromaDB memory store (local ONNX embeddings — free &
  offline), always-on ingestion loop gated by a record toggle, thumbnail gallery + timeline
  UI + per-entry delete.

### Project structure
```
recall/
├── backend/
│   ├── main.py          # FastAPI: /ws (frame/analyze/live/record), /memory GET+DELETE, /thumbnails static
│   ├── perception.py    # analyze_frame (Gemini Flash, pydantic schema) + has_scene_changed (MAD diff)
│   ├── live.py          # Gemini Live relay (push-to-talk, manual activity detection)  ← EDIT in Week 3
│   ├── memory.py        # ChromaDB wrapper: log_observation, recall_memory, list_all, delete_observation  ← EDIT
│   ├── tools.py         # STUB — recall_memory tool declaration goes here  ← EDIT (Week 3 core)
│   └── requirements.txt
├── frontend/
│   ├── public/pcm-worklet.js   # mic-capture AudioWorklet (real file, NOT a data: URL — iOS Safari)
│   ├── src/
│   │   ├── App.jsx      # camera + analyze + push-to-talk + record toggle + memory timeline  ← EDIT
│   │   ├── audio.js     # resample 16k, Int16<->Float32, AudioPlayer (gapless 24k)
│   │   ├── App.css      ← EDIT
│   │   └── main.jsx
│   ├── vite.config.js   # dev proxy /ws -> :8000
│   └── package.json
├── eval/benchmark.py    # STUB — Week 4
├── handoffs/            # WEEK-1-COMPLETED.md, WEEK-2-COMPLETED.md, WEEK-3-PLAN-HANDOFF.md (this)
├── CHANGELOG.md         # session-by-session log — UPDATE at end of Week 3
├── DISCUSSION.md        # full decisions log + original 6-week plan (§8)
├── data/                # gitignored: chroma/, thumbnails/<id>.jpg, last_frame.jpg
├── .env                 # gitignored: GEMINI_API_KEY (billing OFF)
└── README.md            # one-liner stub (fleshed out in Week 6)
```

### Verified Gemini facts (DO NOT re-derive — they cost real time)
- **Live model:** `gemini-3.1-flash-live-preview` (the `.env` placeholder `gemini-2.5-flash-live`
  does NOT exist). Vision model: `gemini-2.5-flash`.
- **Push-to-talk needs MANUAL activity detection:** `RealtimeInputConfig(automatic_activity_detection=AutomaticActivityDetection(disabled=True))`,
  send `activity_start` on press / `activity_end` on release. Automatic VAD won't fire without trailing silence.
- **Audio:** mic in = PCM16 **16 kHz** mono; Gemini out = PCM **24 kHz**.
- **AudioWorklet on iOS Safari:** load from a real same-origin file (`/pcm-worklet.js`), NOT a `data:` URL.
- **Python 3.14:** no `audioop` (removed). **chromadb 1.5.9 works** on 3.14; ships local ONNX
  embedding model `all-MiniLM-L6-v2` (cached in `~/.cache/chroma`) — embeddings free + offline.
- **Toolchain:** on this machine **node** and **cloudflared** are NOT on PATH by default (see Run section).

---

## 2. Week 3 goal & scope (decided with the user 2026-06-17)

The memory store is built but **nothing reads from it by voice yet** — that's the whole point
of the project and exactly what Week 3 delivers.

**Scope = core recall tool + 3 demo enhancers (one focused day):**
1. `recall_memory` wired into the Live session as a function-calling tool → spoken answer.
2. **Confidence gate** — honest "I don't remember seeing that" instead of inventing a memory
   (anti-hallucination = recruiter credibility).
3. **Temporal filter** — "in the last 10 minutes", "when did I last see…".
4. **Remembered-frame spotlight card** — a prominent card above the timeline showing the
   matched thumbnail, synced with the spoken answer (best for the demo video).

---

## 3. Build steps (in order)

### Step 1 — `backend/memory.py`: return distances + a confidence gate
The recall path needs to know *how good* a match is so the model can decline gracefully.

- In `recall_memory(query, k=3, since=None, until=None)`, change the query to
  `include=["documents", "metadatas", "distances"]` and carry each result's `distance`
  through into the returned dict (extend `_unpack` to accept and attach distances).
- Add a module constant `RECALL_MAX_DISTANCE = 1.0`  *(starting guess for the default L2
  ONNX embedding — **must be calibrated**, see Verification §6).* Lower distance = closer match.
- Add a helper used by the tool layer:
  ```python
  def recall_for_tool(query: str, since: float | None = None, until: float | None = None) -> dict:
      matches = recall_memory(query, k=3, since=since, until=until)
      confident = bool(matches) and matches[0]["distance"] <= RECALL_MAX_DISTANCE
      return {"matches": matches, "confident": confident}
  ```
- Keep the existing `_unpack` shape (`id, description, objects, location_label, timestamp`)
  and just add `distance`.

### Step 2 — `backend/tools.py`: declare the tool (currently an empty stub)
```python
"""Function-calling tools exposed to the Gemini Live session."""
from __future__ import annotations
import time
from google.genai import types
from . import memory

RECALL_TOOL = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="recall_memory",
        description=(
            "Search the user's visual memory of their physical space for where or when they "
            "last saw an object or were in a place. Call this for any 'where did I leave/put X', "
            "'when did I last see Y', or 'what was on the Z' question."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(type=types.Type.STRING,
                    description="What to look for, e.g. 'charger', 'my keys', 'the desk'"),
                "minutes_ago": types.Schema(type=types.Type.INTEGER,
                    description="Optional: only search memories from the last N minutes"),
            },
            required=["query"],
        ),
    )
])

def handle_tool_call(name: str, args: dict) -> dict:
    """Execute a tool call from the Live model. Returns a small, speakable result dict."""
    if name != "recall_memory":
        return {"error": f"unknown tool {name}"}
    query = args.get("query", "")
    minutes_ago = args.get("minutes_ago")
    since = time.time() - minutes_ago * 60 if minutes_ago else None
    result = memory.recall_for_tool(query, since=since)
    # Trim to what the model needs to speak (keep payload small).
    now = time.time()
    matches = [{
        "location_label": m["location_label"],
        "description": m["description"],
        "objects": m["objects"],
        "minutes_ago": round((now - m["timestamp"]) / 60),
        "id": m["id"],
    } for m in result["matches"]]
    return {"confident": result["confident"], "matches": matches}
```

### Step 3 — `backend/live.py`: wire the tool into the session
- Add `from . import tools` and put `tools=[tools.RECALL_TOOL]` in the `LiveConnectConfig(...)`.
- Replace `SYSTEM` so the model knows it HAS a photographic memory:
  > "You are Recall, a warm, concise voice assistant with a photographic memory of the user's
  > physical space. For any question about where they left something, when they last saw
  > something, or what was somewhere, you MUST call recall_memory. Speak naturally and briefly:
  > name the location and roughly when (e.g. 'about 10 minutes ago'). If the tool result has
  > confident=false or no matches, say you don't remember seeing it — never invent a memory."
- In the `async for r in session.receive()` loop, handle tool calls (the `r.data` / transcript
  handling stays as-is):
  ```python
  if getattr(r, "tool_call", None):
      responses = []
      for fc in r.tool_call.function_calls:
          result = await asyncio.to_thread(tools.handle_tool_call, fc.name, dict(fc.args or {}))
          responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
          if result.get("confident") and result.get("matches"):
              top = result["matches"][0]
              await websocket.send_json({
                  "type": "recalled",
                  "match": {**top, "thumbnail": f"/thumbnails/{top['id']}.jpg"},
              })
      await session.send_tool_response(function_responses=responses)
  ```
  Run the ChromaDB call via `asyncio.to_thread` (it's sync) so the receive loop isn't blocked.

### Step 4 — `frontend/src/App.jsx`: remembered-frame spotlight card
- Add `const [recalled, setRecalled] = useState(null);`
- In `ws.onmessage`, add: `else if (msg.type === "recalled") setRecalled(msg.match);`
- Clear it at the start of each new query — in `startTalk`, add `setRecalled(null);`
- Render a spotlight card **above** the `.timeline` block when `recalled` is set:
  ```jsx
  {recalled && (
    <div className="recalled">
      <div className="recalled-badge">🧠 Remembered
        <button className="recalled-x" onClick={() => setRecalled(null)}>×</button>
      </div>
      <div className="memory-entry">
        <img className="memory-thumb" src={recalled.thumbnail} alt={recalled.location_label} />
        <div className="memory-meta">
          <div className="memory-loc">📍 {recalled.location_label}</div>
          <p className="memory-desc">{recalled.description}</p>
          <div className="chips">{recalled.objects.map((o,i)=><span key={i} className="chip">{o}</span>)}</div>
          <div className="memory-time">~{recalled.minutes_ago} min ago</div>
        </div>
      </div>
    </div>
  )}
  ```
  Reuse the existing `.memory-entry`, `.memory-thumb`, `.chip` styles.

### Step 5 — `frontend/src/App.css`: spotlight styling
Add a `.recalled` wrapper (accent border, subtle entrance animation) + `.recalled-badge` /
`.recalled-x`, mirroring the existing `.observation` / `.memory-entry` look so it feels native.
Suggested accent: the existing `--accent: #6ea8fe`.

### Step 6 — Docs + git (at end of session)
- **`CHANGELOG.md`:** add `## Week 3 — Recall (<date>)` — tool wiring, confidence gate,
  temporal filter, spotlight UI, and the **calibrated `RECALL_MAX_DISTANCE`** value.
- **`handoffs/WEEK-3-COMPLETED.md`:** new completion handoff (mirror `WEEK-2-COMPLETED.md`):
  resume line, what was built, calibrated threshold, run commands, learnings, Week 4 start.
- **Tag + push:** `git tag -a week-3 -m "Week 3: recall tool + confidence gate + spotlight"`,
  then `git push origin master --tags`. (Auto-commit hooks commit per file; the tag is the
  restore point.)

---

## 4. Critical files
| File | Change |
|------|--------|
| `backend/memory.py` | distances + `RECALL_MAX_DISTANCE` + `recall_for_tool()` |
| `backend/tools.py` | `RECALL_TOOL` declaration + `handle_tool_call()` (was a stub) |
| `backend/live.py` | `tools=[...]`, new SYSTEM prompt, tool-call handling, `recalled` WS msg |
| `frontend/src/App.jsx` | `recalled` state + handler + spotlight card |
| `frontend/src/App.css` | `.recalled` spotlight styles |
| `CHANGELOG.md`, `handoffs/WEEK-3-COMPLETED.md` | session log + completion handoff |

**Reuse, don't rebuild:** `memory._unpack`, `memory._col`, `perception._client` (cached
genai client — already imported in `live.py` as `from .perception import _client`), `App.jsx`
`fmtTime` + `.chip`/`.memory-entry` CSS, the existing `/thumbnails` static mount and
`ingested`/timeline plumbing.

---

## 5. How to run (mobile/demo path) — PowerShell

```powershell
# Terminal 1 — build frontend (only when JSX/CSS changes)
cd C:\Users\Asus\projects\recall\frontend
npm run build

# Terminal 2 — backend (serves dist + /ws on one origin)
cd C:\Users\Asus\projects\recall
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Terminal 3 — public HTTPS tunnel
$env:PATH += ";C:\Program Files (x86)\cloudflared"
cloudflared tunnel --url http://localhost:8000
# -> prints https://<random>.trycloudflare.com (ephemeral; new URL each run) — open on the PHONE
```
(Git Bash equivalent for PATH: `export PATH="/c/Program Files/nodejs:/c/Program Files (x86)/cloudflared:$PATH"`.)

---

## 6. Verification (end-to-end)
1. Build frontend, start backend + tunnel (§5), open the tunnel URL on the phone.
2. Tap **⏺ Record memory**, capture a few distinct scenes (e.g. charger on a desk, pan to a
   kettle) so ChromaDB has memories.
3. **🎙 Start voice** → hold-to-talk → "Recall, where did I leave my charger?" → expect a
   spoken answer naming the location + relative time, and the **spotlight card** with that frame.
4. Ask about something never recorded → expect an honest "I don't remember seeing that."
5. **Calibrate `RECALL_MAX_DISTANCE`:** temporarily `log.info` each query's top distance;
   pick a threshold separating true hits from the never-recorded case. Record it in the handoff.
6. Temporal: "when did I last see the kettle?" and "what did I see in the last 5 minutes?" →
   confirm `minutes_ago` filtering works.

---

## 7. Merged roadmap (original 6-week plan, DISCUSSION.md §8)
- **Week 1** ✅ capture + vision + voice
- **Week 2** ✅ memory ingestion
- **Week 3** ⬅ *this plan* — recall tool + confidence gate + temporal + frame spotlight
- **Week 4 — Make it credible:** `eval/benchmark.py` (staged placements → scripted questions →
  recall@1/@3 + latency, printed into README); quota tuning. The calibrated `RECALL_MAX_DISTANCE`
  feeds the eval.
- **Week 5 — Polish + wow:** UI polish, accessibility/continuous-narration mode, staged demo
  scenarios, record the **60s killer demo video** (the primary artifact).
- **Week 6 — Ship the story:** flesh out `README.md` (currently one line) with demo GIF,
  architecture diagram, metrics, and the physical-world positioning; LinkedIn build-in-public
  series; optional free deploy.

### Next-level backlog (pull in as time allows — Week 4/5+)
- **Object-centric memory:** "last known location" per object (dedupe by object, keep newest).
- **Memory de-duplication:** merge near-identical consecutive scenes at ingestion.
- **Auto-expiry / retention controls:** optional TTL (privacy-by-design — DISCUSSION.md §5).
- **Richer temporal language:** "this morning", "yesterday" → date-range filters.
- **Live hosted demo:** backend on Render/HF Spaces (optional — the video is the artifact).

---

## 8. Checkpoint / restore
All Week 1 & 2 code is committed and pushed to `github.com/syzayd/recall` (public, `master`,
tag `week-2`). Restore the pre-Week-3 baseline with `git checkout week-2`. The `data/`
directory (ChromaDB + thumbnails) is local-only and intentionally not versioned.
