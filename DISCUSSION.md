# Recall — Project Discussion & Decisions Log

> Everything we discussed while shaping this flagship project, from the goal down to the reviewed plan. This is the "how we got here" companion to the implementation plan.

---

## 1. The goal

Zaid wants a **flagship, industry-grade portfolio project** that:
- Instantly improves the impression on recruiters/hirers.
- Is **unique, creative, innovative** — "wow, that's new."
- Is **fun to build**.
- Stays **as free as possible** to run.

Context: Zaid is a B.Tech IT student (MGM University, graduating June 2027), building AI authority on LinkedIn, targeting SDE / AI Engineer / AI-ML / Prompt Engineer roles. Already mastering Claude Code, agentic workflows. Has an existing project (Resume Job-Fit AI, Gemini free-tier).

---

## 2. What we learned about standing out in 2026 (grounding research)

- **Saturated / avoid:** resume builders, PDF-chat RAG, support chatbots, meeting summarizers, generic "AI wrapper" apps. Recruiters are tired of these.
- **What wins now:** solving a real problem with visible *system thinking*, end-to-end + a live demo, measurable results, and ideally **agentic** depth (the 2026 differentiator).
- GitHub projects with runnable code/live demos get **~80% more recruiter engagement** than the resume itself.
- "Wow that's new" = **novel angle + genuine engineering depth + a demo that makes people lean in**.

---

## 3. Decisions made (the funnel)

| Decision | Choice |
|---|---|
| **Project direction** | Real-time multimodal live agent |
| **Scope / ambition** | Flagship (3–6 weeks) — one deep, polished, deployed project |
| **Specific concept** | "AI with a photographic memory of your physical world" |
| **Why not the others** | JARVIS clones / interview coaches / fitness coaches felt too common; wanted something rarely attempted |

Other concepts considered and set aside: build-your-own JARVIS, live AI game opponent (vision), AI Dungeon Master, fitness/form coach, whiteboard thinking partner, real-time sign-language bridge, micro-expression "tell" reader.

---

## 4. The chosen concept — "Recall"

A real-time **camera + voice agent** that continuously observes your physical environment, builds a persistent **episodic spatial-temporal memory**, and answers "where / when / what did I…" questions instantly out loud.

> **Demo moment:** "Recall, where did I leave my charger?" → *"On the kitchen counter, next to the kettle — you set it down about 10 minutes ago."* (and it shows the remembered frame.)

### Why this impresses recruiters (the strategic bet)
- Tackles **agent long-term/spatial memory** — the hottest unsolved problem in AI in 2026 → signals frontier-level thinking, not API-wrapping.
- Demo is **universal + emotional** ("never lose your keys") and visually striking → great LinkedIn build-in-public video.
- It's a **full system** (real-time streaming, perception, memory store, retrieval, voice, tool-calling), not a single API call.
- Meaningful **impact story**: accessibility, elder care, ADHD/forgetfulness.
- Ships with **measurable metrics** (recall@k, latency) → reads "industry-grade," not student toy.

### Positioning (why it's not derivative)
Existing "AI memory" tools (Rewind, Limitless) capture **screen + audio**. Recall's novelty is **the physical world via camera** — spatial-temporal memory of real objects and places. State this explicitly in the README.

---

## 5. Tech foundation (verified June 2026)

- **Gemini Live API** (`gemini-2.5-flash-live` / `gemini-3.1-flash-live`) — natively streams **video + audio + text in one session** (~200ms latency), supports **async function calling/tools**, and has a **free tier**. Strongest multimodal/video breadth, "orders of magnitude cheaper" than OpenAI Realtime. On-brand with the existing Gemini setup.
- **Free-tier rule (critical):** keep billing **OFF** on the Gemini project — enabling billing deletes the free tier entirely.

### Decoupled architecture (key design decision from plan review)
Do **not** run a persistent always-on Live session to "watch" the room — session caps + rate limits make that infeasible on free tier. Instead:
- **Ingestion path (cheap):** periodic frame capture (on scene change / every N seconds) → **standard Gemini Flash vision** (generous free RPD) to extract structured observations.
- **Interaction path (Live):** open a **Gemini Live session only when the user is actively asking** (voice Q&A), then close it.

