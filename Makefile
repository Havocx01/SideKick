# Local tasks. See tasks.ps1 for the PowerShell equivalents.

PY ?= python
VENV ?= .venv
ifeq ($(OS),Windows_NT)
	BIN := $(VENV)/Scripts
else
	BIN := $(VENV)/bin
endif

.DEFAULT_GOAL := help
.PHONY: help setup setup-full data pipeline pipeline-fast bundle api web build types docker

help: ## List the available tasks
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

setup: ## Create the virtualenv and install the app and training dependencies
	$(PY) -m venv $(VENV)
	$(BIN)/python -m pip install -U pip
	$(BIN)/pip install -r backend/requirements-train.txt

setup-full: setup ## Add SHAP, MLflow and matplotlib (optional, heavier)
	$(BIN)/pip install -r backend/requirements-full.txt

data: ## Download the NASA C-MAPSS dataset into data/cmapss
	$(BIN)/python scripts/fetch_data.py

pipeline: ## Full evaluation on FD001, then write the evidence bundle
	$(BIN)/python scripts/run_pipeline.py

pipeline-fast: ## Same pipeline with fewer folds and the required faults only
	$(BIN)/python scripts/run_pipeline.py --fast --required-only

bundle: ## Rebuild evidence/bundle.json from the recorded runs
	$(BIN)/python scripts/export_bundle.py

api: ## Serve the API with reload on http://127.0.0.1:8000
	$(BIN)/uvicorn app.main:app --reload --app-dir backend

web: ## Serve the frontend with hot reload on http://127.0.0.1:5173
	cd frontend && npm run dev

build: types ## Build the frontend into frontend/dist
	cd frontend && npm ci --no-audit --no-fund && npm run build

types: ## Regenerate frontend types from the Pydantic schemas
	$(BIN)/python scripts/generate_types.py

docker: ## Build the deployed replay image locally
	docker build -t sidekick:local .
