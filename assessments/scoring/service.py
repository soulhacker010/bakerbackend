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


# The audiences a flag may be written for. A flag says who it is for; nothing
# else in a result does, which is why the rest is handled by removal below.
_PATIENT_AUDIENCES = {"patient", "both"}


def for_respondent(data: Mapping[str, Any]) -> Dict[str, Any]:
    """A submitted response as the person who answered it may receive it.

    The dashboard chooses not to render clinician-only warnings to a respondent,
    but choosing not to render something is not the same as not sending it. The
    whole result, warnings included, was being returned to the respondent's
    browser, where the text sits in the response body whatever the page does with
    it. On the perinatal screeners that text is a clinical directive about
    suicide risk, addressed to somebody else and read in the worst possible
    circumstances.

    So the server removes it rather than trusting the page to hide it:

    * warnings not addressed to the respondent are dropped outright;
    * ``highlights`` goes entirely. It is a clinician's summary and no
      respondent-facing screen renders it;
    * every ``interpretation`` goes. These are the range descriptions, and they
      are written as instructions to a clinician about a patient: "Urgent
      referral to a psychiatrist. Screen for suicidal ideation." Read by the
      person who just answered, alone, with a Finish button underneath, that is
      the same failure as sending them the warnings — it simply lives in a
      different field.

    Scores, maximums and range labels are kept. "Depression 11 / 15, High" is the
    respondent's own result and is theirs to see. What the range means clinically,
    and what should be done about it, is a conversation with their clinician.
    """
    out = {key: value for key, value in data.items() if key != "highlights"}

    score = out.get("score")
    if isinstance(score, Mapping):
        trimmed = dict(score)
        flags = trimmed.get("flags")
        if isinstance(flags, list):
            trimmed["flags"] = [
                flag for flag in flags
                if isinstance(flag, Mapping)
                and str(flag.get("audience", "clinician")) in _PATIENT_AUDIENCES
            ]

        trimmed.pop("interpretation", None)
        scores = trimmed.get("scores")
        if isinstance(scores, list):
            trimmed["scores"] = [
                {k: v for k, v in entry.items() if k != "interpretation"}
                if isinstance(entry, Mapping) else entry
                for entry in scores
            ]
        out["score"] = trimmed

    return out