### Privacy by design (a maturity signal recruiters notice)
- **Local-only storage** (ChromaDB + thumbnails on disk).
- **Visible record on/off toggle** + clear recording indicator.
- **Memory management:** view/delete observations; optional auto-expiry.
- Document this in the README as a design principle.

---

## 6. Recommended stack (all free)

- **Backend:** Python 3.x + **FastAPI** (WebSocket relay) + `google-genai` SDK (Live API). Reuse `.env` / `GEMINI_API_KEY` pattern + gitignore conventions from the Resume Job-Fit AI project.
- **Memory store:** **ChromaDB** (local, free, persistent) — observation embeddings + metadata (object, location label, timestamp, thumbnail path).
- **Embeddings:** Gemini embeddings (free tier) or local `sentence-transformers` fallback.
- **Frontend:** lightweight **mobile-first Vite + React** (or vanilla JS) using `getUserMedia` (**rear camera**, `facingMode: 'environment'`) for camera/mic, WebSocket to backend. For the demo/mobile path, the **built frontend is served by FastAPI on a single port** so one origin (and one tunnel) covers both the page and the WebSocket. Scaffold from official **`google-gemini/gemini-live-api-examples`**.
- **Tunnel:** **`cloudflared`** quick tunnel for mobile testing (free, no signup, valid HTTPS cert — required because `getUserMedia` needs a secure context). See §13.
- **Repo:** `github.com/syzayd/recall`, build-in-public, README with demo GIF + metrics + architecture diagram.
- **Deploy (optional):** frontend on Vercel/GitHub Pages; backend on Render free tier or Hugging Face Spaces. The **recorded demo video is the primary artifact**, so live deploy is optional.

---

## 7. Architecture

1. **Capture layer (frontend, on the phone):** the **phone's rear camera** + mic capture audio and sampled video frames over WebSocket; renders live camera view, memory timeline/gallery, record toggle, voice/chat panel. The page and the WebSocket share **one origin** (FastAPI serves the built frontend on the same port as `/ws`) so a single `cloudflared` tunnel covers both with valid HTTPS/`wss` — see §13.
2. **Ingestion path (cheap, always-on while recording):** scene-change frame → **Gemini Flash vision** → structured observation `{objects, location_label, description, timestamp, thumbnail}` → embed → store in ChromaDB.
3. **Interaction path (Live, on demand):** user speaks a query → open **Gemini Live session** → close when idle.
4. **Retrieval tool (the moat):** Live session uses **function calling** — `recall_memory(query)` (semantic + temporal search) and `log_observation(...)`. Model composes a natural spoken reply, optionally surfacing the remembered frame.
5. **Eval harness:** stage known object placements, ask scripted retrieval questions, measure **recall@1/@3** and **end-to-end latency**; print metrics into README.

---

## 8. Build phases (3–6 weeks)

- **Week 1 — Two hello-worlds (mobile path first):** (a) **phone** camera/mic capture → FastAPI WebSocket **over the cloudflared tunnel** — prove the mobile capture path first, since it's now the foundational/riskiest piece; (b) frame → Gemini Flash vision → structured observation round-trip, and a Gemini Live voice round-trip. Prove both paths cheaply.
- **Week 2 — Memory ingestion:** scene-change frame sampling → observation pipeline → ChromaDB store + thumbnails + timeline UI + record toggle.
- **Week 3 — The magic:** `recall_memory` retrieval tool wired into the Live session via function calling; "where/when" voice Q&A working out loud with remembered frame.
- **Week 4 — Make it credible:** eval harness + recall@k/latency metrics; quota tuning + privacy/delete controls.
- **Week 5 — Polish + wow:** UI polish, accessibility mode (continuous narration), staged demo scenarios, record the 60s killer demo video.
- **Week 6 — Ship the story:** README + architecture diagram, build-in-public LinkedIn series, optional free deploy.

---

## 9. Critical files to create (greenfield)

