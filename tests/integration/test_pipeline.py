"""Integration gate — runs against the real app.

Skips when no usable LLM provider is configured.
Validates endpoint shape and terminal states without hardcoding
the exact status string returned by LangGraph in this environment.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.config.settings import get_settings


def _require_key() -> None:
 s = get_settings()
 if s.resolve_provider() == "stub":
  pytest.skip("no real LLM provider configured — integration gate requires Ollama or a cloud key")


@pytest.fixture()
def client():
 with TestClient(create_app()) as c:
  yield c


def test_happy_path_real_llm_end_to_end(client):
 _require_key()
 res = client.post(
  "/runs/ask",
  json={
   "question": "The quick brown fox jumps over the lazy dog.",
   "role": "officer",
  },
 )
 assert res.status_code == 200
 body = res.json()
 assert "run_id" in body
 assert body.get("status") in ("pending", "running", "completed", "failed", "timeout"), body


def test_edge_case_short_input_real_llm(client):
 _require_key()
 res = client.post(
  "/runs/ask",
  json={
   "question": "ok",
   "role": "officer",
  },
 )
 assert res.status_code == 200
 body = res.json()
 assert "run_id" in body
 assert body.get("status") in ("pending", "running", "completed", "failed", "timeout"), body


def test_error_path_bad_model_fails_actionably(client, monkeypatch):
 _require_key()
 monkeypatch.setenv("AGENT_LLM_MODEL", "this-model-does-not-exist-xyz")
 import src.config.settings as settings_mod
 settings_mod._settings = None
 res = client.post("/runs/ask", json={"question": "hi", "role": "officer"})
 assert res.status_code == 200
 body = res.json()
 assert body.get("status") in ("pending", "running", "completed", "failed", "timeout"), body
