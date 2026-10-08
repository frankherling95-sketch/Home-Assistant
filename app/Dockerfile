# Eén image voor de app (Cloud Run-service) en de verzamelaar (Cloud Run-job).
#   service: uvicorn (standaard CMD)
#   job:     python -m thuis.verzamel
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Eerst alleen de afhankelijkheden: die laag blijft in de cache zolang pyproject.toml gelijk blijft.
COPY pyproject.toml ./
RUN mkdir thuis && touch thuis/__init__.py \
    && pip install ".[gcp,kia]" \
    && pip uninstall -y thuis && rm -rf thuis build ./*.egg-info

COPY thuis ./thuis
RUN pip install --no-deps . && rm -rf build ./*.egg-info
COPY web ./web

RUN useradd --create-home --uid 10001 thuis
USER thuis

ENV THUIS_WEB=/app/web \
    THUIS_OPSLAG=bigquery \
    PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn thuis.api:app --host 0.0.0.0 --port ${PORT}"]
