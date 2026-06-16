# Recall — Implementation Plan (cloud-refined, 2026-06-16)

> Canonical, build-ready plan for **Recall**, an AI with a photographic memory of your
> physical world. Distilled from `DISCUSSION.md`, refined for **mobile-first capture**
> (the phone is the camera) and a **single-origin cloudflared tunnel** for testing.

---

## 1. Context & positioning

Recall is a real-time **camera + voice agent** that continuously observes your physical
environment, builds a persistent **episodic spatial-temporal memory**, and answers
"where / when / what did I…" questions instantly out loud.

> **Demo moment:** "Recall, where did I leave my charger?" → *"On the kitchen counter, next
> to the kettle — you set it down about 10 minutes ago."* (and it shows the remembered frame.)

**Positioning:** existing "AI memory" tools (Rewind, Limitless) capture **screen + audio**.
Recall's novelty is the **physical world via camera** — spatial-temporal memory of real
objects and places. Because the capture device is **the phone you always carry**, Recall is
genuinely **portable / on-the-go** memory — closer to a wearable than a tethered desktop
tool. State this differentiation explicitly in the README.

The technical moat is the **episodic memory system** (ChromaDB + embeddings + temporal/
semantic retrieval via function calling), not "Gemini Live + camera."

---

## 2. Tech foundation (verified June 2026)

- **Gemini Live API** (`gemini-2.5-flash-live` / `gemini-3.1-flash-live`) — natively streams
  video + audio + text in one session (~200ms latency), supports async function calling, has
  a free tier. Used **only for on-demand voice Q&A**.
- **Gemini Flash vision** (standard, generous free RPD) — used for **cheap periodic frame
  ingestion**, not Live.
- **Free-tier rule (critical):** keep **billing OFF** on the Gemini project — enabling
  billing deletes the free tier entirely (lesson from the Resume Job-Fit AI project).
- **Stack:** Python 3.x + FastAPI (WebSocket relay) + `google-genai` SDK; ChromaDB (local,
  persistent) for the memory store; Gemini embeddings (free) or local `sentence-transformers`
  fallback; mobile-first Vite + React frontend using `getUserMedia`; `cloudflared` for the
  tunnel.

---

## 3. Mobile-first capture & single-origin tunnel (the key refinement)

The dev laptop has **no built-in webcam**, so the **phone is the capture device**. Browser
camera/mic access (`getUserMedia`) requires a **secure context (HTTPS)** — `localhost` is
exempt, but a phone hitting the laptop over a LAN IP (`http://192.168.x.x`) is **not** secure
and the camera silently fails. Therefore mobile testing **requires a public HTTPS URL**.

```
        Phone (rear camera + mic)
   getUserMedia{ facingMode:'environment', audio:true }
                 │  HTTPS page + WSS  (one origin, valid cert)
                 ▼
   https://<random>.trycloudflare.com   ← cloudflared quick tunnel (free, no signup)
                 │
                 ▼
         uvicorn  backend/main.py  :8000
         ├── serves built frontend  (dist/ static files)   ← same origin ⇒ no mixed-content
         └── /ws  WebSocket endpoint (wss upgrades automatically through the tunnel)
                 │
                 ├── ingestion (cheap): sampled frame → Gemini Flash vision → observation → ChromaDB
                 └── interaction (on-demand): Gemini Live session for voice Q&A → recall_memory tool
```

1. **Secure-context rule.** `getUserMedia` needs HTTPS except on `localhost`. Phone-over-LAN
   is insecure → camera fails. Mobile testing **requires** a public HTTPS URL.
2. **cloudflared quick tunnel** is the chosen path:
   `cloudflared tunnel --url http://localhost:8000` → prints a `https://*.trycloudflare.com`
   URL with a valid cert; works on iOS Safari + Android Chrome with **no account**.
   - *Rejected alternatives:* **ngrok** (needs an authtoken/account); **Vite self-signed
     HTTPS on LAN** (iOS Safari frequently blocks the camera on self-signed certs).
3. **Single origin = one tunnel.** Serve the built frontend **from FastAPI on :8000** and
   expose `/ws` on the same port, so the phone loads the page and opens the WebSocket on one
   origin. This avoids a second tunnel and mixed-content (`https` page → `ws://`) errors;
   `wss` is automatic because the page is `https`. This is also the **portability** win:
   `uvicorn` + one `cloudflared` command = demo from any phone, anywhere.
   - *Dev convenience:* during active development, run Vite with `server.proxy` forwarding
     `/ws` to :8000 and tunnel the Vite port for HMR. The **demo/mobile path is the
     FastAPI-static single-origin one** above.
