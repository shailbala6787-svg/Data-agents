"""Conditional edges for the UP Police Data Analyst agent graph.

After any node, route on ``state["error"]`` and ``state["status"]``:
 - error set -> handle_error
 - otherwise -> next stage node
"""
from __future__ import annotations

from src.graph.state import AgentState

NEXT_STAGE: dict[str, str] = {
    "transform_text": "plan_node",
    "plan_node": "execute_node",
    "execute_node": "response_node",
}


def after_transform(state: AgentState) -> str:
    print(f"[TRACE after_transform] state keys: {list(state.keys())}", flush=True)
    print(f"[TRACE after_transform] state.get('error'): {state.get('error')!r}", flush=True)
    print(f"[TRACE after_transform] state.get('next'): {state.get('next')!r}", flush=True)
    if state.get("error"):
        return "handle_error"
    nxt = state.get("next")
    if nxt is None:
        return "finalize"
    return nxt


# Backwards-compat aliases expected by the baseline test suite.
# The UP Police graph uses ingest_node/plan_node/execute_node/response_node.
after_node = after_transform
