@echo off
REM One-click run parity (PROJECT-GENESIS.md Tier 6 item 43): starts the backend (which
REM serves the built frontend/dist) and opens the browser, mirroring this project's
REM entry in jarvis-launcher's jarvis.config.json ("run" action) so the launcher and
REM this repo never drift. Uses the global Python install (no venv), per CLAUDE.md.
REM
REM Local-only: this only launches the app on 127.0.0.1. Phone/camera access still
REM needs the separate cloudflared tunnel terminal documented in CLAUDE.md - this
REM script does not start a tunnel and never touches RECALL_TOKEN or .env.
setlocal

set "ROOT=%~dp0"

start "Recall Backend" /D "%ROOT%" cmd /k "set PYTHONIOENCODING=utf-8 && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(30); while((Get-Date) -lt $deadline) { try { Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8000' -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 } }; Start-Process 'http://localhost:8000'"

endlocal
