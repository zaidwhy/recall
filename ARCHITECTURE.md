# Architecture

System-design case study for Recall.

## Problem

Give someone a spoken answer to "where did I leave my keys?" from a phone camera alone -
no manual tagging, no wearable, no always-on cloud video stream - while staying inside a
vision model's free daily quota and a $0 hosting budget.

## Requirements

- Continuously watch a room through a phone camera, notice when the scene actually
  changes, and remember what was seen and where, with a timestamp.
- Answer a spoken question with a spoken answer, naming the object's location and how
  long ago it was seen - and say honestly when nothing matches, never guess.
- Work from a phone browser over HTTPS with no app install, camera and microphone both
  live, low enough friction that a demo visitor can use it in under a minute.
- Be measurable: an eval benchmark against a fixed set of scenes, not just a live demo.
- Stay entirely inside Gemini's free tier - 20 vision calls/day - with a hard budget
  ceiling that is impossible to exceed by accident.

## Constraints

- `gemini-2.5-flash` free tier: 20 requests/day. The ingest loop stops at 18 to keep 2 in
  reserve, and a 120-second floor between calls caps the maximum possible burn rate to 1
  call every 2 minutes regardless of how often the scene changes.
- The tunnel exposing the phone-facing URL (cloudflared) is public by construction - a
  guessed or leaked URL must not be enough to read or wipe someone's camera memories.
