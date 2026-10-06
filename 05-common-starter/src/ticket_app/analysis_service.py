from ticket_app.analysis_models import Analysis, Request
from ticket_app.analysis_provider import AnalysisProvider, InvalidModelOutput


class AnalysisService:
    def __init__(self, provider: AnalysisProvider, policy: dict):
        self.provider, self.policy = provider, policy

    def analyze(self, request: Request) -> Analysis:
        result = self.provider.analyze(request, self.policy)
        if result.category not in self.policy["categories"]:
            raise InvalidModelOutput("Category outside the scenario contract")
        return result
