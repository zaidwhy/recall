# Recall — an AI with a photographic memory of your world

Point your phone camera at your space. Ask out loud "where did I leave my keys?" and get a spoken answer with the exact frame it saw them in.

Built on Gemini Live (push-to-talk voice), Gemini Flash (always-on vision), and a local ChromaDB vector store for offline semantic recall.

---

## How it works

```
Phone camera → FastAPI WS server → Gemini Flash (scene analysis every 5 s)
                                 → ChromaDB (384-dim ONNX embeddings, local)

Push-to-talk → Gemini Live session → recall_memory() tool call
                                   → ChromaDB semantic search
                                   → spoken answer + spotlight card on phone
```

- **Ingestion**: frames are diff-compared against the last accepted scene; only changed scenes hit the vision API
- **Recall**: Gemini Live calls `recall_memory(query)` as a function; ChromaDB returns top-3 by L2 distance; a confidence gate (`distance ≤ 1.4`) decides whether to surface the match
- **Embedding model**: `all-MiniLM-L6-v2` via ChromaDB default — local ONNX, no cloud calls, no cost

---

## Quick start

**Prerequisites**: Python 3.11+, Node 18+, a Gemini API key (free tier), cloudflared.

```bash
# 1. Backend (run in your own terminal — compiled extensions require user context)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
$env:GEMINI_API_KEY = "..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 2. Tunnel (so phone can reach the server over HTTPS)
cloudflared tunnel --url http://localhost:8000

# 3. Frontend
cd frontend && npm install && npm run build
# Open the tunnel URL on your phone
```

---

## Eval Results

*Last run: 2026-06-17 &mdash; 20 observations (10 targets + 10 distractors)*

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

</details>

## Stack

| Layer | Technology |
|-------|-----------|
| Voice | Gemini Live (`gemini-3.1-flash-live-preview`) |
| Vision | Gemini Flash (structured JSON output) |
| Embeddings | `all-MiniLM-L6-v2` via ChromaDB (local ONNX) |
| Vector store | ChromaDB (persistent, local) |
| Backend | FastAPI + WebSocket |
| Frontend | React + Vite 4 |
| Tunnel | cloudflared |

---

## Project status

| Week | Focus | Status |
|------|-------|--------|
| 1 | Camera → vision → push-to-talk voice | ✅ Done |
| 2 | Always-on ingestion → ChromaDB → timeline UI | ✅ Done |
| 3 | `recall_memory` tool → spoken recall + spotlight | ✅ Done |
| 4 | `eval/benchmark.py` → recall@1/@3 + latency | 🔄 In progress |
| 5–6 | Polish + demo video + LinkedIn series | ⬜ Planned |
