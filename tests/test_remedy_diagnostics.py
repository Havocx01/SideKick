from copy import deepcopy
import json

import pytest

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.profiles import loadPolicy
from app.investigator.findings import FindingCriterion
from scripts import diagnose_remedy as diagnostics
from test_compound_faults import component, fitted as fitted  # noqa: F401

LR = 'logistic_regression/lr-probe'
PAIR = {'components': [component('vibration_rms', kind='stuck', onset_before_failure=60),
    component('oil_particles', kind='stuck', onset_before_failure=60)]}


def test_cases_come_only_from_development_experiments_and_reductions():
    reduced = deepcopy(PAIR)
    reduced['components'][0]['onset_before_failure'] = 30
    evidence = {'experiments': [{'scenario': PAIR}, {'scenario': PAIR}], 'reductions': [{'final': reduced}],
        'validations': [{'cases': [{'scenario': {'components': [component('unknown-fresh-channel')]}}]}]}
    assert len(diagnostics.caseSuite(evidence)) == 2
    with pytest.raises(ValueError, match='development cases'):
        diagnostics.caseSuite({'experiments': [], 'validations': evidence['validations']})


def test_refit_diagnostic_reproduces_the_failure_without_fresh_or_reserved_data(fitted, monkeypatch):
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, loadPolicy('synthetic-rotating-v1', max_evaluations=128))
    training = engine.snapshot()
    expected = set(training.splits.development)
    before = engine.context_fingerprint
    fitFinal, train = diagnostics.fit_final, diagnostics.train_development
    fits = []

    def checkedFinal(dataset, splits, *args, **kwargs):
        assert set(dataset.equipment_ids) == expected
        assert not set(dataset.equipment_ids) & set(training.splits.holdout)
        fits.append('refit')
        return fitFinal(dataset, splits, *args, **kwargs)

    def checkedTrain(dataset, *args, **kwargs):
        assert set(dataset.equipment_ids) == expected
        assert set(kwargs['splits'].development) == expected
        fits.append('resplit')
        return train(dataset, *args, **kwargs)

    monkeypatch.setattr(diagnostics, 'fit_final', checkedFinal)
    monkeypatch.setattr(diagnostics, 'train_development', checkedTrain)
    cases = diagnostics.caseSuite({'experiments': [{'scenario': PAIR}]})
    result = diagnostics.diagnose(engine, cases, FindingCriterion(candidate=LR), thresholds=(.95, .5), seeds=(20261033,))
    rows = [row for row in result['results'] if row['threshold'] == .5]
    original = next(row for row in rows if row['fit'] == 'original_grouped_oof')
    refit = next(row for row in rows if row['fit'] == 'all_development_refit_in_sample_diagnostic')
    assert original['lostUsefulWarnings'] == 0
    assert refit['lostUsefulWarnings'] > 0 and refit['status'] == 'measured_failure'
    assert result['proposedThreshold'] is None
    assert fits == ['refit', 'resplit'] and engine.context_fingerprint == before
    assert result['developmentHistories'] == 22 and result['independentValidation'] is False


def test_proposal_requires_every_fit_and_case_to_meet_limits():
    rows = [{'threshold': .5, 'meetsDevelopmentLimits': True}, {'threshold': .5, 'meetsDevelopmentLimits': False},
        {'threshold': .3, 'meetsDevelopmentLimits': True}]
    assert diagnostics.chooseThreshold(rows, (.5, .3)) == .3
    assert diagnostics.chooseThreshold(rows, (.5,)) is None
    assert diagnostics.chooseThreshold([], (.5,)) is None


def test_lower_candidate_must_pass_development_refit_and_machine_caps(fitted):
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, loadPolicy('synthetic-rotating-v1', max_evaluations=128))
    cases = diagnostics.caseSuite({'experiments': [{'scenario': PAIR}]})
    result = diagnostics.diagnose(engine, cases, FindingCriterion(candidate=LR), thresholds=(.5, .2), seeds=(20261033,))
    assert result['proposedThreshold'] == .2
    proposed = [row for row in result['results'] if row['threshold'] == .2]
    assert all(row['lostUsefulWarnings'] == 0 and row['meetsDevelopmentLimits'] for row in proposed)
    assert all(row['cleanWorstBurden'] <= .05 and row['faultedWorstBurden'] <= .05 for row in proposed)


def test_partial_cases_remain_diagnostic_but_cannot_propose_a_threshold(fitted):
    policy = loadPolicy('synthetic-rotating-v1', max_evaluations=128)
    onset = int(fitted.dataset.frame.groupby('equipment_id').rul.max().min()) + 1
    case = {'components': [component('temp_bearing', kind='stuck', onset_before_failure=onset)]}
    cases = diagnostics.caseSuite({'experiments': [{'scenario': case}]})
    rows = diagnostics.thresholdRows(fitted, cases, FindingCriterion(candidate=LR), policy, (.2,), 'partial_case')
    assert rows[0]['status'] == 'no_measured_failure' and 0 < rows[0]['evaluated'] < 22
    assert diagnostics.chooseThreshold(rows, (.2,)) is None


def test_cli_rejects_evidence_from_another_context(fitted, tmp_path, monkeypatch):
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, loadPolicy('synthetic-rotating-v1', max_evaluations=128))
    monkeypatch.setattr(diagnostics, 'load_trusted_context', lambda *args, **kwargs: engine)
    evidence = tmp_path / 'evidence.json'
    evidence.write_text(json.dumps({'context': {'fingerprint': 'unrelated', 'policyFingerprint': engine.policy.fingerprint}}))
    with pytest.raises(ValueError, match='different fixed context'):
        diagnostics.main(['--context', str(tmp_path), '--trust-local-artifact', '--evidence', str(evidence), '--output', str(tmp_path / 'new')])


def test_cli_preserves_existing_results_and_requires_trusted_artifacts(tmp_path):
    evidence = tmp_path / 'evidence.json'
    evidence.write_text(json.dumps({'criterion': {'candidate': LR}, 'experiments': [{'scenario': PAIR}]}))
    output = tmp_path / 'existing'
    output.mkdir()
    with pytest.raises(FileExistsError):
        diagnostics.main(['--context', str(tmp_path), '--evidence', str(evidence), '--output', str(output)])
    with pytest.raises(ValueError, match='trust'):
        diagnostics.main(['--context', str(tmp_path), '--evidence', str(evidence), '--output', str(tmp_path / 'new')])
