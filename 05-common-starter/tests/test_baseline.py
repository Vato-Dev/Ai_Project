import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from ticket_app.analysis_models import Request
from ticket_app.analysis_provider import (
    InvalidModelOutput,
    LocalAnalysisProvider,
    MockAnalysisProvider,
    ProviderUnavailable,
)
from ticket_app.api import create_app

MOCK_POLICY = {
    "id": "g01",
    "categories": ["account", "network", "software"],
    "instructions": "Route tickets safely.",
}


def load_policy():
    return json.loads(Path("scenarios/g01.json").read_text(encoding="utf-8"))


def make_provider(handler, timeout=5.0):
    return LocalAnalysisProvider(
        base_url="http://localhost:1234/v1",
        model="qwen/qwen2.5-vl-7b",
        timeout=timeout,
        transport=httpx.MockTransport(handler),
    )


def chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


#  Baseline tests (always mock, independent of .env)

def test_baseline_health_and_analysis(tmp_path):
    client = TestClient(
        create_app(
            provider=MockAnalysisProvider(),
            policy=load_policy(),
            db_path=str(tmp_path / "test.db"),
        )
    )
    assert client.get("/health").status_code == 200
    response = client.post(
        "/api/analyze",
        json={"subject": "Help request", "text": "Please help me route this request."},
    )
    assert response.status_code == 200
    assert response.json()["requires_review"] is True


def test_invalid_input(tmp_path):
    client = TestClient(
        create_app(
            provider=MockAnalysisProvider(),
            policy=load_policy(),
            db_path=str(tmp_path / "test.db"),
        )
    )
    assert client.post("/api/analyze", json={"subject": "x", "text": "x"}).status_code == 422


#  Adapter tests (httpx.MockTransport, no live model) 

def test_adapter_request_payload_and_parsing():
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        content = json.dumps(
            {
                "summary": "User cannot reset their account password.",
                "category": "account",
                "priority": "medium",
                "next_action": "Route to the identity team for review.",
            }
        )
        return chat_response(content)

    provider = make_provider(handler)
    result = provider.analyze(
        Request(subject="Reset fails", text="The password reset link does not work."),
        MOCK_POLICY,
    )

    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["body"]["model"] == "qwen/qwen2.5-vl-7b"
    assert captured["body"]["max_tokens"] > 0
    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert result.category == "account"


def test_adapter_timeout_handling():
    def timeout_handler(request: httpx.Request):
        raise httpx.TimeoutException("Connection timed out")

    provider = make_provider(timeout_handler, timeout=1.0)
    req = Request(subject="Password reset", text="User cannot log in to active directory.")
    with pytest.raises(ProviderUnavailable):
        provider.analyze(req, MOCK_POLICY)


def test_adapter_malformed_json_handling():
    def handler(request: httpx.Request):
        return chat_response("Sure, I can help you with that ticket request!")

    provider = make_provider(handler)
    req = Request(subject="Password reset", text="User cannot log in to active directory.")
    with pytest.raises(InvalidModelOutput):
        provider.analyze(req, MOCK_POLICY)


def test_adapter_unknown_category_handling():
    def handler(request: httpx.Request):
        return chat_response(
            '{"summary": "Broken printer issues", "category": "hardware", '
            '"priority": "low", "next_action": "Check cable connection."}'
        )

    provider = make_provider(handler)
    req = Request(subject="Printer down", text="The office printer does not boot at all.")
    with pytest.raises(InvalidModelOutput):
        provider.analyze(req, MOCK_POLICY)


#  API failure behaviour

def test_api_failed_inference_does_not_write_history(tmp_path):
    def failure_handler(request: httpx.Request):
        return httpx.Response(500, text="Internal Server Error inside LM Studio")

    provider = make_provider(failure_handler)
    app = create_app(provider=provider, policy=MOCK_POLICY, db_path=str(tmp_path / "test_history.db"))
    client = TestClient(app)

    response = client.post(
        "/api/analyze",
        json={"subject": "Network failure", "text": "WiFi completely dropped during the call."},
    )
    assert response.status_code in [502, 503]

    history_response = client.get("/api/history")
    assert history_response.status_code == 200
    assert len(history_response.json()) == 0