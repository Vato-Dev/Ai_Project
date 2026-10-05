import json
from pathlib import Path
from fastapi.testclient import TestClient
from ticket_app.api import create_app


def test_baseline_health_and_analysis(tmp_path):
    policy = json.loads(Path("scenarios/g00.json").read_text())
    client = TestClient(create_app(policy=policy, db_path=str(tmp_path / "test.db")))
    assert client.get("/health").status_code == 200
    response = client.post(
        "/api/analyze",
        json={"subject": "Help request", "text": "Please help me route this request."},
    )
    assert response.status_code == 200
    assert response.json()["requires_review"] is True


def test_invalid_input(tmp_path):
    policy = json.loads(Path("scenarios/g00.json").read_text())
    client = TestClient(create_app(policy=policy, db_path=str(tmp_path / "test.db")))
    assert client.post("/api/analyze", json={"subject": "x", "text": "x"}).status_code == 422
