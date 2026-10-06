from typing import Protocol

from ticket_app.models import Ticket


class SummaryProvider(Protocol):
    def summarize(self, ticket: Ticket) -> str:
        """Return a nonempty summary for a ticket."""
