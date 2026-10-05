import json
import logging
import os
import time
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from ticket_app.analysis_models import Record, Request
from ticket_app.analysis_provider import (
    InvalidModelOutput,
    LocalAnalysisProvider,
    MockAnalysisProvider,
    ProviderUnavailable,
)
from ticket_app.analysis_service import AnalysisService
from ticket_app.storage import Store

logger = logging.getLogger("ticket_app")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def create_app(provider=None, policy=None, db_path=None):
    load_dotenv()
    provider_name = os.getenv("LLM_PROVIDER", "mock")
    scenario_id = os.getenv("SCENARIO_ID", "g00")
    if policy is None:
        policy = json.loads(Path(f"scenarios/{scenario_id}.json").read_text())
    if provider is None:
        if provider_name == "mock":
            provider = MockAnalysisProvider()
        elif provider_name == "local":
            key = os.getenv("LLM_API_KEY", "")
            key_file = os.getenv("LLM_API_KEY_FILE", "")
            if key_file:
                key = Path(key_file).read_text().strip()
            provider = LocalAnalysisProvider(
                os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"),
                os.getenv("LLM_MODEL", ""),
                float(os.getenv("LLM_TIMEOUT", "60")),
                key,
            )
        else:
            raise ValueError("LLM_PROVIDER must be mock or local")
    service = AnalysisService(provider, policy)
    store = Store(db_path or os.getenv("DB_PATH", "./data/analyses.db"))
    app = FastAPI(title="Support Request Copilot", version="0.2.0")

    @app.get("/health")
    def health():
        return {"status": "ok", "scenario": policy["id"], "provider": provider_name}

    @app.post("/api/analyze", response_model=Record)
    def analyze(request: Request):
        request_id, start = str(uuid4()), time.perf_counter()
        try:
            analysis = service.analyze(request)
        except ProviderUnavailable as exc:
            raise HTTPException(503, detail=str(exc)) from exc
        except InvalidModelOutput as exc:
            raise HTTPException(502, detail=str(exc)) from exc
        record = Record(
            id=request_id, scenario=policy["id"], provider=provider_name, analysis=analysis
        )
        store.save(record)
        logger.info(
            json.dumps(
                {
                    "event": "analysis_completed",
                    "id": request_id,
                    "provider": provider_name,
                    "elapsed_ms": round((time.perf_counter() - start) * 1000),
                }
            )
        )
        return record

    @app.get("/api/history", response_model=list[Record])
    def history():
        return store.recent()

    return app
