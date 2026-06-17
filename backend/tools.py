"""Function-calling tools exposed to the Gemini Live session."""
from __future__ import annotations

import time

from google.genai import types

from . import memory

RECALL_TOOL = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="recall_memory",
        description=(
            "Search the user's visual memory of their physical space for where or when they "
            "last saw an object or were in a place. Call this for any 'where did I leave/put X', "
            "'when did I last see Y', or 'what was on the Z' question."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="What to look for, e.g. 'charger', 'my keys', 'the desk'",
                ),
                "minutes_ago": types.Schema(
                    type=types.Type.INTEGER,
                    description="Optional: only search memories from the last N minutes",
                ),
            },
            required=["query"],
        ),
    )
])


def handle_tool_call(name: str, args: dict) -> dict:
    """Execute a tool call from the Live model. Returns a small, speakable result dict."""
    if name != "recall_memory":
        return {"error": f"unknown tool {name}"}
    query = args.get("query", "")
    minutes_ago = args.get("minutes_ago")
    since = time.time() - minutes_ago * 60 if minutes_ago else None
    result = memory.recall_for_tool(query, since=since)
    now = time.time()
    matches = [
        {
            "location_label": m["location_label"],
            "description": m["description"],
            "objects": m["objects"],
            "minutes_ago": round((now - m["timestamp"]) / 60),
            "id": m["id"],
        }
        for m in result["matches"]
    ]
    return {"confident": result["confident"], "matches": matches}
