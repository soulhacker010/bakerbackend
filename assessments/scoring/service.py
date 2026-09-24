"""Where the engine meets a stored assessment and a stored response.

The payload written to ``AssessmentResponse.score`` keeps every key the current
dashboard reads — ``total``, ``band``, ``band_label``, ``interpretation`` — and
adds the new ones beside them. Nothing that reads a result today needs to change
in order for an assessment to move onto a card.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Tuple

from .card import ScoringCard
from .engine import OK, ScoringResult, score_assessment
from .loader import card_for_assessment, card_from_dict

logger = logging.getLogger(__name__)


def has_card(assessment) -> bool:
    """True when this assessment has been deliberately moved onto the engine."""
    scoring = getattr(assessment, "scoring", None)
    configuration = (getattr(scoring, "configuration", None) or {}) if scoring else {}
    card = configuration.get("card")
    return isinstance(card, Mapping) and bool(card.get("questions"))


def build_payload(card: ScoringCard, result: ScoringResult) -> Tuple[Dict[str, Any], List[str]]:
    """The stored score, and the highlights shown beside it."""
    payload: Dict[str, Any] = result.as_dict()

    primary = card.primary()
    if primary is not None:
        headline = result.score(primary.id)
        if headline is not None and headline.status == OK and headline.value is not None:
            # Legacy keys, so existing dashboard and export code keeps working.
            payload["total"] = headline.value
            if headline.band_id:
                payload["band"] = headline.band_id
            if headline.band_label:
                payload["band_label"] = headline.band_label
            if headline.interpretation:
                payload["interpretation"] = headline.interpretation

    highlights: List[str] = []
    for score in result.scores:
        if score.status == OK and score.interpretation:
            highlights.append(score.interpretation)
    for flag in result.flags:
        highlights.append(flag.message)

    seen = set()
    deduped = [h for h in highlights if not (h in seen or seen.add(h))]
    return payload, deduped


def score_response(assessment, answers: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Score one submission against the assessment's card.

    Raises only if the card itself cannot be read. Callers treat that as a reason
    to fall back, never as a reason to reject the respondent's submission.
    """
    card = card_for_assessment(assessment)
    result = score_assessment(card, answers)
    return build_payload(card, result)
