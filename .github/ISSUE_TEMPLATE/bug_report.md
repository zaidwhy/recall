---
name: Bug report
about: Something in Recall doesn't work as expected
title: "[Bug] "
labels: bug
assignees: ''
---

**Describe the bug**
A clear description of what went wrong.

**To reproduce**
Steps to reproduce (backend log line, tunnel URL behavior, phone browser action):
```
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# then...
```

**Expected behavior**
What you expected to happen instead.

**Environment**
- OS:
- Python version (`python --version`):
- Node version (`node --version`), if frontend-related:
- Phone browser (if camera/mic/tunnel-related):

**Additional context**
Logs, stack traces, or anything else relevant. Redact your `RECALL_TOKEN`,
`GEMINI_API_KEY`, and any personal memory content before pasting.
