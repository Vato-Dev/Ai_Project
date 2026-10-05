from dataclasses import dataclass


@dataclass(frozen=True)
class Ticket:
    identifier: str
    subject: str
    body: str
