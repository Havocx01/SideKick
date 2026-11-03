# The replay target stays small; the default demo target adds sample training.

FROM node:20-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.11.9-slim-bookworm AS replay

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SIDEKICK_MODE=replay \
    SIDEKICK_STATIC_DIR=/app/static \
    SIDEKICK_BUNDLE_PATH=/app/evidence/bundle.json

WORKDIR /app

COPY backend/requirements.txt docker/runtime-constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c runtime-constraints.txt

COPY backend/app ./app
COPY evidence ./evidence
COPY --from=frontend /build/dist ./static

# One worker avoids duplicating the parsed evidence bundle in memory.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]

FROM replay AS demo

ENV SIDEKICK_MODE=demo \
    SIDEKICK_ARTIFACTS_DIR=/app/artifacts \
    SIDEKICK_DATA_DIR=/app/data \
    SIDEKICK_MLFLOW=0 \
    SIDEKICK_TRAIN_THREADS=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements-train.txt ./
RUN pip install --no-cache-dir -r requirements-train.txt -c runtime-constraints.txt \
    && useradd --create-home sidekick \
    && mkdir -p /app/artifacts /app/data \
    && chown -R sidekick:sidekick /app/artifacts /app/data
USER sidekick

FROM demo AS hosted

USER root
RUN mkdir -p /workspace/artifacts /workspace/data && chown -R sidekick:sidekick /workspace
COPY scripts/check_hosted_config.py ./scripts/
ENV SIDEKICK_MODE=full \
    SIDEKICK_ARTIFACTS_DIR=/workspace/artifacts \
    SIDEKICK_DATA_DIR=/workspace/data \
    SIDEKICK_ASSISTANT_LIVE_ENABLED=0
USER sidekick
CMD ["sh", "-c", "python scripts/check_hosted_config.py && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers"]

# Keep ordinary builds on the restricted public demo.
FROM demo AS public
