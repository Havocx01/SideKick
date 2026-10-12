"""Compose feasible diagnostics from typed proposals and recorded capabilities.

The AI owns the investigative question and competing outcomes. The server owns
scope, controls, prerequisites and the executable diagnostic procedure. No check
is executed here. Availability means inspectable records, never a proven cause.
"""
import re
from typing import Literal

from pydantic import Field

from app.schemas import Strict

CheckKind = Literal["score_persistence", "preprocessing_audit", "sensor_quality",
                    "threshold_sensitivity", "recorded_attribution", "fold_variation"]


class CheckedProviderTest(Strict):
    # Not displayed: Sidekick labels the selected diagnostic from its contract.
    title: str = Field(min_length=1, max_length=120)
    model: str
    check_type: CheckKind
    focus: str = Field(min_length=1, max_length=260,
        description="Specific question this diagnostic should distinguish. Do not invent a procedure or assert a cause.")
    signal: Literal["scores_below_own_threshold", "crossings_without_warning", "preprocessing_contract_mismatch",
        "sensor_quality_anomaly", "attribution_concentration", "fold_outcome_concentration", "threshold_tradeoff"]
    observation_ids: list[str] = Field(min_length=1, max_length=4)


REQUIREMENTS = {
    "score_persistence": ("paired_histories",),
    "preprocessing_audit": ("preprocessing",),
    "sensor_quality": ("sensor_quality",),
    "threshold_sensitivity": (),
    "recorded_attribution": ("feature_contributions",),
    "fold_variation": ("equipment_and_folds",),
}
RECORD_LABELS = {
    "paired_histories": "matched clean/faulted development warning summaries for the cited patterns",
    "preprocessing": "the fitted preprocessing record for this model and development partition",
    "sensor_quality": "recorded original-dataset quality statistics for the cited channels",
    "feature_contributions": "matched recorded clean-prediction contributions for the cited patterns",
    "equipment_and_folds": "recorded development fold outcomes for the cited fault cases",
}
SIGNALS = {
    "scores_below_own_threshold": ("score_persistence", "Faulted scores remain below this model's own threshold in the useful window, compared with matched clean histories.",
        "This would favor investigating model-score response and recorded input handling; it would not identify a physical cause.",
        "This would shift attention to sustained crossings, alert persistence and warning timing; crossings alone do not establish a defect."),
    "crossings_without_warning": ("score_persistence", "Recorded scores cross this model's own threshold while the warning remains inactive in the useful window.",
        "Inspect crossing streaks against the recorded alert rules. Persistence may legitimately delay activation; this does not establish faulty logic.",
        "Inspect whether scores remain below the threshold or warnings occur outside the useful window; classify outcomes from matched records."),
    "preprocessing_contract_mismatch": ("preprocessing_audit", "The recorded fitted preprocessing differs from its declared feature contract for the affected channels.",
        "Investigate that mismatch and its effect on development inputs before attributing the warning shortfall to model scoring.",
        "A consistent contract does not establish adequate fault handling. Compare the transformed faulted inputs and this model's score response next."),
    "sensor_quality_anomaly": ("sensor_quality", "The recorded channel profile shows missingness, flat readings or unusual ranges relevant to the affected inputs.",
        "Prioritize a development trace check of input handling. Original-dataset quality alone cannot explain a faulted warning or justify tuning.",
        "A normal original-dataset profile does not rule out injected-fault sensitivity; inspect matched faulted development records."),
    "attribution_concentration": ("recorded_attribution", "Recorded contributions to a matched clean prediction concentrate on the affected channel features.",
        "Those features merit a separate development fault-response check. Clean contributions cannot explain a faulted prediction or physical cause.",
        "Do not assume the channel is irrelevant. Attribution scope is limited to the recorded clean prediction."),
    "fold_outcome_concentration": ("fold_variation", "Recorded warning shortfalls concentrate in particular equipment or folds among the cited cases.",
        "Inspect those development histories for shared data or protocol conditions; repeated fault cases are not independent samples.",
        "A dispersed shortfall would favor investigating a shared scoring or protocol issue rather than a single equipment subset."),
    "threshold_tradeoff": ("threshold_sensitivity", "A within-model development threshold change improves timely detection while increasing early-alarm burden, with other controls fixed.",
        "This would expose a detection-versus-alarm tradeoff, not establish a better model or permission to deploy.",
        "Inspect score response and persistence before treating threshold changes as a remedy; lack of improvement does not establish a cause."),
}
PROCEDURES = {
    "score_persistence": "Compare matched clean/faulted development scores against this model's own threshold, sustained crossings and active-warning transitions. Distinguish weak scores from persistence blocking a warning; classify late and missed warnings only from recorded outcomes.",
    "preprocessing_audit": "Audit the fitted development preprocessing record: missing-reading flags, median imputation or its recorded alternative, scaling and feature windows. Inspect recorded input handling; do not add flags or change the trained feature contract.",
    "sensor_quality": "Inspect missingness, flat readings and recorded ranges for the cited channels. This original dataset profile is descriptive, may include reserved equipment, and does not identify faulted-history readings or justify tuning.",
    "threshold_sensitivity": "Only after the required records are available, assess sensitivity around this model's own threshold on development histories. Hold the model, preprocessing and alert persistence fixed; measure timely, late and missed warnings AND early-alarm burden. Never synchronize numeric thresholds across models or tune on reserved histories.",
    "recorded_attribution": "Inspect matched recorded contributions to clean predictions only, using this model's attribution scale. Do not infer faulted feature importance, physical causes or neural intermediate layers from these records.",
    "fold_variation": "Compare recorded development outcomes across equipment and folds for the cited fault cases. Keep late and missed outcomes separate; repeated fault cases reuse equipment and are not independent samples.",
}


