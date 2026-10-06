from ticket_app.models import Ticket
from ticket_app.provider import SummaryProvider


class TicketService:
    def __init__(self, provider: SummaryProvider) -> None:
        self.provider = provider

    def summarize(self, ticket: Ticket) -> str:
        if not ticket.body.strip():
            raise ValueError("Ticket body must not be blank")
        summary = self.provider.summarize(ticket).strip()
        if not summary:
            raise ValueError("Provider returned an empty summary")
        return summary
