"""Offline admission covers every recorded model and pair without paid requests."""
import asyncio
import itertools
import json
from pathlib import Path
from types import SimpleNamespace
from provider_helpers import chatCompletion

from app.assistant import deep
from app.assistant.investigation import EvidenceTools
from app.assistant.schemas import AnalysisRequest
from app.config import get_settings
from app.evidence.bundle import load_bundle
from app.evidence.supplement import attach_replays


def test_all_recorded_models_and_pairs_missing_evidence_and_uploaded_context(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'evidence/bundle.json'
    bundle = load_bundle(path)
    attach_replays(bundle, path)
    before = bundle.model_dump_json()
    models = [f'{row.candidate.value}/{row.config_id}' for row in bundle.development_selection.ranked]
    assert len(models) == 10
    contexts = [AnalysisRequest(task='deep', candidates=[model]) for model in models]
    contexts += [AnalysisRequest(task='deep', candidates=list(pair)) for pair in itertools.combinations(models, 2)]
    contexts += [AnalysisRequest(task='deep', candidates=[models[0]], experiment_id='fixture-upload',
        engineer_context={'equipment_type': 'Fixture pump', 'decision': 'Review warning timing'},
        investigation_focus='Compare score timing with warning onset.')]
    requests = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs['max_retries'] == 0
            self.chat = SimpleNamespace(completions=self)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return None
        async def create(self, **kwargs):
            requests.append(kwargs)
            packet = json.loads(kwargs['messages'][-1]['content'])
            anchor = packet['diagnostic_contract']['explanation_anchor']
            focus = max(packet['observations'], key=lambda row: row['failed_cases'])
            ids = anchor['observation_ids'] if anchor else [focus['id']]
            result = {'hypotheses': [], 'gaps': ['Selected records do not establish physical causes or field performance.'],
                'next_tests': [{'title': 'Inspect recorded response', 'model': anchor['model'] if anchor else focus['model'],
                    'check_type': 'score_persistence', 'signal': anchor['recommended_signal'] if anchor else 'crossings_without_warning',
                    'focus': 'Inspect matched score-crossing timing and recorded warning onset.', 'observation_ids': ids}]}
            return chatCompletion(result)

    monkeypatch.setattr(deep, 'AsyncOpenAI', Client)
    settings = get_settings()
    monkeypatch.setattr(settings, 'nebius_api_key', 'offline-mock-only')
    async def run():
        for context in contexts:
            scoped = bundle.model_copy(deep=True) if context.experiment_id else bundle
            if context.experiment_id:
                scoped.experiment_id = context.experiment_id
            tools = EvidenceTools(scoped, context)
            result = await deep.investigate_deep(tools, settings)
            assert result.deep_report and result.deep_report.next_tests
            assert result.deep_report.explanation_status == 'abstained'
            assert result.findings == tools.result.findings
            assert result.deep_report.request_count == 1
            assert all(source.partition == context.partition and source.candidate in context.candidates for source in result.sources)
        missing = bundle.model_copy(deep=True)
        missing.replay_series = []
        result = await deep.investigate_deep(EvidenceTools(missing, contexts[0]), settings)
        assert result.deep_report.next_tests[0].readiness == 'needs_evidence'
    asyncio.run(run())
    assert len(requests) == 57
    assert bundle.model_dump_json() == before