def diagnostic_contract(packet):
    from app.assistant.trace_reasoning import trace_options, explanation_anchor
    architectures = {"logistic_regression": "linear", "xgboost": "trees",
                     "xgboost_augmented": "trees", "age_baseline": "age_only"}
    return {"models": {row["alias"]: {"architecture": architectures.get(row["family"], "unknown"),
                "neural_layers": False, "score_scale": "model_specific_use_own_threshold",
                "sensor_inputs": row["family"] != "age_baseline"} for row in packet["models"]},
        "trace_bases": trace_options(packet),
        "explanation_anchor": explanation_anchor(packet),
        "check_types": {kind: {"procedure": PROCEDURES[kind],
            "required_records": [RECORD_LABELS[name] for name in REQUIREMENTS[kind]],
            "signals": [name for name, row in SIGNALS.items() if row[0] == kind]} for kind in PROCEDURES},
        "scope": "Inspect development evidence only. No new scoring, training or tuning is executed.",
        "threshold_records": "Complete development score traces, selected threshold, fixed alert rules and eligibility mask are required; compact paired summaries cannot support a threshold sweep.",
        "availability": "The server derives inspect_now or needs_evidence for the exact model and cited patterns. Never claim unavailable records were inspected."}


TITLES = {"score_persistence": "Inspect score response and warning persistence",
    "preprocessing_audit": "Audit recorded preprocessing", "sensor_quality": "Inspect recorded channel quality",
    "threshold_sensitivity": "Assess the detection and early-alarm tradeoff",
    "recorded_attribution": "Inspect recorded clean-prediction contributions",
    "fold_variation": "Inspect equipment and fold variation"}


