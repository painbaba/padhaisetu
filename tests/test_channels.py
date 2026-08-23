import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

os.environ.setdefault("PADHAISETU_DB", ":memory:")


def make_client():
    from app.main import app

    return TestClient(app)


def test_health_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("PADHAISETU_DB", str(tmp_path / "m0.db"))
    client = make_client()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
