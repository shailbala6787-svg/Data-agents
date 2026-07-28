"""FastAPI app factory + lifespan. Serves the static frontend at /app."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "public"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from src.config.settings import get_settings
    from src.db.session import init_db
    from src.observability.events import configure_logging

    configure_logging(get_settings().log_level)
    init_db()
    
    from src.graph.nodes import _get_mgr
    _get_mgr()
    
    yield


def create_app() -> FastAPI:
 app = FastAPI(title="UP Police Data Analyst", version="0.2.0", lifespan=_lifespan)

 from fastapi.middleware.cors import CORSMiddleware
 app.add_middleware(
     CORSMiddleware,
     allow_origins=["*"],
     allow_credentials=True,
     allow_methods=["*"],
     allow_headers=["*"],
 )

 from src.api import health, runs

 app.include_router(health.router)
 app.include_router(runs.router)

 if _FRONTEND_DIR.is_dir():
  app.mount("/app", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
  
  from fastapi.responses import RedirectResponse
  @app.get("/")
  def root_redirect():
      return RedirectResponse(url="/app/")

 return app


app = create_app()
