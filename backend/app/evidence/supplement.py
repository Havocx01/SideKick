"""Optional verified replays supplement a historical bundle; its metrics stay intact."""

import hashlib
import json

from app.schemas import ReplaySeries


def attach_replays(bundle, bundle_path):
    path = bundle_path.parent / "replays-v1.5.json"
    if not path.is_file():
        return
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw["original_bundle_sha256"] != hashlib.sha256(bundle_path.read_bytes()).hexdigest():
        return
    existing = {(s.candidate, s.config_id, s.equipment_id, s.scenario_id, s.partition) for s in bundle.replay_series}
    for record in raw["replay_series"]:
        entry = ReplaySeries.model_validate(record)
        key = (entry.candidate, entry.config_id, entry.equipment_id, entry.scenario_id, entry.partition)
        if key not in existing:
            bundle.replay_series.append(entry)
            existing.add(key)
