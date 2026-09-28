"""Guard for the dismissed chromadb Dependabot alerts (GHSA-f4j7-r4q5-qw2c, GHSA-2wm9-hf6c-p5cr,
GHSA-xph7-9rjv-w5fr, GHSA-36p7-vc44-83pf, dismissed 2026-09-28 as "vulnerable code not used").

Every one of them targets chroma's HTTP server (/api/v2 endpoints, its RBAC, collection configuration
with trust_remote_code). recall is safe only while it keeps chroma embedded: PersistentClient in-process,
one fixed collection, no caller-controlled configuration. If this test fails, those alerts apply again:
re-open them and re-assess before shipping. Pure source scan, so it needs no chromadb install.
"""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
SOURCES = {p: p.read_text(encoding="utf-8") for p in BACKEND.rglob("*.py")}


def test_no_chroma_http_client_or_server():
    forbidden = re.compile(
        r"\b(HttpClient|AsyncHttpClient|FastAPI\s*\(\s*chroma|chromadb\.server|chromadb\.app|chroma\s+run)\b"
    )
    hits = [f"{p.name}: {m.group(0)}" for p, text in SOURCES.items() for m in forbidden.finditer(text)]
    assert hits == [], f"chroma's HTTP client/server appeared: {hits}"


def test_no_trust_remote_code():
    hits = [p.name for p, text in SOURCES.items() if "trust_remote_code" in text]
    assert hits == [], f"trust_remote_code appeared in {hits}"


def test_only_the_fixed_collection_with_default_settings():
    calls = [
        (p.name, m.group(0))
        for p, text in SOURCES.items()
        for m in re.finditer(r"\b(?:get_or_create_collection|create_collection|get_collection)\s*\([^)]*\)", text)
    ]
    assert calls, "expected recall to open its chroma collection somewhere in backend/"
    unexpected = [c for c in calls if c[1].split("(", 1)[1].strip(" )") != '"observations"']
    assert unexpected == [], f"a collection other than the fixed 'observations' one, or with settings: {unexpected}"


def test_chroma_client_is_persistent_in_process():
    clients = [m.group(1) for text in SOURCES.values() for m in re.finditer(r"chromadb\.(\w*Client)\s*\(", text)]
    assert clients and set(clients) == {"PersistentClient"}, f"chroma clients in backend/: {clients}"
