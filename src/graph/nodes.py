"""Graph nodes for UP Police Data Analyst - the capability slot."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pandas as pd
import plotly
import plotly.express as px
import sqlalchemy as sa

from src.graph.state import AgentState
from src.llm.client import LLMClient, load_prompt
from src.llm.providers.base import LLMError
from src.db.connections import ConnectionManager
from src.db.session import get_session

_log = logging.getLogger("graph")

_manager: ConnectionManager | None = None


def _get_mgr() -> ConnectionManager:
    global _manager
    if _manager is None:
        from src.config.settings import get_settings

        s = get_settings()
        _manager = ConnectionManager(
            ferkey=s.fernet_key.encode() if s.fernet_key else None
        )
    return _manager


def get_schema_hint(schema: dict) -> str:
    lines: list[str] = []
    for tbl in schema.get("tables", []):
        if "original_name" in tbl and tbl["original_name"]:
            lines.append(f"TABLE: {tbl['name']} (Source: {tbl['original_name']})")
        else:
            lines.append(f"TABLE: {tbl['name']}")
        for col in tbl.get("columns", [])[:60]:
            lines.append(
                f" - {col['name']} ({col['type']}, nullable={col.get('nullable','?')})"
            )
    return "\n".join(lines[:500])


def _boot(state: AgentState, mgr: ConnectionManager) -> AgentState:
    print(f"[TRACE _boot] IN state keys={sorted(state.keys() if state else [])}")
    out: AgentState = {"error": None, **(state or {})}
    print(f"[TRACE _boot] OUT keys={sorted(out.keys())}")
    
    schema = {"tables": []}
    
    if state.get("db_conn_id") and state.get("user_id"):
        try:
            _, _, db_schema = mgr.get_session(
                state["user_id"], int(state["db_conn_id"]), state.get("role", "officer")
            )
            schema["tables"].extend(db_schema.get("tables", []))
        except Exception as exc:
            _log.warning("schema_load_failed: %s", exc)

    csv_files = out.get("csv_files", [])
    if csv_files:
        try:
            with mgr._csv_engine.connect() as conn:
                for tbl in csv_files:
                    tname = tbl.get("table_name")
                    if not tname: continue
                    rows = conn.execute(sa.text(f"PRAGMA table_info('{tname}')")).fetchall()
                    if not rows:
                        continue
                    cols = []
                    for r in rows:
                        cols.append({"name": r[1], "type": r[2], "nullable": not bool(r[3])})
                    original = tbl.get("original_name")
                    schema["tables"].append({"name": tname, "original_name": original, "columns": cols})
        except Exception as exc:
            _log.warning("csv_schema_load_failed: %s", exc)

    if schema["tables"]:
        out["schema"] = schema  # type: ignore[assignment]
        out["schema_hint"] = get_schema_hint(schema)  # type: ignore[assignment]

    return out


def _llm_sql(question: str, schema_hint: str) -> str:
    system = load_prompt("sql_generation_officer")
    user = f"{schema_hint}\n\nQUESTION:\n{question}\n\nGenerate SQL:\n"
    return LLMClient().complete(system, user, max_tokens=2048)


def _llm_sql_analyst(question: str, schema_hint: str) -> str:
    system = load_prompt("sql_generation_analyst")
    user = f"{schema_hint}\n\nQUESTION:\n{question}\n\nGenerate SQL:\n"
    return LLMClient().complete(system, user, max_tokens=2048)


def _looks_chartable(question: str, columns: list[str], rows_count: int) -> bool:
    if rows_count < 2 or rows_count > 2000:
        return False
    text = f"{question} {' '.join(str(c) for c in columns)}".lower()
    hints = [
        "trend",
        "trends",
        "chart",
        "plot",
        "graph",
        "visualize",
        "visualisation",
        "bar",
        "pie",
        "line",
        "histogram",
        "scatter",
        "distribution",
        "compare",
        "comparison",
        "over time",
        "monthly",
        "yearly",
        "district-wise",
        "district wise",
        "top",
        "breakdown",
        "analysis",
    ]
    return any(h in text for h in hints)


def _render_chart(
    df_json: str, question: str, run_id: str
) -> tuple[dict | None, dict | None]:
    try:
        rows = pd.read_json(df_json)
        if rows.empty:
            return None, None

        numeric_cols = [
            c for c in rows.columns if pd.api.types.is_numeric_dtype(rows[c])
        ]
        cat_cols = [c for c in rows.columns if c not in numeric_cols]
        text = f"{question} {' '.join(str(c) for c in columns)}".lower()

        chart_type = "bar"
        x_col = cat_cols[0] if cat_cols else rows.columns[0]
        y_col = (
            numeric_cols[0]
            if numeric_cols
            else (
                rows.columns[1]
                if len(rows.columns) > 1
                else rows.columns[0]
            )
        )

        if any(k in text for k in ["pie"]):
            chart_type = "pie"
        elif any(k in text for k in ["line", "trend", "over time", "time series", "monthly", "yearly"]):
            chart_type = "line"
        elif any(k in text for k in ["scatter", "correlation"]):
            chart_type = "scatter"
        elif any(k in text for k in ["histogram", "distribution"]):
            chart_type = "histogram"
            y_col = None

        fig = None
        if chart_type == "pie":
            fig = px.pie(rows.head(200), names=x_col, values=y_col, title=question)
        elif chart_type == "line":
            fig = px.line(rows.head(500), x=x_col, y=y_col, title=question)
        elif chart_type == "scatter":
            fig = px.scatter(rows.head(500), x=x_col, y=y_col, title=question)
        elif chart_type == "histogram":
            fig = px.histogram(rows.head(500), x=x_col, title=question)
        else:
            fig = px.bar(
                rows.head(200), x=x_col, y=y_col, title=question
            )  # fallback

        fig.update_layout(margin=dict(l=10, r=10, t=30, b=10))
        chart_spec = fig.to_dict()
        chart_spec["data"] = chart_spec.get("data", [])[:1]
        short = {
            "type": chart_type,
            "x": (
                rows[x_col].head(200).tolist()
                if x_col in rows.columns
                else []
            ),
            "y": (
                rows[y_col].head(200).tolist()
                if y_col and y_col in rows.columns
                else []
            ),
            "title": question,
            "xlabel": x_col,
            "ylabel": y_col or "count",
        }
        return chart_spec, short
    except Exception as exc:
        _log.debug("chart_render_failed: %s", exc)
        return None, None


def _df_to_table_payload(df_json: str, sql_text: str) -> dict | None:
    try:
        rows = json.loads(df_json)
        if not rows:
            return None
        visible = rows[:500]
        return {
            "columns": list(rows[0].keys()),
            "rows": visible,
            "total_rows": len(rows),
            "sql": sql_text,
        }
    except Exception as exc:
        _log.debug("table_payload_failed: %s", exc)
        return None


# ---- nodes ----


def ingest_node(state: AgentState) -> AgentState:
    mgr = _get_mgr()
    print(f"[TRACE ingest_node] input state: {state}")
    print(f"[TRACE ingest_node] input state type: {type(state)}")
    out: AgentState = {"error": None}
    out.update(state)
    print(f"[TRACE ingest_node] out after update: {out}")
    print(f"[TRACE ingest_node] out after update keys: {list(out.keys())}")
    csv_files = [
        t for t in out.get("csv_files", []) if isinstance(t, dict)
    ]
    if csv_files:
        _log.info(
            "ingest(%s): %d CSV table(s)", out.get("run_id"), len(csv_files)
        )
    result = _boot(out, mgr)
    if not result.get("error"):
        result["next"] = "plan_node"
    print(f"[TRACE ingest_node] OUT keys={sorted(result.keys())}")
    for k in [
        "question",
        "sql",
        "df_json",
        "chart",
        "table_data",
        "output",
        "answer",
        "error",
        "status",
        "source_summary",
    ]:
        print(f"[TRACE ingest_node]   {k}={result.get(k)!r}")
    return result


def plan_node(state: AgentState) -> AgentState:
    role = state.get("role", "officer")
    question = (state.get("question") or "").strip()
    schema_hint = state.get("schema_hint") or (
        "No schema available. Generated SQL is best-effort against known column names only."
    )
    out: AgentState = {**(state or {})}
    print(f"[TRACE plan_node] IN  keys={sorted(out.keys())}")
    for k in [
        "question",
        "sql",
        "df_json",
        "chart",
        "table_data",
        "output",
        "answer",
        "error",
        "status",
        "source_summary",
    ]:
        print(f"[TRACE plan_node]   {k}={out.get(k)!r}")
    _log.info("[PLAN] question=%r role=%r schema_hint=%r", question[:200], role, schema_hint[:200])
    try:
        if role == "officer":
            print(
                f"[TRACE plan_node] CALLING _llm_sql  question={question!r}  schema_hint={schema_hint[:120]!r}"
            )
            raw_sql = _llm_sql(question, schema_hint)
        else:
            system = load_prompt("sql_generation_analyst")
            user = f"QUESTION:\n{question}\n\nSCHEMA_HINT:\n{schema_hint}\n\nGenerate SQL:\n"
            print(f"[TRACE plan_node] CALLING LLMClient  role=analyst")
            raw_sql = LLMClient().complete(system, user, max_tokens=2048)
            
        import re
        match = re.search(r'```(?:sql)?\n?(.*?)\n?```', raw_sql, re.IGNORECASE | re.DOTALL)
        if match:
            out["sql"] = match.group(1).strip()
        else:
            # Fallback if no markdown blocks are found
            out["sql"] = raw_sql.strip()
            
        print(f"[TRACE plan_node] OUT sql={out.get('sql')!r}")
    except LLMError as exc:
        out["error"] = str(exc)
        _log.error("[PLAN] LLM failed: %s", exc)
        print(f"[TRACE plan_node] LLMError: {exc}")
        return out
    except Exception as exc:
        out["error"] = f"Planner error: {exc}"
        _log.error("[PLAN] unexpected: %s", exc)
        print(f"[TRACE plan_node] EXCEPTION: {exc}")
        import traceback

        traceback.print_exc()
        return out
    _log.info("[PLAN] generated_sql=%r", (out.get("sql") or "")[:500])
    print(f"[TRACE plan_node] generated_sql={out.get('sql')!r}")
    return out


def execute_node(state: AgentState) -> AgentState:
    mgr = _get_mgr()
    out: AgentState = {**(state or {})}
    print(f"[TRACE execute_node] IN keys={sorted(out.keys())}")
    for k in [
        "question",
        "sql",
        "df_json",
        "chart",
        "table_data",
        "output",
        "answer",
        "error",
        "status",
        "source_summary",
    ]:
        print(f"[TRACE execute_node]   {k}={out.get(k)!r}")
    sql = (state.get("sql") or "").strip()
    role = state.get("role", "officer")
    user_id = state.get("user_id", "")
    conn_id = state.get("db_conn_id")
    csv_files = out.get("csv_files") or []
    question = state.get("question") or ""

    # --- DEBUG ---
    _log.info(
        "[EXECUTE] question=%r sql=%r csv_files=%d conn_id=%s",
        question,
        sql[:500],
        len(csv_files),
        conn_id,
    )
    # --- END DEBUG ---

    if not sql:
        out["error"] = "No SQL produced by plan step."
        print(f"[TRACE execute_node] No SQL -> error set")
        result = out
        print(f"[TRACE execute_node] OUT keys={sorted(result.keys())}")
        for k in [
            "question",
            "sql",
            "df_json",
            "chart",
            "table_data",
            "output",
            "answer",
            "error",
            "status",
            "source_summary",
        ]:
            print(f"[TRACE execute_node]   {k}={result.get(k)!r}")
        return result

    source_summary: list[str] = []
    dfs: list[object] = []

    # ---- MsSQL path ----
    if conn_id is not None and user_id:
        try:
            with get_session(user_id, int(conn_id), role) as cx:
                engine = cx.get_bind()
                capped = f"SELECT * FROM ({sql}) AS _upc LIMIT 500000"
                mssql_df = pd.read_sql(sa.text(capped), engine)
            if mssql_df is not None and not mssql_df.empty:
                dfs.append(mssql_df)
            n_rows = len(mssql_df) if mssql_df is not None else 0
            source_summary.append(
                f"MsSQL - {n_rows} row(s), capped at 500000"
            )
            # --- DEBUG ---
            _log.info(
                "[EXECUTE] mssql_df shape=%s cols=%s",
                mssql_df.shape,
                mssql_df.columns.tolist(),
            )
            _log.info(
                "[EXECUTE] mssql_df.head(5)=\n%s",
                mssql_df.head(5).to_string(),
            )
            # --- END DEBUG ---
        except Exception as exc:
            out["error"] = f"MsSQL query failed: {exc}"
            _log.error("[EXECUTE] mssql failed: %s", exc)
            print(f"[TRACE execute_node] MsSQL exception: {exc}")
            result = out
            print(f"[TRACE execute_node] OUT keys={sorted(result.keys())}")
            for k in [
                "question",
                "sql",
                "df_json",
                "chart",
                "table_data",
                "output",
                "answer",
                "error",
                "status",
                "source_summary",
            ]:
                print(f"[TRACE execute_node]   {k}={result.get(k)!r}")
            return result

    # ---- CSV path ----
    if csv_files and not (conn_id is not None and user_id):
        try:
            capped = f"SELECT * FROM ({sql}) AS _upc LIMIT 50000"
            with mgr._csv_engine.connect() as conn:
                csv_df = pd.read_sql(sa.text(capped), conn)
            if csv_df is not None and not csv_df.empty:
                dfs.append(csv_df)
            source_summary.append(
                f"CSV Query - {len(csv_df)} row(s)"
            )
        except Exception as exc:
            _log.debug("csv_read_failed: %s", exc)
            out["error"] = f"CSV query failed: {exc}"
            result = out
            return result

    if not dfs:
        out["df_json"] = "[]"
        out["df_rows"] = 0
        out["df_columns"] = []
        out["source_summary"] = "Zero rows returned across all sources."
        out["status"] = "completed"
        _log.warning("[EXECUTE] no data sources returned anything")
        print(f"[TRACE execute_node] No data sources -> df_json=[]")
        result = out
        print(f"[TRACE execute_node] OUT keys={sorted(result.keys())}")
        for k in [
            "question",
            "sql",
            "df_json",
            "chart",
            "table_data",
            "output",
            "answer",
            "error",
            "status",
            "source_summary",
        ]:
            print(f"[TRACE execute_node]   {k}={result.get(k)!r}")
        return result

    merged = (
        pd.concat(dfs, ignore_index=True)
        if len(dfs) > 1
        else dfs[0]
    )
    out["df_rows"] = len(merged)
    out["df_columns"] = list(merged.columns)
    out["df_json"] = (
        merged.head(200)
        .to_json(orient="records", default_handler=str, date_format="iso")
    )
    out["source_summary"] = "; ".join(source_summary)
    out["status"] = "completed"
    _log.info(
        "[EXECUTE] merged shape=%s cols=%s head5:\n%s",
        merged.shape,
        list(merged.columns),
        merged.head(5).to_string(),
    )
    print(
        f"[TRACE execute_node] merged shape={merged.shape} columns={list(merged.columns)} df_json len={len(out['df_json'])}"
    )
    result = out
    print(f"[TRACE execute_node] OUT keys={sorted(result.keys())}")
    for k in [
        "question",
        "sql",
        "df_json",
        "chart",
        "table_data",
        "output",
        "answer",
        "error",
        "status",
        "source_summary",
    ]:
        print(f"[TRACE execute_node]   {k}={result.get(k)!r}")
    return result


def response_node(state: AgentState) -> AgentState:
    out: AgentState = {**(state or {})}
    print(f"[TRACE response_node] IN keys={sorted(out.keys())}")
    for k in [
        "question",
        "sql",
        "df_json",
        "chart",
        "table_data",
        "output",
        "answer",
        "error",
        "status",
        "source_summary",
    ]:
        print(f"[TRACE response_node]   {k}={out.get(k)!r}")
    if state.get("error"):
        out["status"] = "failed"
        print(f"[TRACE response_node] error present -> status=failed")
        result = out
        print(f"[TRACE response_node] OUT keys={sorted(result.keys())}")
        for k in [
            "question",
            "sql",
            "df_json",
            "chart",
            "table_data",
            "output",
            "answer",
            "error",
            "status",
            "source_summary",
        ]:
            print(f"[TRACE response_node]   {k}={result.get(k)!r}")
        return result

    role = out.get("role", "officer")
    schema_hint = out.get("schema_hint") or "No schema hint available."
    df_json = out.get("df_json") or "[]"
    sql_text = state.get("sql") or ""

    rows = []
    try:
        rows = json.loads(df_json)
    except Exception:
        rows = []

    chart = None
    table_data = None
    chart_short = None

    if rows:
        _, chart_short = _render_chart(
            df_json, out.get("question", ""), out.get("run_id", "run")
        )
        table_data = _df_to_table_payload(df_json, sql_text)
        chart = chart_short

    if role == "officer":
        system = load_prompt("answer_officer")
        user = (
            f"DATA (JSON):\n{df_json}\n\n"
            f"OFFICER QUESTION:\n{out.get('question', '')}\n\n"
            f"SCHEMA_HINT:\n{schema_hint}\n\n"
            "Return a short answer. If visualization helps, mention it.\n"
        )
    else:
        system = load_prompt("answer_analyst")
        user = (
            f"SOURCE SUMMARY:\n{out.get('source_summary', 'n/a')}\n\n"
            f"DATA (JSON):\n{df_json}\n\n"
            f"ANALYST QUESTION:\n{out.get('question', '')}\n\n"
            f"SCHEMA_HINT:\n{schema_hint}\n\n"
            "If a visualization would help, include a one-line description.\n"
        )

    print(
        f"[TRACE response_node] CALLING LLMClient  role={role}  prompt_len={len(system)+len(user)}"
    )
    try:
        answer = LLMClient().complete(system, user, max_tokens=2048)
        print(f"[TRACE response_node] LLM RAW RESPONSE: {answer!r}")
        out["output"] = (
            f"{answer}\n\n![Chart]({chart_short})"
            if chart and role == "officer"
            else answer
        )
        out["chart"] = chart
        out["table_data"] = table_data
        out["status"] = "completed"
    except Exception as exc:
        out["error"] = str(exc)
        out["status"] = "failed"
        print(f"[TRACE response_node] LLM EXCEPTION: {exc}")
        import traceback

        traceback.print_exc()

    result = out
    print(f"[TRACE response_node] OUT keys={sorted(result.keys())}")
    for k in [
        "question",
        "sql",
        "df_json",
        "chart",
        "table_data",
        "output",
        "answer",
        "error",
        "status",
        "source_summary",
    ]:
        print(f"[TRACE response_node]   {k}={result.get(k)!r}")
    return result


def handle_error(state: AgentState) -> AgentState:
    return {"status": "failed", "error": state.get("error", "Unknown error.")}


def finalize(state: AgentState) -> AgentState:
    return {"status": state.get("status", "completed")}


def transform_text(state):
    try:
        from src.config.settings import get_settings

        s = get_settings()
    except Exception as exc:
        return {
            "error": f"AGENT_CONFIG_INVALID: {type(exc).__name__}: {exc}"
        }
    if s.resolve_provider() == "stub":
        return {"error": "AGENT_UNCONFIGURED: configure a provider key or AGENT_FERNET_KEY."}
    return {"error": None, **state}