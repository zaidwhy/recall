---
title: Recall — Week 3 Completed (Handoff)
date: 2026-06-17
project: recall
status: Week 3 code complete; verify on phone + calibrate RECALL_MAX_DISTANCE; Week 4 unblocked
---

# Recall — Week 3 Completed ✅

> **Resume in one line:** "Load handoffs/WEEK-3-COMPLETED.md and start Week 4 — build eval/benchmark.py: staged object placements → scripted questions → recall@1/@3 + latency, printed into README."

> **Repo:** `github.com/syzayd/recall` (public, default branch `master`). Week 3 changes committed. Tag `week-3` after phone verification.

---

## What we built (Week 3) — pending phone verification

| # | Feature | What it does | Status |
|---|---------|--------------|--------|
| 9  | **`recall_memory` as Live tool** | `RECALL_TOOL` declared in `tools.py`, wired into `LiveConnectConfig(tools=[...])` in `live.py` | ✅ code |
| 10 | **Tool dispatch** | `handle_tool_call` in `tools.py`; `asyncio.to_thread` in receive loop so sync ChromaDB doesn't block | ✅ code |
| 11 | **Confidence gate** | `recall_for_tool` returns `confident` flag; model told to say "I don't remember" if `confident=false` | ✅ code |
| 12 | **Temporal filter** | `minutes_ago` param → `since = time.time() - N*60` → `recall_memory(since=...)` | ✅ code |
| 13 | **Remembered-frame spotlight** | `recalled` WS message → spotlight card above timeline (accent border, slide-in, dismiss ×) | ✅ code |

---

## CRITICAL: calibrate RECALL_MAX_DISTANCE

The confidence gate threshold in `backend/memory.py` is set to `1.0` (L2, `all-MiniLM-L6-v2`). This is a starting guess. Before tagging `week-3`:

1. Temporarily add `log.info("distance: %s", result['matches'][0]['distance'] if result['matches'] else 'no match')` in `handle_tool_call`
2. Record a few scenes (charger on desk, kettle, etc.)
3. Ask about something you recorded → note distance (should be small, < 0.5 ideally)
4. Ask about something never recorded → note distance (should be large)
5. Pick `RECALL_MAX_DISTANCE` to sit cleanly between the two
6. Update `RECALL_MAX_DISTANCE` in `memory.py`, remove the debug log, update value in `CHANGELOG.md`

---

## Project structure (as of Week 3)

```
recall/
├── backend/
│   ├── main.py          # unchanged this week
│   ├── perception.py    # unchanged this week
│   ├── live.py          # +tools=[RECALL_TOOL], new SYSTEM, tool_call handling, recalled WS msg
│   ├── memory.py        # +distances in recall_memory, RECALL_MAX_DISTANCE, recall_for_tool()
│   ├── tools.py         # RECALL_TOOL declaration + handle_tool_call() (was a stub)
│   └── requirements.txt
├── frontend/
│   ├── public/pcm-worklet.js
│   ├── src/
│   │   ├── App.jsx      # +recalled state, recalled msg handler, spotlight card JSX
│   │   ├── audio.js
│   │   ├── App.css      # +.recalled, .recalled-badge, .recalled-x styles
│   │   └── main.jsx
│   ├── vite.config.js
│   └── package.json
├── eval/benchmark.py    # STUB — Week 4
├── handoffs/
│   ├── WEEK-1-COMPLETED.md
│   ├── WEEK-2-COMPLETED.md
│   └── WEEK-3-COMPLETED.md  ← this file
├── CHANGELOG.md
├── data/                # gitignored: chroma/, thumbnails/, last_frame.jpg
├── .env                 # gitignored: GEMINI_API_KEY (billing OFF)
└── DISCUSSION.md
```

---

## How to run

> Node and cloudflared are NOT on the PowerShell PATH by default.

```powershell
# Terminal 1 — build frontend (JSX + CSS changed this week)
cd C:\Users\Asus\projects\recall\frontend
npm run build

# Terminal 2 — start backend
cd C:\Users\Asus\projects\recall
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Terminal 3 — tunnel
$env:PATH += ";C:\Program Files (x86)\cloudflared"
cloudflared tunnel --url http://localhost:8000

# Open the printed https://*.trycloudflare.com URL on the phone
```

---

## Verification checklist

- [ ] Build frontend, start backend + tunnel, open URL on phone
- [ ] Tap "⏺ Record memory", capture 2–3 distinct scenes
- [ ] "🎙 Start voice" → hold-to-talk → "Recall, where did I leave my charger?"
  - Expect: spoken answer with location + relative time
  - Expect: spotlight card appears above timeline with matched thumbnail
- [ ] Ask about something never recorded → "I don't remember seeing that"
- [ ] "When did I last see the kettle?" / "What did I see in the last 5 minutes?" → temporal filter
- [ ] **Calibrate `RECALL_MAX_DISTANCE`** (see section above) and update in `memory.py`
- [ ] `git tag -a week-3 -m "Week 3: recall tool + confidence gate + spotlight"` + push

---

## Architecture decisions (don't re-derive)

- `asyncio.to_thread` for ChromaDB — it's a sync blocking call; running it in the receive loop without `to_thread` would stall audio delivery
- Spotlight card cleared on `startTalk` — each new query gets a fresh spotlight (don't show stale result from a previous question)
- `minutes_ago` in the tool payload is rounded to nearest minute — more natural to speak ("about 10 minutes ago") than an exact float
- `distance` is not surfaced in the UI — it's internal confidence plumbing only

---

## Hard-won learnings (Week 3)

- `RECALL_MAX_DISTANCE` must be calibrated empirically — the L2 distance from `all-MiniLM-L6-v2` is not normalized to [0,1]; true semantic hits can be anywhere below ~0.6, noise hits cluster above ~1.2, but the exact boundary depends on vocabulary
- The `tool_call` attribute on Live session responses is separate from `server_content` — both can appear; handle them independently in the receive loop
- `FunctionResponse` needs `id=fc.id` to match the function call; some SDK versions are strict about this

---

## What's next

### Week 4 — Make it credible
- **`eval/benchmark.py`**: staged placements → scripted questions → recall@1/@3 + latency, printed into README
- Quota tuning: confirm ingestion loop + voice sessions fit inside daily free limits over a full day of use
- Feed `RECALL_MAX_DISTANCE` (now calibrated) into the eval as the confidence threshold

### Week 5 — Polish + wow
- UI polish, accessibility/continuous-narration mode
- Staged demo scenarios (charger, keys, where I put my coffee)
- Record the **60s killer demo video**

### Week 6 — Ship the story
- Flesh out README (architecture diagram, metrics, demo GIF)
- LinkedIn build-in-public series
- Optional free deploy
