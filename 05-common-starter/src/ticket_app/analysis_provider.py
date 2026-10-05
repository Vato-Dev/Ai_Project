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
        self.base_url, self.model, self.timeout = base_url, model, timeout
        self.key, self.transport = key, transport

    def analyze(self, request: Request, policy: dict) -> Analysis:
        # Implement the local JSON-output adapter in Phase 2.
        raise ProviderUnavailable("Complete the local analysis adapter during the project")
