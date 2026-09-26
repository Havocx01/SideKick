# Include training dependencies for local experiments.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY backend/requirements.txt backend/requirements-train.txt ./
RUN pip install --no-cache-dir -r requirements-train.txt

COPY backend/app ./app
COPY scripts ./scripts
COPY pyproject.toml ./

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