def semantic_text(text):
    """Reject known invalid experiments/causal claims, including past paid failures."""
    # Explicit negation of an invalid comparison is fine; the provider cannot use
    # that caveat to conceal the same affirmative proposal in another sentence.
    for sentence in re.split(r"[.;\n]", text):
        if re.search(r"\bwarnings?\s+(?:(?:may|might|could|would|can|do|does|instead|briefly|still)\s+)*(?:(?:remain|stay|fall|are)\s+)?(?:below|above|cross\w*)\s+(?:(?:its|their|the|own|model-\d+)\s+){0,3}threshold\b", sentence, re.I) and not re.search(r"\bwarnings? scores?\b|\bwarning model(?:'s)? scores?\b", sentence, re.I):
            return False  # Thresholds apply to scores; warnings have an active state.
        shared = re.search(r"(?:synchroniz\w*|identical|same|shared|common|equal)\s+(?:numeric\s+)?threshold|threshold[^,]{0,50}(?:fixed or synchronized|synchroniz)", sentence, re.I)
        cross_model = len(set(re.findall(r"\bmodel-\d+\b", sentence, re.I))) > 1 or re.search(r"\b(?:both|across|between|compare)\b.*\bmodels\b|synchroniz", sentence, re.I)
        if shared and cross_model:
            if not re.search(r"\b(?:never|cannot|do not|don't|not a controlled)\b", sentence, re.I):
                return False
        if re.search(r"intermediate (?:neural )?layers?|hidden layers?|neural representations?", sentence, re.I):
            if not re.search(r"\b(?:no|never|cannot|do not|don't|not available)\b", sentence, re.I):
                return False
        if re.search(r"\b(?:primarily|mainly|definitely)\s+(?:due to|caused by|responsible)|\b(?:the|a) (?:root|physical) cause (?:is|was)\b", sentence, re.I):
            return False
        if re.search(r"\brobust (?:to|against|scores|performance|handling|detection)|\b(?:is|proven|demonstrates?) robust\b|near[- ]perfect timely warnings", sentence, re.I) and not re.search(r"\b(?:could|might|may|whether|not|cannot)\b", sentence, re.I):
            return False
        if re.search(r"\b(?:flaws?|mechanisms?|preprocessing|threshold settings|input handling)\b[^,]{0,100}\bexplain(?:s)?\b", sentence, re.I) and not re.search(r"\b(?:could|might|may|would|possible|suggesting|whether)\b", sentence, re.I):
            return False
        if not sentence.strip().endswith("?") and re.search(r"\bleading to (?:late|missed|delayed)|\b(?:shows?|demonstrates?)\b[^,]{0,100}\b(?:late|missed) warnings\b", sentence, re.I) and not re.search(r"\b(?:could|might|may|whether|if|suggesting)\b", sentence, re.I):
            return False
        if re.search(r"\bcoverage\b", sentence, re.I) and re.search(r"incomplete training|training incompleteness|insufficient training", sentence, re.I):
            if not re.search(r"\b(?:cannot establish|does not establish|not evidence|cannot infer)\b", sentence, re.I):
                return False
        if re.search(r"(?:missing|absent|unavailable)[^.]{0,70}(?:records?|information|metadata)[^.]{0,50}(?:implies?|suggests?|indicates?)", sentence, re.I) and re.search(r"deficien\w*|inadequate|poor|faulty|incomplete", sentence, re.I):
            return False
        if re.search(r"threshold (?:setting|stringency)[^.]{0,130}(?:despite sustained|scores cross thresholds persistently)", sentence, re.I):
            return False
        if re.search(r"(?:sensor|reading) quality|quality statistics", sentence, re.I) and re.search(r"\b(?:imply\w*|indicat\w*)\b[^.]{0,100}(?:do not cause|don't cause|not explain)", sentence, re.I):
            return False
        if re.search(r"sensor (?:signal )?quality", sentence, re.I) and re.search(r"explain(?:s)?\s+(?:the\s+)?(?:detection failure|faulted warning)|rule out (?:injected )?fault", sentence, re.I):
            return False
    return True


