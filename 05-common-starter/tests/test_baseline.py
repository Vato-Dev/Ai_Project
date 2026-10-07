import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ticket_app.analysis_models import Analysis, Record, Request
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

def load_fixtures():
    path = Path(__file__).parent / "fixtures.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy():
    return json.loads(Path("scenarios/g01.json").read_text(encoding="utf-8"))


def make_provider(handler, timeout=5.0):
    return LocalAnalysisProvider(
        base_url="http://localhost:1234/v1",
        model="qwen/qwen2.5-vl-7b",
        timeout=timeout,
        transport=httpx.MockTransport(handler),
    )


def chat_response(content) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )


def valid_payload(**overrides) -> dict:
    data = {
        "summary": "User cannot reset their account password.",
        "category": "account",
        "priority": "medium",
        "next_action": "Route to the identity team for review.",
    }
    data.update(overrides)
    return data


def analyze_with(handler):
    provider = make_provider(handler)
    req = Request(subject="Password reset", text="User cannot log in to active directory.")
    return provider.analyze(req, MOCK_POLICY)


# --- Baseline tests (always mock, independent of .env) ----------------------

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


# --- Mock routing: every fixture lands in its expected category -------------

@pytest.mark.parametrize("case", load_fixtures(), ids=lambda c: c["subject"])
def test_mock_routes_each_fixture(case):
    result = MockAnalysisProvider().analyze(
        Request(subject=case["subject"], text=case["text"]), load_policy()
    )
    assert result.category == case["expected_category"]
    assert result.priority == case["expected_priority"]
    # The mock only proposes routing; it never claims a real action happened.
    assert "reviewer" in result.next_action.lower()


def test_mock_flags_ambiguous_request_for_reviewer():
    result = MockAnalysisProvider().analyze(
        Request(subject="Printer problem", text="The office printer makes a strange noise."),
        load_policy(),
    )
    assert result.category in load_policy()["categories"]
    assert "reviewer" in result.next_action.lower()


def test_mock_does_not_match_keywords_inside_other_words():
    # "provide" contains "ide", "debug" contains "bug": neither is a software signal.
    result = MockAnalysisProvider().analyze(
        Request(subject="Please provide info", text="Could you debug nothing in particular?"),
        load_policy(),
    )
    assert "reviewer" in result.next_action.lower()


# --- Adapter tests (httpx.MockTransport, no live model) ---------------------

def test_adapter_request_payload_and_parsing():
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return chat_response(json.dumps(valid_payload()))

    result = analyze_with(handler)

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


def test_adapter_http_error_handling():
    with pytest.raises(ProviderUnavailable):
        analyze_with(lambda request: httpx.Response(500, text="boom"))


def test_adapter_malformed_json_handling():
    with pytest.raises(InvalidModelOutput):
        analyze_with(lambda request: chat_response("Sure, I can help you with that ticket request!"))


def test_adapter_unknown_category_handling():
    content = json.dumps(valid_payload(category="hardware"))
    with pytest.raises(InvalidModelOutput):
        analyze_with(lambda request: chat_response(content))


def test_adapter_rejects_non_object_json():
    with pytest.raises(InvalidModelOutput):
        analyze_with(lambda request: chat_response("[1, 2, 3]"))


@pytest.mark.parametrize("bad_category", [None, 42, ["account"]])
def test_adapter_rejects_non_string_category(bad_category):
    content = json.dumps(valid_payload(category=bad_category))
    with pytest.raises(InvalidModelOutput):
        analyze_with(lambda request: chat_response(content))


def test_adapter_normalizes_category_before_saving():
    content = json.dumps(valid_payload(category="  Account "))
    result = analyze_with(lambda request: chat_response(content))
    assert result.category == "account"


def test_adapter_accepts_json_inside_code_fence():
    content = "```json\n" + json.dumps(valid_payload()) + "\n```"
    result = analyze_with(lambda request: chat_response(content))
    assert result.category == "account"


def test_adapter_rejects_summary_that_is_too_short():
    content = json.dumps(valid_payload(summary="short"))
    with pytest.raises(InvalidModelOutput):
        analyze_with(lambda request: chat_response(content))


def test_adapter_rejects_null_message_content():
    with pytest.raises(InvalidModelOutput):
        analyze_with(lambda request: chat_response(None))


# --- requires_review is never model-dependent --------------------------------

def test_record_requires_review_cannot_be_false():
    analysis = Analysis(**valid_payload())
    with pytest.raises(ValidationError):
        Record(id="1", scenario="g01", provider="mock", analysis=analysis, requires_review=False)


# --- API failure behaviour ---------------------------------------------------

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