- Render's free tier has no persistent disk: `data/` (ChromaDB memories and thumbnails)
  resets on redeploy and likely on the spin-down-then-wake that follows ~15 minutes idle.
  Accepted deliberately (Zaid's call, 2026-07-29) rather than paying for a disk add-on for
  a demo.
- Camera and microphone access require HTTPS, which `localhost` alone cannot give a
  phone on the same network - hence the tunnel, and a single-origin design (one server
  serves both the built frontend and the WebSocket) so the phone never has a
  mixed-content or second-tunnel problem.

## Architecture

```
Phone browser (camera + mic)  <-- wss (single origin, same server serves frontend/dist)
        |
FastAPI app (backend/main.py, 461 lines)
   |-- TokenAuthMiddleware: RECALL_TOKEN required on every HTTP route AND /ws
   |-- Ingest loop (_ingest_loop): poll every 5s, only call Gemini when the scene
   |     actually changed AND the rate floor has elapsed
   |     |-- perception.py: scene-change gate (grayscale frame diff) -> Gemini
   |     |     Flash structured vision call -> Observation(objects, location, desc)
   |     `-- memory.py (MemoryStore): embeds and stores the observation in ChromaDB,
   |           deduping same-location re-ingests inside a 60s window
   `-- Live voice path (live.py): phone mic audio (PCM16) relayed to a Gemini Live
         session; recall_memory is wired in as a function-calling tool (tools.py) -
         the model must call it before answering a "where" question, never guess
```

## Data flow: "where are my keys?"

1. The phone opens a Gemini Live voice session over the same WebSocket the ingest loop
   uses; mic audio streams in as binary PCM16 frames.
2. The model is instructed (system prompt in `live.py`) that for any question about where
   something is or was last seen, it must call the `recall_memory` tool first - never
   answer from its own guess.
3. `tools.handle_tool_call("recall_memory", ...)` calls `memory.recall_for_tool()`, which
   embeds the query locally (bundled ONNX `all-MiniLM-L6-v2`, no Gemini embedding call)
   and queries ChromaDB.
4. Each candidate's score is its L2 distance plus a recency penalty
   (`DECAY_WEIGHT * log(1 + hours_ago)`), so a fresher memory beats an older one at equal
   semantic distance rather than the two competing on similarity alone.
5. A result is only "confident" below `RECALL_MAX_DISTANCE = 1.4` (chosen to accept any
   real semantic overlap on unit-vector L2 distance); above that, the tool reports no
   confident match and the model is instructed to say so honestly rather than guess.
6. The model speaks the answer - location and recency - back over the same socket as
   PCM24 audio, with a text transcript sent alongside for an on-screen caption.

## Components

| Component | File | Responsibility |
|---|---|---|
| FastAPI app | `backend/main.py` (461 lines) | routes, `TokenAuthMiddleware`, the ingest loop, the Flash rate/budget guard |
| perception.py | 91 lines | scene-change gate, one structured Gemini Flash vision call per accepted frame |
| memory.py (MemoryStore) | 329 lines | ChromaDB wrapper, local ONNX embeddings, recency-weighted recall, dedup window |
| live.py | 125 lines | the Gemini Live voice session, system prompt that forces tool-call-before-answer |
| tools.py | 99 lines | `recall_memory` function-calling tool the Live model actually calls |
| frontend/ | Vite/React, built to `dist/` | camera capture, mic streaming, served as a static build by the same FastAPI process |

## Failure modes

| Failure | Effect | Mitigation |
|---|---|---|
| A guessed or leaked tunnel URL | anyone could read or wipe camera memories over the public tunnel | `TokenAuthMiddleware` requires `RECALL_TOKEN` (header, query param, or cookie) on every route and the WebSocket, no exceptions |
| Scene never changes but the loop keeps polling | wasted vision-quota calls | `has_scene_changed()` gates every call on an actual frame diff; polling every 5s costs nothing since Gemini is only called on a real change |
| Vision quota exhausted mid-demo | ingestion silently stops working | a hard `FLASH_DAILY_BUDGET = 18` (below the real 20/day limit) plus a 120s floor between calls, both checked before every call, with a human-readable reason returned when blocked |
| A "where is X" question with nothing matching in memory | a made-up answer would be worse than no answer | the 1.4 L2-distance confidence cutoff plus an explicit system-prompt rule to say so honestly when `confident=false` |
| Render free-tier spin-down/redeploy | `data/` (all memories, thumbnails) is wiped | accepted for a demo; documented as a deliberate, non-durable tradeoff, not a bug |
| Render's own HTTP health check | every route including `/health` requires the token, so an unauthenticated health check would always 401 | no `healthCheckPath` is set in `render.yaml`; Render falls back to a plain TCP listening check instead |

## Tradeoffs

- **Local ONNX embeddings over a Gemini embedding call**: keeps recall free and fast
  (no network round-trip, no quota impact) at the cost of embedding quality being
  whatever a small bundled model gives - acceptable at this project's scale and object
  vocabulary.
- **Recency-weighted score over pure semantic distance**: a slightly fuzzier ranking
  formula (one more tunable weight) in exchange for "where did I last see my keys"
  correctly preferring the recent sighting over an older, equally-similar one.
- **Hard daily budget below the real quota, not equal to it**: gives up 2 calls/day of
  headroom in exchange for a demo that can never hard-fail mid-session from quota
  exhaustion.
- **No persistent disk on Render**: $0 hosting cost, at the cost of memories not
  surviving a redeploy or a cold spin-down - a real limitation, but the right tradeoff
  for a public demo rather than a personal daily-use deployment.
- **Single-origin serving (FastAPI serves the built frontend) over a separate frontend
  host**: the entire reason phone camera/mic access and the WebSocket both work cleanly
  behind one tunnel, at the cost of a build step (`npm run build`) being required before
  any frontend change is visible.

## Scaling (what would change first)

1. A persistent disk (Render Starter + disk add-on) the moment this needs to survive
   redeploys for real daily use rather than demo purposes - a config change, not a
   redesign, since `MemoryStore` already isolates its data directory per instance.
2. Multiple concurrent ingest sessions (one MemoryStore instance per room/user) would
   need the currently-global `_last_flash_call`/`_flash_calls_today` rate-guard state in
   `main.py` to move from module-level globals into something keyed per session.
3. A vision model with a larger free-tier quota, or a paid tier with real budget
   tracking, once daily usage patterns outgrow 18 calls - `_charge_flash()` is already
   the single choke point that would need the new ceiling.

## Security

- Every HTTP route and the `/ws` socket require `RECALL_TOKEN`, checked in header, query
  param, or cookie form - the token is what turns a public tunnel URL into something
  safe to share for a demo.
- The token cookie is `httponly` and `samesite=lax`, set automatically after the first
  authenticated request so later page/asset loads and the WS handshake carry it without
  the query param needing to persist in the URL.
- `GEMINI_API_KEY` and `RECALL_TOKEN` are both `sync: false` in `render.yaml` - set only
  in Render's dashboard, never committed.
- `.env` is never read directly by an agent working on this repo; values are always asked
  of the human.

## Observability

Structured `logging` to stdout (Render's log stream): the vision model and rate-guard
floor are logged once at startup, and every blocked Flash call logs a human-readable
reason (budget exhausted vs. rate-floor wait). No per-request cost/latency aggregation
beyond what `perception.analyze_frame()` already returns (`latency_ms` per call) - the
eval benchmark (`python -m eval.benchmark`, isolated temp ChromaDB, never touches real
data) is the closest thing to a trend line today: 10/10 recall@1 on a fixed 10-item eval
set, 149ms median retrieval latency.

## Cost

$0. Vision calls stay inside Gemini's free tier by construction (18/day hard cap, 120s
floor). Embeddings are local and free (bundled ONNX model, no API call). Render's free
web-service tier hosts the backend; Vercel-equivalent static hosting is unnecessary since
the same FastAPI process serves the built frontend. The only recurring cost is the
demo's traded-away durability (no persistent disk), not money.

## Future

- Persistent disk if Recall moves from public demo to actual daily personal use (see
  Scaling).
- Per-request cost/latency logging aggregated into a dashboard, matching the direction
  CivilizationOS's `LLMRouter` and personal-llm's eval suite are already headed.
- A second, larger eval set once the 10-item benchmark stops being able to distinguish a
  real regression from noise.
