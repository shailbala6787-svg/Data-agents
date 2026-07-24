"""Smoke test that imports the FastAPI app for inference."""
from fastapi.testclient import TestClient

from src.api import create_app


def test_app_importable():
 from src.api import create_app
 app = create_app()
 assert app is not None
 c = TestClient(app)
 r = c.get("/health")
 assert r.status_code == 200
