# How to Run Recall

Three terminals, in this order. Wait for each to be up before starting the next.

## Terminal 1 - build the frontend (once, or after UI changes)

```powershell
cd C:\Users\Asus\projects\recall\frontend
npm run build
```

The FastAPI backend serves the built files, so there is no separate dev server to keep running.

## Terminal 2 - start the backend

```powershell
cd C:\Users\Asus\projects\recall
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The first log line should read: `Vision model: gemini-2.5-flash | min gap between Flash calls: 120s`.

## Terminal 3 - tunnel (HTTPS for the phone)

```powershell
$env:PATH += ";C:\Program Files (x86)\cloudflared"
cloudflared tunnel --url http://localhost:8000
```

cloudflared prints an `https://*.trycloudflare.com` URL. Open that URL on your phone: the camera and mic permissions require HTTPS, which is the whole reason the tunnel exists.

## On the phone

1. Open the tunnel URL.
2. Tap **Start camera**. Recording begins automatically.
3. Point the camera around the room. The pill shows when a scan fires and how many daily vision calls remain.
4. Hold the circular button and ask out loud, e.g. "where did I leave my keys?" Release to send.

## Notes

- The free-tier `gemini-2.5-flash` quota is 20 vision calls/day; the ingest loop stops at 18 to keep 2 in reserve. Quota resets at midnight. Do not enable billing: it removes the free tier.
- To wipe all memories: delete the `data/` folder.
- Eval: `python -m eval.benchmark` (uses an isolated temp ChromaDB, never touches `data/`).
