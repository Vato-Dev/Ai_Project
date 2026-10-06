import argparse
import os

from dotenv import load_dotenv

from ticket_app.compatible_provider import OpenAICompatibleProvider
from ticket_app.mock_provider import MockProvider
from ticket_app.models import Ticket
from ticket_app.service import TicketService


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Summarize a synthetic support ticket")
    parser.add_argument("--provider", choices=["mock", "local", "hosted"], default="mock")
    args = parser.parse_args()

    if args.provider == "mock":
        provider = MockProvider()
    else:
        explicit_base_url = os.getenv("LLM_BASE_URL", "").strip()
        if args.provider == "hosted" and not explicit_base_url:
            parser.error("Hosted mode requires an explicit LLM_BASE_URL")
        base_url = explicit_base_url or "http://localhost:1234/v1"
        model = os.getenv("LLM_MODEL", "").strip()
        if not model:
            parser.error("Set LLM_MODEL to a model ID shown by your server")
        if args.provider == "hosted" and not os.getenv("LLM_API_KEY"):
            parser.error("Hosted mode requires LLM_API_KEY")
        provider = OpenAICompatibleProvider(base_url, model, os.getenv("LLM_API_KEY", ""))

    ticket = Ticket(
        "T-104", "Cannot reset password", "The reset link expires immediately after I open it."
    )
    print(TicketService(provider).summarize(ticket))


if __name__ == "__main__":
    main()
