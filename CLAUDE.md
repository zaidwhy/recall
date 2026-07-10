# Recall - Claude Instructions

Camera-based memory assistant: FastAPI backend + Gemini vision/live + React frontend served as static build (no frontend dev server).
Repo: https://github.com/syzayd/recall

## Run (three terminals, in this order)

Terminal 1 - build frontend (only needed after JSX/CSS changes; backend serves `frontend/dist`):
```powershell
cd C:\Users\Asus\projects\recall\frontend
npm run build
```

Terminal 2 - backend (port 8000):
```powershell
cd C:\Users\Asus\projects\recall
$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
First log line must be: `Vision model: gemini-2.5-flash | min gap between Flash calls: 120s`

Terminal 3 - tunnel (phone camera/mic require HTTPS):
```powershell
$env:PATH += ";C:\Program Files (x86)\cloudflared"
cloudflared tunnel --url http://localhost:8000
```
Open the printed `https://*.trycloudflare.com` URL on the phone.

## Python environment

- No venv: this project runs on the GLOBAL Python install (`python` / `py`).
- If backend imports fail, run `pip install -r backend/requirements.txt` (chromadb went missing from global Python once; reinstalled 2026-07-02, chromadb 1.5.9 works on Python 3.14).

## Tests / eval

- No pytest suite. Eval benchmark: `python -m eval.benchmark` (uses an isolated temp ChromaDB, never touches `data/`).

## Env

- `.env` at repo root needs `GEMINI_API_KEY`; template in `.env.example`. Never read `.env` directly; ask the user for values.
- Vision model defaults to `gemini-2.5-flash`. Free-tier quota is 20 vision calls/day; the ingest loop stops at 18 to keep 2 in reserve. Do NOT enable billing - it removes the free tier.

## Logs and handoffs (required every session)

- Master log: `MASTER_LOG.md` - append only, read just the tail (it is long).
- Handoffs: `handoffs/HANDOFF-YYYY-MM-DD-HHMM.md`.
- Before ending a session: update the master log AND write a handoff.

## Gotchas

- To wipe all memories: delete the `data/` folder.
- `RECALL_MAX_DISTANCE = 1.4` is the recall relevance cutoff; tune down toward 1.1 if wrong objects appear.
- Never use the em dash character (U+2014) anywhere; use " - " instead.
