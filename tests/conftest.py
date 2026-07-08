"""Pytest bootstrap - must run before backend.main is imported anywhere.

RECALL_TOKEN is read once at module import time (backend/main.py), so it has to be
set in the environment before the first `import backend.main` in the test session.
"""
import os

os.environ.setdefault("RECALL_TOKEN", "test-recall-token")
