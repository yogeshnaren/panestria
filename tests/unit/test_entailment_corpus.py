"""Dataset provenance and SYNTHETIC metric checks, not actual model calibration."""

import hashlib
import json
from pathlib import Path

import pytest

from panestria.verification.entailment import (
    SNLI_REVISION,
    SNLI_SUBSET_SHA256,
    EntailmentPrediction,
    load_snli_subset,
    score_predictions,
)

DATA = Path(__file__).resolve().parents[1] / "fixtures/research/snli-v1"


@pytest.fixture
def corpus():
    return load_snli_subset(DATA / "corpus.json")


def test_pinned_human_corpus_has_balanced_disjoint_source_groups(corpus):
    assert len(corpus.folds.calibration) == len(corpus.folds.qualification) == 36
    all_cases = (*corpus.folds.calibration, *corpus.folds.qualification)
    assert len({c.case_id for c in all_cases}) == len({c.premise_group_sha256 for c in all_cases}) == 72
    for cases in (corpus.folds.calibration, corpus.folds.qualification):
        assert {
            label: sum(c.expected == label for c in cases) for label in ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT")
        } == {"SUPPORTED": 12, "CONTRADICTED": 12, "INSUFFICIENT": 12}
    assert corpus.purpose == "evaluation_fixture_only_no_training_authorization"


def test_every_selected_label_and_unchanged_text_resolves_to_pinned_original_rows(corpus):
    provenance = json.loads((DATA / "provenance.json").read_text())
    assert provenance["revision"] == SNLI_REVISION and provenance["corpus_sha256"] == SNLI_SUBSET_SHA256
    assert provenance["license"] == "CC-BY-SA-4.0"
    originals = {}
    for source in provenance["upstream"]:
        raw = (DATA / source["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == source["sha256"]
        assert source["x_revision"] == SNLI_REVISION
        data = json.loads(raw)
        assert data["features"][2]["type"]["names"] == ["entailment", "neutral", "contradiction"]
        split = "validation" if "validation" in source["path"] else "test"
        for row in data["rows"]:
            originals[(split, row["row_idx"])] = row
    for case in (*corpus.folds.calibration, *corpus.folds.qualification):
        original = originals[(case.source_split, case.source_row_index)]
        assert not original["truncated_cells"] and original["row"]["label"] in (0, 1, 2)
        assert (case.premise, case.hypothesis, case.source_label) == (
            original["row"]["premise"],
            original["row"]["hypothesis"],
            original["row"]["label"],
        )
    assert "Bowman" in (DATA / "ATTRIBUTION.md").read_text()


def test_model_input_projection_has_no_gold_or_source_index_leakage(corpus):
    inputs = corpus.model_inputs("qualification")
    assert all(set(item.model_dump()) == {"case_id", "premise", "hypothesis"} for item in inputs)
    assert [(p.case_id, p.premise, p.hypothesis) for p in inputs] == [
        (c.case_id, c.premise, c.hypothesis) for c in corpus.folds.qualification
    ]


def test_synthetic_perfect_predictions_check_metrics_only_not_a_model_pass(corpus):
    synthetic = tuple(EntailmentPrediction(case_id=c.case_id, verdict=c.expected) for c in corpus.folds.calibration)
    score = score_predictions(corpus, "calibration", synthetic)
    assert (score.total, score.answered, score.correct) == (36, 36, 36)
    assert score.coverage == score.accuracy_on_answered == score.supported_precision == 1
    assert score.false_supported_count == 0 and score.authority == "PREDICTION_METRICS_ONLY"
    assert sum(cell.count for cell in score.confusion) == 36
    assert not hasattr(score, "release_pass") and not hasattr(score, "model_qualified")


def test_all_abstentions_keep_undefined_precision_and_answered_accuracy_unknown(corpus):
    synthetic = tuple(EntailmentPrediction(case_id=c.case_id, verdict="UNKNOWN") for c in corpus.folds.qualification)
    score = score_predictions(corpus, "qualification", synthetic)
    assert score.coverage == score.correct_fraction == 0 and score.answered == 0
    assert score.accuracy_on_answered is None and score.supported_precision is None
    assert score.supported_predictions == score.false_supported_count == 0


def test_overconfident_synthetic_predictions_expose_unsupported_labels(corpus):
    synthetic = tuple(EntailmentPrediction(case_id=c.case_id, verdict="SUPPORTED") for c in corpus.folds.qualification)
    score = score_predictions(corpus, "qualification", synthetic)
    assert score.supported_predictions == 36 and score.false_supported_count == 24
    assert score.supported_precision == pytest.approx(1 / 3)
    assert score.accuracy_on_answered == pytest.approx(1 / 3)


def test_mixed_abstentions_preserve_denominators_and_labeled_confusion_cells(corpus):
    synthetic = tuple(
        EntailmentPrediction(case_id=c.case_id, verdict="UNKNOWN" if c.expected == "INSUFFICIENT" else "SUPPORTED")
        for c in corpus.folds.qualification
    )
    score = score_predictions(corpus, "qualification", synthetic)
    assert (score.total, score.answered, score.correct, score.false_supported_count) == (36, 24, 12, 12)
    assert score.coverage == pytest.approx(2 / 3)
    assert score.correct_fraction == pytest.approx(1 / 3)
    assert score.accuracy_on_answered == score.supported_precision == 0.5
    cells = {(cell.expected, cell.predicted): cell.count for cell in score.confusion}
    assert len(cells) == len(score.confusion) == 12
    expected = {("SUPPORTED", "SUPPORTED"): 12, ("INSUFFICIENT", "UNKNOWN"): 12, ("CONTRADICTED", "SUPPORTED"): 12}
    assert cells == {
        (gold, prediction): expected.get((gold, prediction), 0)
        for gold in ("SUPPORTED", "INSUFFICIENT", "CONTRADICTED")
        for prediction in ("SUPPORTED", "INSUFFICIENT", "CONTRADICTED", "UNKNOWN")
    }
    with pytest.raises(ValueError):
        score_predictions(corpus, "qualification", list(synthetic))


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate", "other-fold", "bad-verdict"])
def test_missing_duplicate_foreign_or_invalid_predictions_never_silently_score(corpus, change):
    synthetic = tuple(EntailmentPrediction(case_id=c.case_id, verdict="UNKNOWN") for c in corpus.folds.calibration)
    if change == "missing":
        synthetic = synthetic[:-1]
    elif change == "extra":
        synthetic += (synthetic[0],)
    elif change == "duplicate":
        synthetic = (synthetic[1], *synthetic[1:])
    elif change == "other-fold":
        synthetic = (synthetic[0].model_copy(update={"case_id": corpus.folds.qualification[0].case_id}), *synthetic[1:])
    else:
        synthetic = (synthetic[0].model_copy(update={"verdict": "approved"}), *synthetic[1:])
    with pytest.raises(ValueError, match="entailment_predictions_unconfirmed"):
        score_predictions(corpus, "calibration", synthetic)


@pytest.mark.parametrize("mutation", ["label", "extra", "too-large"])
def test_changed_corpus_bytes_cannot_replace_pin(tmp_path, mutation):
    raw = (DATA / "corpus.json").read_bytes()
    if mutation == "label":
        raw = raw.replace(b'"source_label": 0', b'"source_label": 1', 1)
    elif mutation == "extra":
        raw += b" "
    else:
        raw = b"x" * (64 * 1024 + 1)
    target = tmp_path / "changed.json"
    target.write_bytes(raw)
    with pytest.raises(ValueError, match="entailment_corpus_unconfirmed"):
        load_snli_subset(target)
