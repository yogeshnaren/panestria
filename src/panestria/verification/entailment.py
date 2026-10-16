"""Pinned human-label preflight data and prediction metrics, never release/model authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

SNLI_SUBSET_SHA256 = "5f9c0ac087ebcb1cedea91275ccf497cf9f5a8dec51e112cb597a277e93e7f1c"
SNLI_REVISION = "cdb5c3d5eed6ead6e5a341c8e56e669bb666725b"
Gold = Literal["SUPPORTED", "INSUFFICIENT", "CONTRADICTED"]
Label = Literal["SUPPORTED", "INSUFFICIENT", "CONTRADICTED", "UNKNOWN"]
_GOLD: tuple[Gold, ...] = ("SUPPORTED", "INSUFFICIENT", "CONTRADICTED")
_LABELS: tuple[Label, ...] = (*_GOLD, "UNKNOWN")


class _Closed(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, revalidate_instances="always", hide_input_in_errors=True
    )


class EntailmentInput(_Closed):
    case_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    premise: str = Field(min_length=1, max_length=2048)
    hypothesis: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def byte_caps(self) -> Self:
        if any(len(value.encode()) > 2048 for value in (self.premise, self.hypothesis)):
            raise ValueError("entailment_input_byte_limit")
        return self


class HumanLabelCase(EntailmentInput):
    source_split: Literal["validation", "test"]
    source_row_index: StrictInt = Field(ge=0, lt=200)
    source_label: StrictInt = Field(ge=0, le=2)
    expected: Gold
    premise_group_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def source_binding(self) -> Self:
        group = hashlib.sha256(" ".join(self.premise.split()).casefold().encode()).hexdigest()
        identity = hashlib.sha256(
            json.dumps(
                {
                    "revision": SNLI_REVISION,
                    "split": self.source_split,
                    "row_idx": self.source_row_index,
                    "premise": self.premise,
                    "hypothesis": self.hypothesis,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()[:24]
        if group != self.premise_group_sha256 or identity != self.case_id or self.expected != _GOLD[self.source_label]:
            raise ValueError("entailment_source_binding_invalid")
        return self


class _Folds(_Closed):
    calibration: tuple[HumanLabelCase, ...] = Field(min_length=36, max_length=36)
    qualification: tuple[HumanLabelCase, ...] = Field(min_length=36, max_length=36)


class EntailmentCorpus(_Closed):
    schema_version: Literal[1]
    dataset: Literal["stanfordnlp/snli"]
    dataset_revision: Literal["cdb5c3d5eed6ead6e5a341c8e56e669bb666725b"]
    license: Literal["CC-BY-SA-4.0"]
    purpose: Literal["evaluation_fixture_only_no_training_authorization"]
    folds: _Folds

    @model_validator(mode="after")
    def disjoint_balanced(self) -> Self:
        groups: set[str] = set()
        ids: set[str] = set()
        for split, cases in (("validation", self.folds.calibration), ("test", self.folds.qualification)):
            if any(case.source_split != split for case in cases):
                raise ValueError("entailment_fold_invalid")
            if [sum(case.expected == label for case in cases) for label in _GOLD] != [12, 12, 12]:
                raise ValueError("entailment_balance_invalid")
            if tuple(case.case_id for case in cases) != tuple(sorted(case.case_id for case in cases)):
                raise ValueError("entailment_case_order_invalid")
            for case in cases:
                if case.case_id in ids or case.premise_group_sha256 in groups:
                    raise ValueError("entailment_case_leakage")
                ids.add(case.case_id)
                groups.add(case.premise_group_sha256)
        return self

    def cases(self, fold: Literal["calibration", "qualification"]) -> tuple[HumanLabelCase, ...]:
        if fold not in {"calibration", "qualification"}:
            raise ValueError("entailment_fold_invalid")
        return self.folds.calibration if fold == "calibration" else self.folds.qualification

    def model_inputs(self, fold: Literal["calibration", "qualification"]) -> tuple[EntailmentInput, ...]:
        # Explicit projection. Gold labels, source row/split and selection order
        # are host-only evaluation data, never included in the model payload.
        return tuple(
            EntailmentInput(case_id=c.case_id, premise=c.premise, hypothesis=c.hypothesis) for c in self.cases(fold)
        )


class EntailmentPrediction(_Closed):
    case_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    verdict: Label


@dataclass(frozen=True)
class ConfusionCell:
    expected: Gold
    predicted: Label
    count: int


@dataclass(frozen=True)
class EntailmentScore:
    total: int
    answered: int
    correct: int
    coverage: float
    correct_fraction: float
    accuracy_on_answered: float | None
    supported_predictions: int
    supported_precision: float | None
    false_supported_count: int
    confusion: tuple[ConfusionCell, ...]
    authority: Literal["PREDICTION_METRICS_ONLY"] = "PREDICTION_METRICS_ONLY"


def load_snli_subset(path: Path) -> EntailmentCorpus:
    try:
        with path.open("rb") as stream:
            raw = stream.read(64 * 1024 + 1)
        if len(raw) > 64 * 1024 or hashlib.sha256(raw).hexdigest() != SNLI_SUBSET_SHA256:
            raise ValueError
        return EntailmentCorpus.model_validate_json(raw)
    except Exception:
        raise ValueError("entailment_corpus_unconfirmed") from None


def score_predictions(
    corpus: EntailmentCorpus,
    fold: Literal["calibration", "qualification"],
    predictions: tuple[EntailmentPrediction, ...],
) -> EntailmentScore:
    try:
        corpus = EntailmentCorpus.model_validate(corpus)
        cases = corpus.cases(fold)
        if type(predictions) is not tuple or len(predictions) != len(cases):
            raise ValueError
        parsed = tuple(EntailmentPrediction.model_validate(p) for p in predictions)
        by_id = {p.case_id: p.verdict for p in parsed}
        if len(by_id) != len(parsed) or set(by_id) != {c.case_id for c in cases}:
            raise ValueError
        correct = sum(by_id[c.case_id] == c.expected for c in cases)
        answered = sum(p.verdict != "UNKNOWN" for p in parsed)
        supported = sum(p.verdict == "SUPPORTED" for p in parsed)
        false_supported = sum(by_id[c.case_id] == "SUPPORTED" and c.expected != "SUPPORTED" for c in cases)
        confusion = tuple(
            ConfusionCell(gold, label, sum(c.expected == gold and by_id[c.case_id] == label for c in cases))
            for gold in _GOLD
            for label in _LABELS
        )
        return EntailmentScore(
            len(cases),
            answered,
            correct,
            answered / len(cases),
            correct / len(cases),
            correct / answered if answered else None,
            supported,
            (supported - false_supported) / supported if supported else None,
            false_supported,
            confusion,
        )
    except Exception:
        raise ValueError("entailment_predictions_unconfirmed") from None
