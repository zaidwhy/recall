# Contributing

Thanks for looking at Recall. It is a personal project, but issues and small, focused
PRs are welcome.

## Ground rules

1. **Tests stay offline.** `pytest tests/ -q` must pass with no `GEMINI_API_KEY`, no
   network, and no real ChromaDB data - it only exercises `RECALL_TOKEN` auth on the
   HTTP routes and `/ws`. `eval/benchmark.py` creates its own isolated temp ChromaDB
   and never touches `data/`.
2. **One concern per PR.** Small and surgical beats broad and clever.
3. **Never touch the quota/rate-limit guards without tests.** The 120-second minimum
   gap between Flash calls and the 18/20 daily budget cap exist to keep the free tier
   usable for a full demo session; any change to `backend/` logic that governs them
   needs a corresponding test in `tests/test_rate_limit.py`.
4. **Privacy stays intact.** Frames and mic audio leave the device only to reach
   Gemini; embeddings, thumbnails, and memory descriptions stay local in `data/`. Don't
   add telemetry or a new outbound call without calling it out in the PR description.

## Dev setup

Follow the Quick start in [README.md](README.md) (global Python, no venv), then:

```bash
pip install -r backend/requirements.txt
pytest tests/ -q
```

All tests should pass before and after your change. CI runs the same command on every
push and PR.