def compose_checks(provider, packet, observations, aliases):
    from app.assistant.deep import DeepVerificationError, validate_synthesis
    from app.assistant.schemas import DeepSynthesis, DeepTest, DeepHypothesis
    from app.assistant.trace_reasoning import grounded_title, trace_options
    if packet["partition"] != "out_of_fold":
        raise DeepVerificationError("scope")
    patterns = {row["id"]: row for row in packet["observations"]}
    support = packet["supporting_evidence"]
    if len(set(provider.gaps)) != len(provider.gaps):
        raise DeepVerificationError("duplicate")
    records = {row["observation_id"]: row for section in support.values() for row in section.get("items", [])}
    hypotheses = []
    partial = False
    for hypothesis in provider.hypotheses:
        mentioned = {alias.lower() for alias in re.findall(r"\bmodel-\d+\b",
            " ".join([hypothesis.explanation, hypothesis.alternative]), re.I)}
        cited_models = {patterns[id]["model"] for id in hypothesis.observation_ids if id in patterns}
        if not mentioned <= cited_models:
            raise DeepVerificationError("scope")
        if not hypothesis.title.strip() or not hypothesis.explanation.strip() or not hypothesis.alternative.strip():
            raise DeepVerificationError("format")
        # Each paragraph must remain tentative throughout. A may-prefixed opening
        # cannot authorize subsequent unsupported observations or causal assertions.
        unsafe_paragraph = False
        for text in (hypothesis.explanation, hypothesis.alternative):
            sentences = [sentence.strip() for sentence in re.split(r"[.!;\n]", text) if sentence.strip()]
            for sentence in sentences:
                cautious = re.search(r"\b(?:may|might|could|would|if|possible|perhaps|cannot|unknown|unavailable)\b|not recorded|does not establish|consistent with|competing explanation", sentence, re.I)
                # One general mechanism is framed as a hypothesis by Sidekick.
                # Additional factual sentences or asserted observed score behavior
                # require their own conditional framing, not a paragraph's prefix.
                actual = re.search(r"\b(?:observed|recorded|indicates?|demonstrates?|shows?)\b|\b(?:this|the) (?:low|modest|weak) scor\w*|\bmodel-\d+\b.*\b(?:does|produces?|has)\b", sentence, re.I)
                if not cautious and (len(sentences) > 1 or actual):
                    unsafe_paragraph = True
        if unsafe_paragraph:
            partial = True
            continue
        if hypothesis.explanation.strip().casefold() == hypothesis.alternative.strip().casefold():
            partial = True
            continue
        title = grounded_title(hypothesis, packet, patterns, records)
        if title is None:
            partial = True
            continue
        # Private provider trace choices never enter the public/stored report schema.
        hypotheses.append(DeepHypothesis(title=title, explanation="Possible explanation: " + hypothesis.explanation.strip(),
            alternative=hypothesis.alternative.strip(), observation_ids=list(dict.fromkeys(hypothesis.observation_ids))))
    raw_tests = []
    metadata = {}
    bases = trace_options(packet)
    for item in provider.next_tests:
        pattern_ids = {id for id in item.observation_ids if id in patterns}
        if not pattern_ids or any(patterns[id]["model"] != item.model for id in pattern_ids):
            raise DeepVerificationError("scope")
        for id in item.observation_ids:
            if id in patterns:
                continue
            row = records.get(id)
            if not row or row.get("model", item.model) != item.model or not pattern_ids.intersection(row.get("related_pattern_ids", [])):
                raise DeepVerificationError("scope")
        # Free text must refer to this model; mechanisms can compare models, but
        # each diagnostic has one score scale and one recorded model contract.
        text = item.focus  # Provider display titles are never interpreted or published.
        if any(alias.lower() != item.model for alias in re.findall(r"\bmodel-\d+\b", text, re.I)):
            raise DeepVerificationError("scope")
        if SIGNALS[item.signal][0] != item.check_type:
            raise DeepVerificationError("capability")
        cited_pairs = [row for row in support['paired_histories']['items'] if row['observation_id'] in item.observation_ids]
        retained_warning_check = (item.check_type == 'score_persistence' and bool(cited_pairs)
            and all(bases.get(row['observation_id']) == 'warning_retained' for row in cited_pairs))
        if retained_warning_check and (item.signal == 'scores_below_own_threshold'
                or re.search(r'\b(?:missed|missing|absent|disappear\w*)\s+warnings?\b|\bfail\w* to warn\b', text, re.I)):
            # These directly cited windows contain crossings AND active warnings.
            # Do not spend an engineer's time on a premise the records already refute.
            partial = True
            continue
        for sentence in re.split(r"[.;\n]", text):
            if re.search(r"\b(?:retrain\w*|add\w* (?:new |missing\w* )?(?:features|flags)|chang\w* (?:the )?imputation|adapt\w* thresholds?|recover\w* when missingness is represented)\b", sentence, re.I) and not re.search(r"\b(?:never|do not|don't|without|no)\b", sentence, re.I):
                raise DeepVerificationError("capability")
        if packet["diagnostic_contract"]["models"][item.model]["architecture"] == "age_only" and item.check_type in ("sensor_quality", "preprocessing_audit", "recorded_attribution"):
            raise DeepVerificationError("capability")
        prerequisites = []
        for section in REQUIREMENTS[item.check_type]:
            covered = {id for row in support[section]["items"] if row.get("model", item.model) == item.model
                       and (section != 'paired_histories' or row.get('score_warning_trace', {}).get('status') == 'available')
                       for id in row.get("related_pattern_ids", [])}
            if not pattern_ids <= covered:
                missing = pattern_ids - covered
                prerequisites.append("Obtain " + RECORD_LABELS[section] + (
                    f" for {len(missing)} remaining cited patterns; available examples cover only part of this check." if covered.intersection(pattern_ids) else "."))
        if item.check_type == 'score_persistence':
            relevant = [row for row in support['paired_histories']['items'] if row.get('model') == item.model
                and pattern_ids.intersection(row.get('related_pattern_ids', []))
                and row.get('score_warning_trace', {}).get('status') == 'available']
            if any(not row['score_warning_trace']['useful_window_complete'] for row in relevant):
                prerequisites.append('Obtain the missing useful-window cycles; stored excerpts with incomplete source histories cannot establish the full crossing sequence.')
        if item.check_type == "threshold_sensitivity":
            prerequisites.append("Obtain complete development score traces, the selected threshold, fixed alert rules and the early-alarm eligibility mask; compact summaries are insufficient.")
        if item.check_type in ("score_persistence", "threshold_sensitivity"):
            rules = support["paired_histories"].get("warning_rules", {})
            if not all(type(rules.get(name)) is int and rules[name] > 0 for name in ("alert_on_consecutive", "alert_off_consecutive")):
                prerequisites.append("Obtain recorded alert opening and closing persistence rules.")
        controls = ["Keep the model fixed; use development evidence only.", "Keep the recorded preprocessing and alert rules fixed; no training or validation job is run."]
        if item.check_type == "sensor_quality":
            controls[0] = "Inspect the original dataset profile descriptively; it may include reserved equipment. Do not use this profile for tuning."
        procedure = PROCEDURES[item.check_type]
        expected, present, absent = SIGNALS[item.signal][1:]
        if retained_warning_check:
            paired_warning = ("Both cited histories retain warnings" if all(row['clean']['useful_window']['active_cycles'] > 0 for row in cited_pairs)
                else "The cited faulted histories retain warnings; inspect their clean counterparts' recorded warning states before comparing timing")
            procedure = f"Compare matched clean/faulted development crossing streaks, prior warning state and recorded warning onset/lead using this model's own threshold and fixed opening/closing rules. {paired_warning}; inspect timing differences without treating retained warnings as missing or changing the model."
            expected = "The matched faulted history reaches the recorded opening streak later than the clean history while retaining an active warning."
            present = "This would favor investigating changes in score-crossing timing and recorded input response; it would not identify a physical cause or establish a remedy."
            absent = "Inspect prior warning state and how recorded onset/lead is assigned before attributing the difference to scoring; retained warnings do not establish unchanged timing."
        if any(patterns[id]["kind"] == "dropout" for id in pattern_ids) and item.check_type == "score_persistence":
            procedure += " Review recorded missing-reading flags and median imputation or its recorded alternative; unavailable fitted preprocessing must be obtained first."
            covered = {id for row in support["preprocessing"]["items"] if row.get("model") == item.model for id in row.get("related_pattern_ids", [])}
            if not pattern_ids <= covered:
                prerequisites.append("Obtain " + RECORD_LABELS["preprocessing"] + ".")
        title = TITLES[item.check_type] + " · " + item.model
        if title in metadata:
            raise DeepVerificationError("duplicate")
        metadata[title] = {"model": item.model, "check_type": item.check_type,
            "readiness": "needs_evidence" if prerequisites else "inspect_now",
            "prerequisites": prerequisites, "controls": controls, "procedure": procedure,
            "focus": item.focus, "expected_signal": expected,
            "interpretation": "If observed: " + present + "\nIf absent: " + absent}
        # Validate the model's question. Signals and branches are server-owned.
        raw_tests.append(DeepTest(title=title, observation_ids=list(dict.fromkeys(item.observation_ids)), procedure=item.focus,
            expected_signal="The selected recorded signal needs checking.",
            interpretation="The recorded signal would guide the proposed investigation."))
    # Review independently generated paragraphs/questions. Do not invent an
    # explanation to accompany an otherwise feasible diagnostic question.
    class DiagnosticSynthesis(DeepSynthesis):
        hypotheses: list[DeepHypothesis] = Field(min_length=0, max_length=3)
    verified = DiagnosticSynthesis(summary="Possible explanations and checks for the inspected fault patterns.",
        hypotheses=[], next_tests=raw_tests, gaps=list(provider.gaps))
    for field, values in (("hypotheses", hypotheses), ("next_tests", raw_tests), ("gaps", provider.gaps)):
        retained = []
        for item in values:
            isolated = verified.model_copy(update={"hypotheses": [], "next_tests": [], "gaps": [], field: [item]})
            try:
                validate_synthesis(isolated, observations, aliases, fault_kinds={row["kind"] for row in patterns.values()})
            except DeepVerificationError as error:
                if error.code != "claims":
                    raise
                partial = True
            else:
                retained.append(item)
        setattr(verified, field, retained)
    if not verified.next_tests or not verified.gaps:
        raise DeepVerificationError("claims")
    for item in verified.next_tests:
        info = metadata[item.title]
        item.procedure = info.pop("procedure")
        for field, value in info.items():
            setattr(item, field, value)
    return verified, partial
