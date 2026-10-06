import json
from pathlib import Path
import pytest
import httpx
from fastapi.testclient import TestClient

from ticket_app.api import create_app
from ticket_app.analysis_models import Request
from ticket_app.analysis_provider import LocalAnalysisProvider, ProviderUnavailable, InvalidModelOutput

MOCK_POLICY = {
    "id": "g01",
    "categories": ["account", "network", "software"],
    "instructions": "Route tickets safely."
}


def test_baseline_health_and_analysis(tmp_path):
    policy = json.loads(Path("scenarios/g01.json").read_text())
    client = TestClient(create_app(policy=policy, db_path=str(tmp_path / "test.db")))
    assert client.get("/health").status_code == 200
    response = client.post(
        "/api/analyze",
        json={"subject": "Help request", "text": "Please help me route this request."},
    )
    assert response.status_code == 200
    assert response.json()["requires_review"] is True


def test_invalid_input(tmp_path):
    policy = json.loads(Path("scenarios/g01.json").read_text())
    client = TestClient(create_app(policy=policy, db_path=str(tmp_path / "test.db")))
    assert client.post("/api/analyze", json={"subject": "x", "text": "x"}).status_code == 422



# 1. ТЕСТ НА ТАЙМАУТ АДАПТЕРА (Timeout test)
def test_adapter_timeout_handling():
    def timeout_handler(request: httpx.Request):
        raise httpx.TimeoutException("Connection timed out")

    transport = httpx.MockTransport(timeout_handler)
    provider = LocalAnalysisProvider(
        base_url="http://localhost:1234/v1",
        model="qwen2.5-7b",
        timeout=1.0,
        transport=transport
    )
    
    req = Request(subject="Password reset", text="User cannot log in to active directory.")
    with pytest.raises(ProviderUnavailable):
        provider.analyze(req, MOCK_POLICY)


def test_adapter_malformed_json_handling():
    def malformed_handler(request: httpx.Request):
        mock_response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Sure, I can help you with that ticket request!"
                }
            }]
        }
        return httpx.Response(200, json=mock_response)

    transport = httpx.MockTransport(malformed_handler)
    provider = LocalAnalysisProvider(
        base_url="http://localhost:1234/v1",
        model="qwen2.5-7b",
        transport=transport
    )
    
    req = Request(subject="Password reset", text="User cannot log in to active directory.")
    with pytest.raises(InvalidModelOutput):
        provider.analyze(req, MOCK_POLICY)


def test_adapter_unknown_category_handling():
    def unknown_category_handler(request: httpx.Request):
        bad_json_output = (
            '{"summary": "Broken printer issues", "category": "hardware", '
            '"priority": "low", "next_action": "Check cable connection."}'
        )
        mock_response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": bad_json_output
                }
            }]
        }
        return httpx.Response(200, json=mock_response)

    transport = httpx.MockTransport(unknown_category_handler)
    provider = LocalAnalysisProvider(
        base_url="http://localhost:1234/v1",
        model="qwen2.5-7b",
        transport=transport
    )
    
    req = Request(subject="Printer down", text="The office printer does not boot at all.")
    with pytest.raises(InvalidModelOutput):
        provider.analyze(req, MOCK_POLICY)


def test_api_failed_inference_does_not_write_history(tmp_path):
    def failure_handler(request: httpx.Request):
        return httpx.Response(500, text="Internal Server Error inside LM Studio")

    transport = httpx.MockTransport(failure_handler)
    provider = LocalAnalysisProvider(
        base_url="http://localhost:1234/v1",
        model="qwen2.5-7b",
        transport=transport
    )
    
    test_db = str(tmp_path / "test_history.db")
    app = create_app(provider=provider, policy=MOCK_POLICY, db_path=test_db)
    client = TestClient(app)
    
    payload = {"subject": "Network failure", "text": "WiFi completely dropped during the call."}
    response = client.post("/api/analyze", json=payload)
    
    assert response.status_code in [502, 503]
    
    history_response = client.get("/api/history")
    assert history_response.status_code == 200
    assert len(history_response.json()) == 0
