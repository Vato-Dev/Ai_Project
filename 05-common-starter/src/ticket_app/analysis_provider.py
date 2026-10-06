import json
import httpx
from typing import Protocol
from ticket_app.analysis_models import Analysis, Request

class ProviderUnavailable(RuntimeError):
    pass

class InvalidModelOutput(RuntimeError):
    pass

class AnalysisProvider(Protocol):
    def analyze(self, request: Request, policy: dict) -> Analysis: ...

class MockAnalysisProvider:
    def analyze(self, request: Request, policy: dict) -> Analysis:
        return Analysis(
            summary=f"{request.subject}: {request.text}"[:240],
            category=policy["categories"][0],
            priority="medium",
            next_action="Ask a reviewer to route the request.",
        )

class LocalAnalysisProvider:
    def __init__(self, base_url, model, timeout=60, key="", transport=None):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.key = key
        self.transport = transport

    def analyze(self, request: Request, policy: dict) -> Analysis:
        allowed_categories = policy.get("categories", ["account", "network", "software"])
        
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
                            "category": {"type": "string", "enum": list(allowed_categories)},
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
                raise ProviderUnavailable(f"Inference server returned HTTP {exc.response.status_code}") from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f"Inference server unreachable: {type(exc).__name__}") from exc

        try:
            response_json = response.json()
            raw_content = response_json["choices"][0]["message"]["content"].strip()
            
            if raw_content.startswith("```"):
                raw_content = raw_content.strip("`").replace("json", "", 1).strip()
                
            parsed_analysis = json.loads(raw_content)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise InvalidModelOutput("Model response was not valid JSON or text was malformed") from exc

        model_category = parsed_analysis.get("category", "").strip().lower()
        if model_category not in allowed_categories:
            raise InvalidModelOutput(f"Model returned an unallowed category: '{model_category}'")

        try:
            return Analysis(**parsed_analysis)
        except Exception as exc:
            raise InvalidModelOutput("Model output failed Pydantic string length or layout constraints") from exc