- `backend/main.py` — FastAPI app + WebSocket endpoint + Gemini Live session manager.
- `backend/memory.py` — ChromaDB wrapper: `log_observation`, `recall_memory`, embedding + thumbnail handling.
- `backend/tools.py` — function-calling tool definitions wired into the Live session.
- `backend/perception.py` — frame sampling + scene-change detection + structured observation extraction (Flash vision).
- `frontend/` — Vite app: camera/mic capture, WebSocket client, live view + memory timeline + voice panel.
- `eval/benchmark.py` — staged retrieval benchmark → recall@k + latency report.
- `.env` (gitignored), `.gitignore`, `README.md` (demo GIF, metrics, architecture diagram, "why it matters").

---

## 10. Verification

- **Functional (mobile):** `uvicorn backend.main:app --port 8000`, then `cloudflared tunnel --url http://localhost:8000`; open the printed `https://*.trycloudflare.com` URL on the **phone** and grant camera + mic. Confirm rear-camera frames arrive at the backend over `wss`. Then place objects, ask "where did I put X?" / "when did I last see Y?" — confirm correct spoken answers + correct remembered frame.
- **Quantitative:** run `eval/benchmark.py` → confirm recall@1/@3 and median latency; record in README.
- **Demo:** record the 60s "lost item → instant recall" video.
- **Quota safety:** confirm billing stays disabled and a full demo session stays within free-tier limits.

---

## 11. Open follow-ups (decide during build, not blocking)

- Final product name (working name: **Recall**; alternatives: Mnemo, Déjà, Total Recall).
- Whether to ship a live hosted demo or rely on the video + local run.

---

## 12. Status / next steps

- ✅ Git repo created at `C:\Users\Asus\projects\recall` (initial commit done).
- ✅ Plan refined remotely via **Ultraplan** (cloud agent) — mobile-first capture folded in; canonical plan committed as `PLAN.md`.
- ⬜ Scaffold `backend/` `frontend/` `eval/` + `.gitignore` once ready.
- ⬜ Begin Week 1 build.

---

## 13. Mobile-first capture & testing (cloud refinement, 2026-06-16)

New constraint: **the dev laptop has no built-in webcam, so the phone is the capture
device**, and the project should be **portable** (demo from a phone anywhere). This
reframes a constraint into a feature — the camera you always carry → on-the-go,
wearable-adjacent memory, a stronger demo story than a tethered laptop.

### The secure-context problem
Browser camera/mic access (`getUserMedia`) requires a **secure context (HTTPS)**.
`localhost` is exempt, but a phone hitting the laptop over a LAN IP (`http://192.168.x.x`)
is **not** secure — the camera silently fails. So mobile testing **requires a public HTTPS
URL**. (This gap was unaddressed in the original laptop-webcam plan.)

### Decision: cloudflared quick tunnel
`cloudflared tunnel --url http://localhost:8000` → prints a `https://*.trycloudflare.com`
URL with a valid cert; works on iOS Safari + Android Chrome with **no account**.

| Option | Verdict |
|---|---|
| **cloudflared quick tunnel** | ✅ Chosen — free, no signup, valid cert, reliable on iOS + Android. |
| ngrok | ❌ Needs an authtoken/account. |
| Vite self-signed HTTPS on LAN | ❌ iOS Safari frequently blocks the camera on self-signed certs. |

### Single origin = one tunnel
Serve the **built frontend from FastAPI on :8000** and expose `/ws` on the same port, so the
phone loads the page and opens the WebSocket on one origin. This avoids a second tunnel and
mixed-content (`https` page → `ws://`) errors; `wss` is automatic because the page is
`https`. Portability win: `uvicorn` + one `cloudflared` command = demo on any phone.
*Dev convenience:* run Vite with `server.proxy` forwarding `/ws` to :8000 and tunnel the
Vite port for HMR; the demo/mobile path is the FastAPI-static single-origin one.

### Frontend capture specifics
- `getUserMedia({ video: { facingMode: 'environment' }, audio: true })` → rear camera.
- `<video playsinline autoplay muted>`; start capture on a **user gesture** (iOS Safari quirk).
- Derive the WS URL from `window.location` so it becomes `wss://…` through the tunnel.
- Mobile-first responsive layout.
