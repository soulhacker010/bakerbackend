"""Builds a scoring card from what is stored on an assessment.

Two paths, chosen per assessment:

* A card has been written for it, so the card is used.
* No card yet, so one is derived that reproduces the behaviour the assessment has
  today. Nothing changes for anyone until a card is deliberately written.

That second path is what makes this safe to deploy. Adding the engine does not
alter a single existing result; assessments move over one at a time.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .card import (
    AVERAGE,
    SUM,
    THRESHOLD_COUNT,
    Band,
    CardError,
    FlagRule,
    QuestionRule,
    ScoreRule,
    ScoringCard,
    Transform,
)

# Answer options are stored as display strings carrying their own value. Both
# orders are in use across the live assessments:
#   "0 - Never"        number first    (440 options)
#   "Moderate (2)"     number last     (725 options)
# No option in the database contains more than one number, so either end is
# unambiguous. A second number appearing in future would be, which is why
# ``parse_option_value`` refuses rather than guessing.
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def parse_option_value(option: Any) -> Optional[float]:
    """The numeric value an answer option carries, or None if it has none."""
    if isinstance(option, (int, float)) and not isinstance(option, bool):
        return float(option)
    if isinstance(option, Mapping):
        value = option.get("value")
        return float(value) if isinstance(value, (int, float)) else None
    if not isinstance(option, str):
        return None
    found = _NUMBER.findall(option)
    if not found:
        return None
    if len(set(found)) > 1:
        raise CardError(
            f"Answer option {option!r} contains more than one number, so its value "
            "is ambiguous. Give the option an explicit value."
        )
    return float(found[0])


def option_map(options: Sequence[Any]) -> Dict[str, float]:
    """Every way an answer might arrive, mapped to the number it is worth.

    Respondents submit the option text, not an index, so the text is the key.
    The bare number is accepted too, for clients that send the value directly.
    """
    mapping: Dict[str, float] = {}
    for option in options or ():
        value = parse_option_value(option)
        if value is None:
            continue
        label = option if isinstance(option, str) else str(option)
        mapping[label.strip()] = value
        mapping[label.strip().lower()] = value
        # "2" and "2.0" both resolve.
        mapping[str(value)] = value
        if value == int(value):
            mapping[str(int(value))] = value
    return mapping


def question_rule(question, *, allow_na: bool = False) -> QuestionRule:
    """A card rule for one stored ``AssessmentQuestion``."""
    config = question.config if isinstance(question.config, dict) else {}
    options = config.get("options") or []
    values = [v for v in (parse_option_value(o) for o in options) if v is not None]

    # A question whose options carry no numbers cannot contribute to a score.
    # The CAGE "alcohol or drugs?" item is one: a classification, not an answer
    # to be added up. Today it is summed as zero; here it is excluded outright.
    scored = bool(values)

    return QuestionRule(
        identifier=question.identifier,
        domain=(question.domain or "general"),
        scale_min=min(values) if values else 0.0,
        scale_max=max(values) if values else None,
        scored=scored,
        allow_na=allow_na,
        options=option_map(options) or None,
    )


def _bands_from_configuration(configuration: Mapping[str, Any]) -> List[Band]:
    raw = configuration.get("bands")
    if not isinstance(raw, list):
        return []
    bands: List[Band] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        low, high = entry.get("min"), entry.get("max")
        if low is None or high is None:
            continue
        try:
            low, high = float(low), float(high)
        except (TypeError, ValueError):
            continue
        bands.append(Band(
            id=str(entry.get("id") or entry.get("label") or f"band-{index + 1}"),
            label=str(entry.get("label") or ""),
            minimum=low,
            maximum=high,
            description=str(entry.get("description") or ""),
        ))
    return bands


def legacy_card(questions: Sequence[Any], configuration: Mapping[str, Any]) -> ScoringCard:
    """A card that scores exactly the way the assessment does today.

    One total across every question, against the bands already configured. The
    only difference is that answers which carry no number are excluded rather
    than counted as zero, which changes no total.
    """
    rules = [question_rule(q) for q in questions]
    total = ScoreRule(
        id="total",
        label="Total",
        questions=[r.identifier for r in rules],
        method=SUM,
        bands=_bands_from_configuration(configuration or {}),
    )
    return ScoringCard(questions=rules, scores=[total])


# --------------------------------------------------------------------------- #
# Reading and writing a stored card
# --------------------------------------------------------------------------- #

def _transform_from(data: Optional[Mapping[str, Any]]) -> Optional[Transform]:
    if not isinstance(data, Mapping):
        return None
    return Transform(
        kind=str(data.get("kind", "linear")),
        multiply=float(data.get("multiply", 1.0)),
        divide=float(data.get("divide", 1.0)),
        to=float(data.get("to", 1.0)),
    )


def card_from_dict(data: Mapping[str, Any]) -> ScoringCard:
    """Rebuild a card from the JSON stored against an assessment."""
    questions = []
    for entry in data.get("questions") or ():
        qualifying = entry.get("qualifying_values")
        questions.append(QuestionRule(
            identifier=str(entry["identifier"]),
            domain=entry.get("domain"),
            weight=float(entry.get("weight", 1.0)),
            reverse=bool(entry.get("reverse", False)),
            scale_min=float(entry.get("scale_min", 0.0)),
            scale_max=(float(entry["scale_max"]) if entry.get("scale_max") is not None else None),
            scored=bool(entry.get("scored", True)),
            allow_na=bool(entry.get("allow_na", False)),
            qualifying_values=(frozenset(str(v) for v in qualifying) if qualifying else None),
            options=({str(k): float(v) for k, v in entry["options"].items()}
                     if entry.get("options") else None),
        ))

    scores = []
    for entry in data.get("scores") or ():
        scores.append(ScoreRule(
            id=str(entry["id"]),
            label=str(entry.get("label") or entry["id"]),
            method=str(entry.get("method", SUM)),
            domain=entry.get("domain"),
            questions=entry.get("questions"),
            scores=entry.get("scores"),
            na_policy=str(entry.get("na_policy", "exclude")),
            min_answered=int(entry.get("min_answered", 1)),
            transform=_transform_from(entry.get("transform")),
            bands=[Band(
                id=str(b["id"]),
                label=str(b.get("label") or ""),
                minimum=float(b["min"]),
                maximum=float(b["max"]),
                description=str(b.get("description") or ""),
            ) for b in entry.get("bands") or ()],
            precision=int(entry.get("precision", 2)),
            granularity=float(entry.get("granularity", 1.0)),
            positive_at=(int(entry["positive_at"]) if entry.get("positive_at") is not None else None),
        ))

    flags = []
    for entry in data.get("flags") or ():
        flags.append(FlagRule(
            id=str(entry["id"]),
            message=str(entry.get("message") or ""),
            severity=str(entry.get("severity", "review")),
            audience=str(entry.get("audience", "clinician")),
            questions=entry.get("questions"),
            operator=str(entry.get("operator", ">=")),
            value=entry.get("value"),
            match=str(entry.get("match", "any")),
            score_id=entry.get("score_id"),
        ))

    return ScoringCard(
        questions=questions,
        scores=scores,
        flags=flags,
        standing_notice=str(data.get("standing_notice") or ""),
        primary_score=data.get("primary_score"),
    )


def card_to_dict(card: ScoringCard) -> Dict[str, Any]:
    """Serialise a card for storage. The inverse of ``card_from_dict``."""
    return {
        "questions": [
            {
                "identifier": q.identifier,
                "domain": q.domain,
                "weight": q.weight,
                "reverse": q.reverse,
                "scale_min": q.scale_min,
                "scale_max": q.scale_max,
                "scored": q.scored,
                "allow_na": q.allow_na,
                "qualifying_values": sorted(q.qualifying_values) if q.qualifying_values else None,
                "options": dict(q.options) if q.options else None,
            }
            for q in card.questions
        ],
        "scores": [
            {
                "id": s.id,
                "label": s.label,
                "method": s.method,
                "domain": s.domain,
                "questions": list(s.questions) if s.questions else None,
                "scores": list(s.scores) if s.scores else None,
                "na_policy": s.na_policy,
                "min_answered": s.min_answered,
                "transform": ({
                    "kind": s.transform.kind,
                    "multiply": s.transform.multiply,
                    "divide": s.transform.divide,
                    "to": s.transform.to,
                } if s.transform else None),
                "bands": [
                    {"id": b.id, "label": b.label, "min": b.minimum,
                     "max": b.maximum, "description": b.description}
                    for b in s.bands
                ],
                "precision": s.precision,
                "granularity": s.granularity,
                "positive_at": s.positive_at,
            }
            for s in card.scores
        ],
        "flags": [
            {
                "id": f.id,
                "message": f.message,
                "severity": f.severity,
                "audience": f.audience,
                "questions": list(f.questions) if f.questions else None,
                "operator": f.operator,
                "value": f.value,
                "match": f.match,
                "score_id": f.score_id,
            }
            for f in card.flags
        ],
        "standing_notice": card.standing_notice,
        "primary_score": card.primary_score,
    }


def card_for_assessment(assessment) -> ScoringCard:
    """The card to score this assessment with.

    Uses the written card when there is one, and otherwise derives one that
    matches current behaviour.
    """
    scoring = getattr(assessment, "scoring", None)
    configuration = (getattr(scoring, "configuration", None) or {}) if scoring else {}
    questions = list(assessment.questions.all())

    stored = configuration.get("card")
    if isinstance(stored, Mapping) and stored.get("questions"):
        return card_from_dict(stored)

    return legacy_card(questions, configuration)
