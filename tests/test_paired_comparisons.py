from types import SimpleNamespace

import numpy as np
from app.config import EXPERIMENT
from app.scoring.metrics import compact_scoring, score_engine
from app.scoring.paired import compare


def test_paired_bootstrap_uses_equipment_and_is_reproducible():
    matrix = {}
    for candidate in ("first", "second"):
        for scenario in ("a", "b"):
            matrix[candidate, scenario] = [compact_scoring(score_engine(str(i), np.full(100, int(candidate == "second")),
                np.arange(1, 101), np.arange(100, 0, -1), .5)) for i in range(4)]
    result = SimpleNamespace(matrix=SimpleNamespace(equipment_metrics=matrix), required_scenario_ids={"a", "b"},
        training=SimpleNamespace(config=EXPERIMENT, splits=SimpleNamespace(development=[str(i) for i in range(4)])))
    first = compare(result, "first", "second", "selected")
    second = compare(result, "first", "second", "selected")
    assert first.model_dump() == second.model_dump()
    assert first.detection_delta == 1
    assert first.detection_interval == [1, 1]
    assert first.engines == 4 and first.scenarios == 2 and first.resamples == 1000
    matrix["second", "b"].pop()
    assert compare(result, "first", "second", "selected") is None
