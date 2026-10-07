FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-deps .

COPY scenarios ./scenarios
COPY ui ./ui

RUN useradd --create-home --uid 10001 app \
    && mkdir /data && chown app:app /data
ENV DB_PATH=/data/analyses.db LLM_PROVIDER=mock SCENARIO_ID=g01
USER app
EXPOSE 8000 8501

CMD ["uvicorn", "ticket_app.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
