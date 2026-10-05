from ticket_app.models import Ticket


class MockProvider:
    def summarize(self, ticket: Ticket) -> str:
        body = " ".join(ticket.body.split())
        return f"{ticket.subject.strip()}: {body[:160]}"[:220]
