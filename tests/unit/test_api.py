"""Pydantic models for all runs stored by the UP Police Data Analyst."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RunRecord(BaseModel):
 run_id: str | None = None
 status: str = "queued"
 question: str = ""
 role: str = "officer"
 db_conn_id: str | None = None
 user_id: str | None = None
 schema_hint: str | None = None
 sql: str | None = None
 df_json: str = "[]"
 df_rows: int = 0
 df_columns: list[str] | None = None
 source_summary: str | None = None
 output: str | None = None
 error: str | None = None
 created_at: datetime | None = None
 finished_at: datetime | None = None


