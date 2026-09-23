"""Turns a set of answers into scores, bands and flags, by following a card.

The engine knows nothing about any particular instrument. Everything specific to
an assessment lives in its card, which is why adding a measure needs no code.

Two rules shape most of what follows:

* A score is never invented. If too few questions were answered to calculate one
  honestly, the result says so rather than reporting a number that reads as low.
* Rounding happens once, at the end. Subscale maxima such as the Postpartum
  screener's 34.5 sit on half points, and rounding mid-calculation moves people
  across band boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .card import (
    AS_ZERO,
    AVERAGE,
    EXCLUDE,
    SUM,
    THRESHOLD_COUNT,
    Band,
    CardError,
    FlagRule,
    QuestionRule,
    ScoreRule,
    ScoringCard,
)

# Answers that mean "no realistic opportunity to observe this", as opposed to an
# answer of zero. The EFAA and Return to Play both rely on the distinction.
NA_VALUES = {None, "", "na", "n/a", "not applicable"}

OK = "ok"
INSUFFICIENT_DATA = "insufficient_data"


def is_na(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in NA_VALUES
    return value is None


@dataclass
class ScoreResult:
    id: str
    label: str
    status: str
    value: Optional[float] = None
    max_possible: Optional[float] = None
    band_id: Optional[str] = None
    band_label: Optional[str] = None
    interpretation: str = ""
    answered: int = 0
    applicable: int = 0
    # threshold_count only
    positive: Optional[bool] = None

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "answered": self.answered,
            "applicable": self.applicable,
        }
        if self.value is not None:
            payload["value"] = self.value
        if self.max_possible is not None:
            payload["max_possible"] = self.max_possible
        if self.band_id:
            payload["band"] = self.band_id
            payload["band_label"] = self.band_label
        if self.interpretation:
            payload["interpretation"] = self.interpretation
        if self.positive is not None:
            payload["positive"] = self.positive
        return payload


@dataclass
class FlagResult:
    id: str
    message: str
    severity: str
    audience: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "message": self.message,
            "severity": self.severity,
            "audience": self.audience,
        }


@dataclass
class ScoringResult:
    scores: List[ScoreResult] = field(default_factory=list)
    flags: List[FlagResult] = field(default_factory=list)
    notice: str = ""

    def score(self, score_id: str) -> Optional[ScoreResult]:
        for result in self.scores:
            if result.id == score_id:
                return result
        return None

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "version": 2,
            "scores": [s.as_dict() for s in self.scores],
            "flags": [f.as_dict() for f in self.flags],
        }
        if self.notice:
            payload["notice"] = self.notice
        return payload


def _numeric(value: Any) -> Optional[float]:
    """A respondent's answer as a number, or None when it is not one.

    Deliberately strict. The old engine pulled the first number out of any string
    with a regular expression, so a free-text answer of "about 3 times a week"
    added 3 to a clinical total.
    """
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _from_questions(
    card: ScoringCard,
    score: ScoreRule,
    answers: Mapping[str, Any],
) -> ScoreResult:
    rules = card.questions_for(score)
    result = ScoreResult(id=score.id, label=score.label, status=OK, applicable=len(rules))

    contributions: List[float] = []
    maxima: List[float] = []
    qualifying = 0

    for rule in rules:
        raw = answers.get(rule.identifier, None)

        if is_na(raw):
            if rule.allow_na and score.na_policy == EXCLUDE:
                continue          # shrinks the denominator, as the instruments require
            if score.na_policy == AS_ZERO:
                contributions.append(0.0)
                maxima.append(rule.max_contribution())
                result.answered += 1
            continue

        if score.method == THRESHOLD_COUNT:
            if rule.qualifying_values is None:
                raise CardError(
                    f"Question {rule.identifier!r} needs qualifying_values to be counted."
                )
            result.answered += 1
            if raw in rule.qualifying_values or str(raw) in rule.qualifying_values:
                qualifying += 1
            continue

        # The question resolves its own answer, because it knows its options.
        value = rule.value_of(raw)
        if value is None:
            # An unparseable answer is not a zero. Treat it as unanswered so it
            # cannot quietly drag a total down.
            continue

        result.answered += 1
        contributions.append(rule.contribution(value))
        maxima.append(rule.max_contribution())

    if result.answered < score.min_answered:
        result.status = INSUFFICIENT_DATA
        return result

    if score.method == THRESHOLD_COUNT:
        result.value = float(qualifying)
        result.max_possible = float(len(rules))
        result.positive = qualifying >= int(score.positive_at)
        return _finish(score, result)

    if score.method == AVERAGE:
        result.value = sum(contributions) / len(contributions)
        result.max_possible = max(maxima) if maxima else None
    else:
        result.value = sum(contributions)
        result.max_possible = sum(maxima)

    return _finish(score, result)


def _from_scores(
    score: ScoreRule,
    computed: Mapping[str, ScoreResult],
) -> ScoreResult:
    """A score built from other scores, such as an overall made of its subscales."""
    result = ScoreResult(id=score.id, label=score.label, status=OK)
    parts = [computed[i] for i in score.scores or () if i in computed]
    usable = [p for p in parts if p.status == OK and p.value is not None]
    result.applicable = len(parts)
    result.answered = len(usable)

    if len(usable) < score.min_answered:
        result.status = INSUFFICIENT_DATA
        return result

    values = [p.value for p in usable]
    maxima = [p.max_possible for p in usable if p.max_possible is not None]

    if score.method == AVERAGE:
        result.value = sum(values) / len(values)
        result.max_possible = max(maxima) if maxima else None
    else:
        result.value = sum(values)
        result.max_possible = sum(maxima) if maxima else None

    return _finish(score, result)


def _finish(score: ScoreRule, result: ScoreResult) -> ScoreResult:
    if result.value is None:
        return result

    if score.transform is not None:
        if score.transform.kind == "normalize":
            if not result.max_possible:
                result.status = INSUFFICIENT_DATA
                result.value = None
                return result
            result.value = score.transform.apply(result.value, result.max_possible)
            result.max_possible = score.transform.to
        else:
            result.value = score.transform.apply(result.value, result.max_possible or 0.0)
            if result.max_possible is not None:
                result.max_possible = score.transform.apply(result.max_possible, result.max_possible)

    result.value = round(result.value, score.precision)
    if result.max_possible is not None:
        result.max_possible = round(result.max_possible, score.precision)

    band = score.band_for(result.value)
    if band is not None:
        result.band_id = band.id
        result.band_label = band.label
        result.interpretation = band.description
    return result


def _flags(
    card: ScoringCard,
    answers: Mapping[str, Any],
    computed: Mapping[str, ScoreResult],
) -> List[FlagResult]:
    raised: List[FlagResult] = []

    for flag in card.flags:
        fired = False

        if flag.questions is not None:
            outcomes = []
            for identifier in flag.questions:
                raw = answers.get(identifier, None)
                if is_na(raw):
                    outcomes.append(False)
                    continue
                value = _numeric(raw)
                if value is None:
                    # Yes/No red flags arrive as text. Compare on equality only,
                    # since ordering has no meaning for them.
                    outcomes.append(
                        flag.operator == "=="
                        and str(raw).strip().lower() == str(flag.value).strip().lower()
                    )
                    continue
                outcomes.append(flag.compare(value))
            fired = all(outcomes) if flag.match == "all" else any(outcomes)

        else:
            result = computed.get(flag.score_id)
            # A score that could not be calculated cannot raise or clear a flag.
            if result is not None and result.status == OK and result.value is not None:
                fired = flag.compare(result.value)

        if fired:
            raised.append(
                FlagResult(
                    id=flag.id,
                    message=flag.message,
                    severity=flag.severity,
                    audience=flag.audience,
                )
            )

    return raised


def score_assessment(card: ScoringCard, answers: Mapping[str, Any]) -> ScoringResult:
    """Score one submission against one card.

    ``answers`` is keyed by question identifier. Missing keys are treated as
    unanswered, which is not the same as zero.
    """
    computed: Dict[str, ScoreResult] = {}
    ordered: List[ScoreResult] = []

    for rule in card.ordered_scores():
        if rule.scores is not None:
            result = _from_scores(rule, computed)
        else:
            result = _from_questions(card, rule, answers)
        computed[rule.id] = result
        ordered.append(result)

    # Scores are reported in the order the card declares them, which is the order
    # the clinician expects to read them, not the dependency order above.
    by_id = {r.id: r for r in ordered}
    scores = [by_id[s.id] for s in card.scores]

    return ScoringResult(
        scores=scores,
        flags=_flags(card, answers, computed),
        notice=card.standing_notice,
    )
