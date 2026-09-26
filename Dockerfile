# Replay needs only serving dependencies; training runs locally.

FROM node:20-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SIDEKICK_MODE=replay \
    SIDEKICK_STATIC_DIR=/app/static \
    SIDEKICK_BUNDLE_PATH=/app/evidence/bundle.json

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY evidence ./evidence
COPY --from=frontend /build/dist ./static

# One worker avoids duplicating the parsed evidence bundle in memory.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
