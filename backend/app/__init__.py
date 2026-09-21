"""Sidekick: sensor-fault-aware model selection for predictive maintenance.

Package layout
--------------
``config``    Frozen experiment definition plus runtime settings.
``schemas``   Pydantic contract shared by the pipeline, the API and the frontend.
``data``      Loading, the upload contract, profiling, synthetic fallback data.
``features``  Causal windowed features with a single-sensor rebuild path.
``models``    Splits, candidates, cross-validated training, thresholds.
``faults``    Sensor-fault specification, injection and scenario matrix.
``scoring``   Alert episodes, operational measures, selection rule.
``evidence``  Run records, optional MLflow bridge, replay bundle export.
``copilot``   Tool registry, numeric-claim verification, bounded agent loop.
``api``       FastAPI surface.
"""

__version__ = "0.1.0"
