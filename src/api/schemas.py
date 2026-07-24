"""Request/response models for the UP Police Data Analyst API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=10_000)
    role: str = Field(default="officer", pattern="^(officer|analyst|admin)$")
    db_conn_id: int | None = None


class AskResponse(BaseModel):
    run_id: str
    status: str
    output: str | None = None
    source_summary: str | None = None
    error: str | None = None
    chart: dict | None = None
    table_data: dict | None = None
    download_url: str | None = None


class DBProfileCreate(BaseModel):
    name: str = Field(..., max_length=200)
    host: str = Field(..., max_length=255)
    port: int = Field(default=1433, ge=1, le=65535)
    database: str = Field(..., max_length=255)
    username: str = Field(..., max_length=255)
    password: str = Field(..., min_length=1, max_length=255)
    driver: str = Field(default="{ODBC Driver 17 for SQL Server}", max_length=255)


class DBProfileOut(BaseModel):
    id: int
    name: str
    host: str
    port: int
    database: str
    username: str
    created_at: str


class UploadResponse(BaseModel):
    uploaded: list[dict]
    errors: list[dict]
    total_uploaded: int


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[dict]
    total_rows: int


class DatasetItem(BaseModel):
    table_name: str
    rows: int | None = None


class DashboardResponse(BaseModel):
    total_datasets: int
    total_records: int
    total_queries: int
    completed_queries: int
    failed_queries: int
    active_connections: int
    recent_queries: list[dict]
    recent_uploads: list[dict]
    provider: str
    model: str
