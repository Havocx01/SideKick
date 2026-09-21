# The hosted replay service: one image serving the API and the built frontend.
#
# It installs backend/requirements.txt only. numpy, pandas, scikit-learn and
# xgboost are absent on purpose: the hosted service answers from the committed
# evidence bundle and never trains, so carrying the training stack would waste
# most of a 512 MB instance on libraries that are never imported.

FROM node:20-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Relative API paths, because one service serves both.
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
# The bundle is the deployment payload: it is committed, so the hosted numbers are
# the ones a reviewer can read out of the repository.
COPY evidence ./evidence
COPY --from=frontend /build/dist ./static

# Render supplies PORT. Single worker: the work is serving one parsed JSON
# document, and a second worker would double the memory for no throughput gain.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
