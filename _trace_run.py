"""Thin wrapper: rebuilds the graph with per-node tracing and runs one question."""
from __future__ import annotations

import importlib
import logging
import sys
import time

import src.graph.edges as edges_mod
import src.graph.nodes as nodes_mod
import src.graph.agent as agent_mod

# ---------------------------------------------------------------------------
# Reload all three graph modules so picked-up code is the latest on disk.
# ---------------------------------------------------------------------------
for mod in (edges_mod, nodes_mod, agent_mod):
    importlib.reload(mod)

from src.graph.agent import build_agent, agentic_ai as _orig_agent
from src.config.settings import get_settings

# ---------------------------------------------------------------------------
# Logging: DEBUG everywhere so we see every LLM call and exception.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
    force=True,
)


# ---------------------------------------------------------------------------
# Patch every node in the freshly compiled graph with a tracer wrapper.
# ---------------------------------------------------------------------------
def _make_tracer(name, fn):
    def wrapped(state):
        t0 = time.perf_counter()
        sin = dict(state)
        print(f"\n{'='*60}")
        print(f"  NODE ENTER: {name}")
        print(f"{'='*60}")
        print(f"  input keys  : {sorted(sin.keys())}")
        for k in ("question", "sql", "df_json", "chart", "table_data",
                  "output", "answer", "error", "status", "source_summary"):
            v = sin.get(k)
            if isinstance(v, str) and v and len(v) > 400:
                v = v[:400] + "..."
            print(f"    {k}: {v!r}")

        try:
            result = fn(sin)
        except Exception as exc:
            dt = time.perf_counter() - t0
            print(f"\n  !! NODE EXCEPTION in {name} after {dt:.3f}s !!")
            print(f"  !! {type(exc).__name__}: {exc}")
            import traceback; traceback.print_exc()
            raise

        dt = time.perf_counter() - t0
        sout = dict(result)
        print(f"\n  NODE EXIT : {name}  ({dt:.3f}s)")
        print(f"  output keys: {sorted(sout.keys())}")
        for k in ("question", "sql", "df_json", "chart", "table_data",
                  "output", "answer", "error", "status", "source_summary"):
            v = sout.get(k)
            if isinstance(v, str) and v and len(v) > 400:
                v = v[:400] + "..."
            print(f"    {k}: {v!r}")
        print(f"{'='*60}\n")
        return result

    wrapped.__name__ = f"_traced_{name}"
    return wrapped


_trace_map = {
    "ingest_node": nodes_mod.ingest_node,
    "plan_node":   nodes_mod.plan_node,
    "execute_node": nodes_mod.execute_node,
    "response_node": nodes_mod.response_node,
    "handle_error":  nodes_mod.handle_error,
    "finalize":      nodes_mod.finalize,
    "transform_text": nodes_mod.transform_text,
}

traced = {k: _make_tracer(k, fn) for k, fn in _trace_map.items()}

# Rebuild the graph so it references our traced node functions.
g = build_agent()

# Replace node callables in the compiled graph's internal dict.
# LangGraph stores nodes in graph.nodes (a dict of Node objects).
for node_id, node_obj in g.nodes.items():
    if node_id in traced:
        node_obj.func = traced[node_id]

agentic_ai = g

# ---------------------------------------------------------------------------
# Provider diagnostics
# ---------------------------------------------------------------------------
settings = get_settings()
print(f"\n{'#'*60}")
print(f"# Provider : {settings.resolve_provider()}")
print(f"# Model    : {settings.resolve_model()}")
print(f"# Key set  : {bool(settings.openrouter_api_key)}")
print(f"{'#'*60}\n")

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
state = {
    "run_id": "debug-001",
    "user_id": "default",
    "question": "Total FIRs in 2023",
    "role": "officer",
    "db_conn_id": None,
    "error": None,
    "next": None,
}

print("\n>>> INVOKING GRAPH <<<")
t0 = time.perf_counter()
try:
    result = agentic_ai.invoke(state)
    dt = time.perf_counter() - t0
    print(f"\n{'#'*60}")
    print(f"# GRAPH DONE in {dt:.3f}s")
    print(f"{'#'*60}")
    print(f"Result keys  : {sorted(result.keys())}")
    for k in ("question", "sql", "df_json", "chart", "table_data",
              "output", "answer", "error", "status", "source_summary"):
        v = result.get(k)
        if isinstance(v, str) and v and len(v) > 600:
            v = v[:600] + "..."
        print(f"  {k}: {v!r}")
except Exception as exc:
    print(f"\n!! GRAPH FAILED: {exc}")
    import traceback; traceback.print_exc()