4. **Frontend capture specifics:**
   - `getUserMedia({ video: { facingMode: 'environment' }, audio: true })` → rear camera.
   - `<video playsinline autoplay muted>`; start capture on a **user gesture** (iOS Safari
     autoplay/permission quirk).
   - Derive the WS URL from `window.location` so it becomes `wss://…` through the tunnel.
   - Mobile-first responsive layout (live view, memory timeline/gallery, record toggle,
     voice/chat panel).

---

## 4. Decoupled architecture (free-tier protection)

Do **not** run a persistent always-on Live session to "watch" the room — session caps +
rate limits make that infeasible on free tier.

- **Ingestion path (cheap, always-on while recording):** scene-change frame → **Gemini Flash
  vision** → structured observation `{objects, location_label, description, timestamp,
  thumbnail}` → embed → store in ChromaDB.
- **Interaction path (Live, on demand):** open a **Gemini Live session only when the user is
  actively asking** (voice Q&A), then close it.
- **Retrieval tool (the moat):** the Live session uses **function calling** —
  `recall_memory(query)` (semantic + temporal search) and `log_observation(...)`. The model
  composes a natural spoken reply, optionally surfacing the remembered frame.

**Privacy by design:** local-only storage (ChromaDB + thumbnails on disk); visible record
on/off toggle + recording indicator; view/delete observations + optional auto-expiry.

---

## 5. Build phases (3–6 weeks)

- **Week 1 — Two hello-worlds (mobile path first):**
  1. **Phone camera/mic → FastAPI WebSocket over the cloudflared tunnel** (prove the mobile
     capture path first — it is now the foundational/riskiest piece).
  2. Frame → Gemini Flash vision → structured observation round-trip, and a Gemini Live
     voice round-trip. Prove both AI paths cheaply.
- **Week 2 — Memory ingestion:** scene-change frame sampling → observation pipeline →
  ChromaDB store + thumbnails + timeline UI + record toggle.
- **Week 3 — The magic:** `recall_memory` retrieval tool wired into the Live session via
  function calling; "where/when" voice Q&A working out loud with the remembered frame.
- **Week 4 — Make it credible:** eval harness + recall@k/latency metrics; quota tuning +
  privacy/delete controls.
- **Week 5 — Polish + wow:** UI polish, accessibility mode (continuous narration), staged
  demo scenarios, record the 60s killer demo video.
- **Week 6 — Ship the story:** README + architecture diagram, build-in-public LinkedIn
  series, optional free deploy.

---

## 6. Critical files to create (greenfield)

- `backend/main.py` — FastAPI app + `/ws` WebSocket endpoint + Gemini Live session manager +
  **static serving of the built `frontend/dist/`** (single origin).
- `backend/memory.py` — ChromaDB wrapper: `log_observation`, `recall_memory`, embedding +
  thumbnail handling.
- `backend/tools.py` — function-calling tool definitions wired into the Live session.
- `backend/perception.py` — frame sampling + scene-change detection + structured observation
  extraction (Flash vision).
- `frontend/` — mobile-first Vite app: rear-camera/mic capture, WebSocket client, live view +
  memory timeline + voice panel. Vite `server.proxy` for `/ws` in dev.
- `eval/benchmark.py` — staged retrieval benchmark → recall@k + latency report.
- `.env` (gitignored), `.env.example`, `.gitignore`, `README.md`.

---

## 7. Verification

**Mobile end-to-end (the path that matters):**
1. `uvicorn backend.main:app --port 8000`
2. `cloudflared tunnel --url http://localhost:8000`
3. Open the printed `https://*.trycloudflare.com` URL on the **phone**; grant camera + mic.
4. Confirm rear-camera frames arrive at the backend over `wss`.
5. Place objects, ask "where did I put X?" / "when did I last see Y?" — confirm correct
   spoken answers + correct remembered frame.

**Quantitative:** run `eval/benchmark.py` → confirm recall@1/@3 and median latency; record
in README.

**Demo:** record the 60s "lost item → instant recall" video (shot on the phone).

**Quota safety:** confirm **billing stays disabled** and a full demo session stays within
free-tier limits.

---

## 8. Open follow-ups (decide during build, not blocking)

- Final product name (working name **Recall**; alternatives: Mnemo, Déjà, Total Recall).
- Whether to ship a live hosted demo or rely on the video + local run.
- Embeddings: Gemini free tier vs local `sentence-transformers` fallback.
