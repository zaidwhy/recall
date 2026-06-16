"""Function-calling tools exposed to the Gemini Live session (the interaction path).

Week 3 target. The Live model calls these to answer "where/when did I…" questions out loud:
    recall_memory(query)      -> semantic + temporal search over the memory store
    log_observation(...)      -> let the model record something on demand

Tool declarations are wired into the Live session config in main.py.
"""

from __future__ import annotations

# Intentionally empty for Week 1. See PLAN.md / DISCUSSION.md §4 (the demo moment).
