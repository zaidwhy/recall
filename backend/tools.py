"""Function-calling tools exposed to the Gemini Live session."""
from __future__ import annotations

import logging
import time

from google.genai import types

from . import memory

log = logging.getLogger("recall")

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


def _format_time(minutes_ago: int) -> str:
    if minutes_ago < 1:
        return "just now"
    if minutes_ago < 60:
        return f"{minutes_ago} minute{'s' if minutes_ago != 1 else ''} ago"
    hours = round(minutes_ago / 60)
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = round(hours / 24)
    return f"{days} day{'s' if days != 1 else ''} ago"


def handle_tool_call(name: str, args: dict) -> dict:
    """Execute a tool call from the Live model. Returns a speakable result dict."""
    if name != "recall_memory":
        return {"error": f"unknown tool {name}"}

    query = args.get("query", "")
    minutes_ago = args.get("minutes_ago")
    since = time.time() - minutes_ago * 60 if minutes_ago else None

    result = memory.recall_for_tool(query, since=since)

    if result["matches"]:
        log.info("recall query=%r  top_dist=%.3f  confident=%s  (threshold=%.1f)",
                 query, result["matches"][0].get("distance"), result["confident"], memory.RECALL_MAX_DISTANCE)
    else:
        log.info("recall query=%r  no matches in store", query)

    now = time.time()
    matches = [
        {
            "location": m["location_label"],
            "scene_description": m["description"],
            "objects_visible": m["objects"],
            "time_ago": _format_time(round((now - m["timestamp"]) / 60)),
            "id": m["id"],
        }
        for m in result["matches"]
    ]
    return {"confident": result["confident"], "matches": matches}
