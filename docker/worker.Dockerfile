# Finite fault-evaluation worker: one manifest in, one result artifact out.
# Context packages only load with the coordinator's exact Python and scoring versions, so build with:
#   python scripts/worker_constraints.py
#   docker build -f docker/worker.Dockerfile --build-arg PYTHON=<printed version> -t sidekick-worker .
ARG PYTHON=3.11
FROM python:${PYTHON}-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements-train.txt ./backend/
COPY docker/worker-constraints.txt ./docker/
RUN pip install --no-cache-dir -r backend/requirements-train.txt -c docker/worker-constraints.txt \
    && useradd --create-home sidekick

# The worker's source digest must match the coordinator's, so copy the same backend sources unchanged.
COPY backend/app ./backend/app
COPY scripts/run_fault_job.py ./scripts/

USER sidekick
ENTRYPOINT ["python", "scripts/run_fault_job.py"]
