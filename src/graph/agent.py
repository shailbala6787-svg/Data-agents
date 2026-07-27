"""Graph assembly - 5-node pipeline: ingest -> plan -> execute -> respond -> finalize."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.graph.edges import after_node
from src.graph.nodes import (
    execute_node,
    finalize,
    handle_error,
    ingest_node,
    plan_node,
    response_node,
)
from src.graph.state import AgentState


def build_agent():
    g = StateGraph(AgentState)

    g.add_node("ingest_node", ingest_node)
    g.add_node("transform_text", ingest_node)
    g.add_node("plan_node", plan_node)
    g.add_node("execute_node", execute_node)
    g.add_node("response_node", response_node)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    g.set_entry_point("ingest_node")

    stages = ["ingest_node", "plan_node", "execute_node", "response_node"]
    for i, src in enumerate(stages):
        targets: dict[str, str] = {}
        if i + 1 < len(stages):
            targets[stages[i + 1]] = stages[i + 1]
        targets["finalize"] = "finalize"
        targets["handle_error"] = "handle_error"
        targets["plan_node"] = "plan_node"
        
        def make_cond(current: str):
            def _cond(state: AgentState) -> str:
                if state.get("next"):
                    nxt = state["next"]
                    if nxt in targets:
                        return nxt
                if state.get("error"):
                    return "handle_error"
                idx = stages.index(current)
                if idx + 1 < len(stages):
                    return stages[idx + 1]
                return "finalize"
            return _cond

        g.add_conditional_edges(src, make_cond(src), targets)

    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = build_agent()
