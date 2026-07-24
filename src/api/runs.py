"""Legacy + admin-callable run endpoints."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.orm import Session

from src.api._common import api_error, ok
from src.api.schemas import (
    AskRequest,
    AskResponse,
    UploadResponse,
)
from src.config.settings import get_settings
from src.db.connections import ConnectionManager, _load_registry, _touch
from src.db.models import RunRow
from src.db.session import get_session
from src.domain.run import RunRequest, RunResult
from src.graph.runner import run_agent
from src.graph.agent import agentic_ai

router = APIRouter()


def _to_result(run: RunRow) -> RunResult:
    return RunResult(
        run_id=str(run.id),
        status=run.status,
        output_text=run.output_text,
        provider=run.provider,
        model=run.model,
        error_message=run.error_message,
    )


@router.post("/runs/ask")
async def ask(req: AskRequest, session: Session = Depends(get_session)):
    try:
        reg = _load_registry()
        csv_files = [{"table_name": t, "original_name": t} for t in reg.keys()]
        
        state: dict[str, Any] = {
            "run_id": f"api-{abs(hash(req.question)) % 100000 + 1000}",
            "user_id": "default",
            "question": req.question,
            "role": req.role,
            "db_conn_id": req.db_conn_id,
            "csv_files": csv_files,
            "error": None,
        }
        out = agentic_ai.invoke(state)
        error = out.get("error")
        answer = (out.get("output") or out.get("answer") or "").strip()
        
        if error:
            answer = f"Error: {error}"
        elif not answer:
            answer = "No answer was produced."

        provider = get_settings().resolve_provider()
        model = get_settings().resolve_model()

        run = RunRow(
            input_text=req.question,
            instruction=req.role,
            status="failed" if error else "completed",
            provider=provider,
            model=model,
            output_text=answer,
            error_message=str(error) if error else None,
        )
        session.add(run)
        session.commit()

        return {
            "run_id": str(run.id),
            "status": "failed" if error else "completed",
            "output": answer,
            "source_summary": out.get("source_summary"),
            "chart": out.get("chart"),
            "table_data": out.get("table_data"),
            "error": str(error) if error else None,
        }
    except Exception as exc:
        provider = get_settings().resolve_provider()
        model = get_settings().resolve_model()
        run = RunRow(
            input_text=getattr(req, "question", ""),
            instruction=getattr(req, "role", ""),
            status="failed",
            provider=provider,
            model=model,
            output_text=str(exc)[:10_000],
            error_message=str(exc)[:10_000],
        )
        session.add(run)
        session.commit()
        return {
            "run_id": str(run.id),
            "status": "failed",
            "output": str(exc),
            "source_summary": None,
            "chart": None,
            "table_data": None,
            "error": str(exc),
        }


@router.post("/runs/upload-csv")
@router.post("/upload-csv", include_in_schema=False)
async def upload_csv(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    targets: list[UploadFile] = []
    for _, value in form.multi_items():
        if hasattr(value, "filename"):
            targets.append(value)
        elif isinstance(value, list):
            targets.extend([item for item in value if hasattr(item, "filename")])

    if not targets or len(targets) > 5:
        return ok({
            "uploaded": [],
            "errors": [{"filename": "", "error": "Please upload 1 to 5 files at a time."}],
            "total_uploaded": 0,
        })

    mgr = ConnectionManager(
        ferkey=get_settings().fernet_key.encode() if get_settings().fernet_key else None,
    )

    uploaded: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for f in targets:
        if not f.filename:
            errors.append({"filename": "", "error": "File missing a name."})
            continue

        filename_lower = f.filename.lower()
        if not (filename_lower.endswith(".csv") or f.content_type in {
            "text/csv", "application/vnd.ms-excel", "application/csv",
        }):
            errors.append({"filename": f.filename, "error": "Only CSV files are supported."})
            continue

        try:
            raw = await f.read()
            if not raw.strip():
                errors.append({"filename": f.filename, "error": "Empty file."})
                continue
            table_name, n_rows, cols = mgr.csv_to_sqlite(raw, f.filename)
            if table_name:
                _touch(table_name, n_rows)
            uploaded.append({
                "filename": f.filename,
                "table_name": table_name,
                "rows": n_rows,
                "columns": cols,
            })
        except Exception as exc:
            errors.append({"filename": f.filename, "error": str(exc)})

    return ok({
        "uploaded": uploaded,
        "errors": errors,
        "total_uploaded": len(uploaded),
    })


@router.delete("/runs/csv-tables/{table_name:path}")
def delete_csv_table(table_name: str):
    mgr = ConnectionManager(
        ferkey=get_settings().fernet_key.encode() if get_settings().fernet_key else None,
    )
    reg = _load_registry()
    if table_name not in reg:
        raise api_error("table_not_found", f"No temp table: {table_name}", 404)
    mgr.drop_temp_table(table_name)
    return ok({"deleted": table_name})


@router.get("/runs/csv-tables")
async def csv_tables():
    reg = _load_registry()
    out: list[dict[str, Any]] = []
    for table_name, row_count in reg.items():
        out.append({"table_name": table_name, "rows": row_count, "filename": table_name})
    return ok({"tables": out})


@router.post("/runs/upload", response_model=UploadResponse, include_in_schema=False)
@router.post("/runs", response_model=RunResult)
def create_run(req: RunRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    run_id = run_agent(req.text, req.instruction)
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("run_not_found", f"run {run_id} vanished", 500)
    return ok(_to_result(run).model_dump())


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("run_not_found", f"no run with id {run_id}", 404)
    return ok(_to_result(run).model_dump())
