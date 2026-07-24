from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.graph.state import AgentState

_log = logging.getLogger("graph.trace")


def trace_node(name: str, fn):
    """Wrap a graph node to log full state before/after."""
    def wrapper(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        state_in = dict(state or {})
        _log.info("=== NODE %s START ===", name)
        _log.info("[%s] input keys: %s", name, sorted(state_in.keys()))
        for key in ["question", "sql", "df_json", "chart", "table_data", "output", "answer", "error", "status", "source_summary"]:
            val = state_in.get(key)
            if isinstance(val, str) and len(val) > 300:
                val = val[:300] + "..."
            _log.info("[%s] state[%s] = %r", name, key, val)

        try:
            result = fn(state)
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            _log.error("[%s] EXCEPTION after %.3fs: %s", name, elapsed, exc, exc_info=True)
            raise

        elapsed = time.perf_counter() - t0
        result_out = dict(result or {})
        _log.info("[%s] output keys: %s  (%.3fs)", name, sorted(result_out.keys()), elapsed)
        for key in ["question", "sql", "df_json", "chart", "table_data", "output", "answer", "error", "status", "source_summary"]:
            val = result_out.get(key)
            if isinstance(val, str) and len(val) > 500:
                val = val[:500] + "..."
            _log.info("[%s] state[%s] = %r", name, key, val)
        _log.info("=== NODE %s END ===\n", name)
        return result

    wrapper.__name__ = name
    return wrapper
