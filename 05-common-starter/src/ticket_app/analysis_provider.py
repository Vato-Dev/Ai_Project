import json
import re
from typing import Protocol

import httpx
from pydantic import ValidationError

from ticket_app.analysis_models import Analysis, Request


class ProviderUnavailable(RuntimeError):
    pass


class InvalidModelOutput(RuntimeError):
    pass


class AnalysisProvider(Protocol):
    def analyze(self, request: Request, policy: dict) -> Analysis: ...


# ---------------------------------------------------------------------------
# Mock provider (deterministic, used in CI and tests)
# ---------------------------------------------------------------------------

def _contains(text: str, keyword: str) -> bool:
    """Whole-word match that tolerates simple endings (crash -> crashes)."""
    pattern = rf"\b{re.escape(keyword.lower())}(?:s|es|ed|ing)?\b"
    return re.search(pattern, text) is not None


class MockAnalysisProvider:
    def analyze(self, request: Request, policy: dict) -> Analysis:
        text = " ".join(f"{request.subject} {request.text}".lower().split())
        categories = policy["categories"]
        keywords = policy.get("keywords", {})

        scores = {
            category: sum(_contains(text, kw) for kw in keywords.get(category, []))
            for category in categories
        }
        best = max(scores.values())
        winners = [c for c in categories if scores[c] == best]
        category = winners[0]
        ambiguous = best == 0 or len(winners) > 1

        high_words = policy.get("high_priority_words", [])
        priority = "high" if any(_contains(text, w) for w in high_words) else "medium"

        if ambiguous:
            next_action = "Category unclear: a reviewer must confirm the queue."
        else:
            next_action = f"Propose routing to the {category} queue; reviewer to confirm."

        return Analysis(
            summary=f"{request.subject}: {request.text}"[:240],
            category=category,
            priority=priority,
            next_action=next_action,
        )


# ---------------------------------------------------------------------------
# Local provider (LM Studio, OpenAI-compatible chat completions)
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.DOTALL)


def _extract_json_text(raw: str) -> str:
    """Strip an optional Markdown code fence around the model output."""
    raw = raw.strip()
    match = _FENCE_RE.match(raw)
    return match.group(1).strip() if match else raw


class LocalAnalysisProvider:
    def __init__(self, base_url, model, timeout=60, key="", transport=None):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.key = key
        self.transport = transport

    def analyze(self, request: Request, policy: dict) -> Analysis:
        # A missing "categories" key means a broken scenario file: fail loudly.
        allowed_categories = list(policy["categories"])

        system_instruction = (
            f"You are an IT Helpdesk triage expert. Analyze the user support ticket.\n"
            f"You MUST reply with a single, valid JSON object containing exactly four fields.\n"
            f"Do not enclose your output in markdown code blocks like ```json. Output ONLY raw JSON text.\n\n"
            f"JSON Schema specification:\n"
            f"{{\n"
            f'  "summary": "Short ticket summary (between 10 and 240 characters)",\n'
            f'  "category": "Must be exactly one of: {", ".join(allowed_categories)}",\n'
            f'  "priority": "Must be exactly one of: low, medium, high",\n'
            f'  "next_action": "Recommended step (between 10 and 240 characters)"\n'
            f"}}\n"
            f"Strict routing rules:\n"
            f"{policy.get('instructions', 'Route based on context.')}\n"
            f"Never claim that a real system action has occurred. Rely only on provided facts."
        )

        user_content = f"Subject: {request.subject}\nTicket Text: {request.text}"
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
            "max_tokens": 300,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "ticket_triage",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "category": {"type": "string", "enum": allowed_categories},
                            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                            "next_action": {"type": "string"},
                        },
                        "required": ["summary", "category", "priority", "next_action"],
                        "additionalProperties": False,
                    },
                },
            },
        }

        with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
            try:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ProviderUnavailable(
                    f"Inference server returned HTTP {exc.response.status_code}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(
                    f"Inference server unreachable: {type(exc).__name__}"
                ) from exc

        try:
            response_json = response.json()
            raw_content = response_json["choices"][0]["message"]["content"]
            parsed = json.loads(_extract_json_text(raw_content))
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise InvalidModelOutput(
                "Model response was not valid JSON or was malformed"
            ) from exc

        if not isinstance(parsed, dict):
            raise InvalidModelOutput("Model response was not a JSON object")

        category = parsed.get("category")
        if not isinstance(category, str):
            raise InvalidModelOutput("Model category was missing or not a string")

        category = category.strip().lower()
        if category not in allowed_categories:
            raise InvalidModelOutput(f"Model returned an unallowed category: '{category}'")
        parsed["category"] = category  # store exactly what was validated

        try:
            return Analysis(**parsed)
        except (ValidationError, TypeError) as exc:
            raise InvalidModelOutput(
                "Model output failed length or field constraints"
            ) from exc