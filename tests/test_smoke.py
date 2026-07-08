"""Backend smoke suite - app import + RECALL_TOKEN auth on HTTP routes and /ws.

Offline, no GEMINI_API_KEY needed: perception/memory only touch Gemini/ChromaDB on
first *use*, not on import (see backend/perception.py::_client, backend/memory.py::_col).
"""
import os

from fastapi.testclient import TestClient

from backend.main import RECALL_TOKEN, app

GOOD_TOKEN = os.environ["RECALL_TOKEN"]
assert RECALL_TOKEN == GOOD_TOKEN  # sanity: module read the same env var conftest set


def test_app_imports():
    assert app.title == "Recall"


def test_health_without_token_is_401():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 401
    assert resp.json() == {"error": "unauthorized"}


def test_health_with_wrong_token_is_401():
    client = TestClient(app)
    resp = client.get("/health", headers={"X-Recall-Token": "not-the-token"})
    assert resp.status_code == 401


def test_health_with_header_token_is_200():
    client = TestClient(app)
    resp = client.get("/health", headers={"X-Recall-Token": GOOD_TOKEN})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_query_token_authenticates_and_sets_cookie_for_later_requests():
    client = TestClient(app)
    first = client.get(f"/health?token={GOOD_TOKEN}")
    assert first.status_code == 200
    assert client.cookies.get("recall_token") == GOOD_TOKEN

    # No token supplied this time - the cookie set above must carry the session.
    second = client.get("/health")
    assert second.status_code == 200


def test_other_api_routes_require_token():
    client = TestClient(app)
    assert client.get("/memory").status_code == 401
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/search?q=keys").status_code == 401
    assert client.delete("/memory").status_code == 401


def test_ws_without_token_is_rejected():
    client = TestClient(app)
    try:
        with client.websocket_connect("/ws"):
            assert False, "connection should have been rejected before accept()"
    except Exception:
        pass  # WebSocketDisconnect (or equivalent) is expected


def test_ws_with_token_is_accepted():
    client = TestClient(app)
    with client.websocket_connect(f"/ws?token={GOOD_TOKEN}") as ws:
        ws.close()
