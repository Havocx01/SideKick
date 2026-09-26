"""Run records, the replay bundle and the optional MLflow mirror."""

from app.evidence.bundle import LIMITATIONS, build_bundle, load_bundle, write_bundle
from app.evidence.store import EvidenceStore, compare_runs, git_commit
from app.evidence.tracking import mirror_run

__all__ = [
    "LIMITATIONS",
    "EvidenceStore",
    "build_bundle",
    "build_series",
    "choose_replay_engines",
    "compare_runs",
    "git_commit",
    "load_bundle",
    "mirror_run",
    "write_bundle",
]


def __getattr__(name):
    if name in {"build_series", "choose_replay_engines"}:
        from app.evidence import replay

        return getattr(replay, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
