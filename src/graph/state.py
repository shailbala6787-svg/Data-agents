"""AgentState — the TypedDict flowing through the UP Police Data Analyst graph."""
from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    # ---- identity ----
    run_id: str
    user_id: str
    role: str  # 'officer' | 'analyst' | 'admin'

    # ---- workspace (session-level, set at run creation) ----
    csv_files: list[dict]  # [{'table_name', 'original_name', 'rows', 'columns'}]
    db_conn_id: int | None
    schema: dict | None  # full schema dict from MsSQL
    schema_hint: str | None  # LLM-readable string built from schema

    # ---- per-query (within one ask) ----
    question: str
    sql: str | None
    source_summary: str | None
    df_json: str | None  # JSON-serialised rows (≤200)
    df_rows: int | None
    df_columns: list[str] | None

    # ---- output ----
    output: str | None  # final answer markdown/text

    # ---- visualization ----
    chart: dict | None  # structured chart config for frontend
    table_data: dict | None  # structured table data for frontend

    # ---- control ----
    error: str | None
    last_sql_error: str | None
    status: str | None  # pending | planning | executing | responding | completed | failed
    next: str | None  # next node hint
    sql_retries: int | None

