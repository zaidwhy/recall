# Deployment - Recall on Render (free tier)

Everything except two secrets is already in the repo: `Dockerfile` (multi-stage: Vite build, then FastAPI serving `frontend/dist`) and `render.yaml` (Render Blueprint, free plan, Docker runtime). Deploying is a dashboard step because the secrets must never be in git.

## One-time setup (Zaid, ~5 minutes)

1. Render dashboard -> **New** -> **Blueprint** -> connect `zaidwhy/recall` -> Render reads `render.yaml`.
2. When prompted for the `sync: false` variables, set:
   - `GEMINI_API_KEY` - from https://aistudio.google.com/apikey (free tier; do not enable billing, it removes the free quota).
   - `RECALL_TOKEN` - any long random string (`python -c "import secrets; print(secrets.token_urlsafe(24))"`). Every route and the WebSocket require it.
3. Deploy. First build takes a few minutes (Node build + Python deps).
4. Open `https://<service>.onrender.com/?token=<RECALL_TOKEN>` once on the phone; the server sets an httponly cookie so later visits need no query string.
5. Set the GitHub repo homepage to the service URL (`gh repo edit zaidwhy/recall --homepage https://<service>.onrender.com`) and add the URL to the README "Live" line. Verify with `curl -sI -L <url>` (a 401 JSON is expected without the token; that means the service is up).

## What to expect on the free plan

- Cold start of ~25-50 s after 15 minutes idle. Acceptable for a demo; the CivilizationOS keep-alive cron is the one warm service allowed under the 750 hour/month limit.
- No persistent disk: `data/` (ChromaDB memories, thumbnails) resets on redeploy and on wake after spin-down. Revisit with a paid disk only if someone other than Zaid depends on the memories.
- Render's HTTP health check is intentionally not configured (`/health` is token-gated); Render falls back to a TCP check.

## Rollback

Render -> service -> Deploys -> pick the previous successful deploy -> **Rollback**. Config changes go through `render.yaml` in git, never only in the dashboard.

## Local Docker check before pushing

```powershell
docker build -t recall .
docker run --rm -p 8000:8000 -e RECALL_TOKEN=dev -e GEMINI_API_KEY=x recall
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/health   # 401 without the token = up
```
