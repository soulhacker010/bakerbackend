"""Scoring cards for the published instruments.

These are fixed, externally defined measures. Their cut-offs come from the
published scoring guidance rather than from anything configurable, so they are
written here rather than typed into the editor, and the tests beside them hold
the engine to the published figures.

Each builder takes the assessment's questions in order and binds the card to
whatever identifiers that installation happens to use. Identifiers differ between
environments (live carries a ``-2`` suffix from an earlier slug collision), so
nothing here may hard-code them.

Not included: any question text. These instruments are copyrighted, and the words
belong to their publishers, not to this file.
"""
from __future__ import annotations

from typing import List, Sequence

from .card import (
    Band,
    CardError,
    FlagRule,
    QuestionRule,
    ScoreRule,
    ScoringCard,
    THRESHOLD_COUNT,
    URGENT,
    REVIEW,
    BOTH,
    CLINICIAN,
    PATIENT,
)
from .loader import question_rule


def _rules(questions: Sequence, expected: int, name: str) -> List[QuestionRule]:
    ordered = sorted(questions, key=lambda q: getattr(q, "order", 0))
    if len(ordered) != expected:
        raise CardError(
            f"{name} expects {expected} questions but this assessment has {len(ordered)}."
        )
    return [question_rule(q) for q in ordered]


def _check_scale(rules: Sequence[QuestionRule], low: float, high: float, name: str) -> None:
    """Refuse to score an instrument whose answer options are not the published ones.

    The live PCL-5 and ASRS both carry the editor's default four-point frequency
    scale instead of their own, which makes their totals incomparable to any
    published threshold. Failing here is how that gets noticed.
    """
    for rule in rules:
        if rule.scale_min != low or rule.scale_max != high:
            raise CardError(
                f"{name} is scored on {low:g}-{high:g}, but question "
                f"{rule.identifier!r} offers {rule.scale_min:g}-"
                f"{rule.scale_max if rule.scale_max is not None else '?'}. "
                "The answer options need correcting before this can be scored."
            )


# --------------------------------------------------------------------------- #
# PHQ-9
# --------------------------------------------------------------------------- #

def phq9(questions: Sequence) -> ScoringCard:
    """Patient Health Questionnaire-9. Nine items on 0-3, total 0-27.

    Item 9 asks about thoughts of being better off dead or of self-harm. Any
    answer above zero raises a flag regardless of the total, because a low total
    with a positive item 9 is exactly the case a total would hide.
    """
    rules = _rules(questions, 9, "PHQ-9")
    _check_scale(rules, 0, 3, "PHQ-9")
    item9 = rules[8].identifier

    total = ScoreRule(
        id="total",
        label="PHQ-9 Total",
        questions=[r.identifier for r in rules],
        min_answered=9,
        bands=[
            Band("none-minimal", "None-minimal", 0, 4,
                 "Symptoms are minimal. No treatment indicated on this measure alone."),
            Band("mild", "Mild", 5, 9,
                 "Mild symptoms. Watchful waiting; repeat the measure at follow-up."),
            Band("moderate", "Moderate", 10, 14,
                 "Moderate symptoms. Consider counselling, follow-up or pharmacotherapy."),
            Band("moderately-severe", "Moderately severe", 15, 19,
                 "Moderately severe symptoms. Active treatment with pharmacotherapy "
                 "and/or psychotherapy is usually indicated."),
            Band("severe", "Severe", 20, 27,
                 "Severe symptoms. Immediate initiation of treatment and expedited "
                 "referral to a mental health specialist is usually indicated."),
        ],
    )
    return ScoringCard(
        questions=rules,
        scores=[total],
        flags=[
            FlagRule(
                id="phq9-item-9",
                message="Item 9 was answered above zero. Review for risk before this "
                        "result is filed, whatever the total score.",
                severity=URGENT,
                audience=CLINICIAN,
                questions=[item9],
                operator=">=",
                value=1,
            ),
            FlagRule(
                id="phq9-item-9-respondent",
                message="You indicated thoughts of being better off dead or of hurting "
                        "yourself. Please speak to your clinician straight away. If you "
                        "are in immediate danger, contact your local emergency services.",
                severity=URGENT,
                audience=PATIENT,
                questions=[item9],
                operator=">=",
                value=1,
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# GAD-7
# --------------------------------------------------------------------------- #

def gad7(questions: Sequence) -> ScoringCard:
    """Generalized Anxiety Disorder 7-item scale. Seven items on 0-3, total 0-21."""
    rules = _rules(questions, 7, "GAD-7")
    _check_scale(rules, 0, 3, "GAD-7")

    total = ScoreRule(
        id="total",
        label="GAD-7 Total",
        questions=[r.identifier for r in rules],
        min_answered=7,
        bands=[
            Band("minimal", "Minimal", 0, 4, "Minimal anxiety."),
            Band("mild", "Mild", 5, 9, "Mild anxiety. Monitor."),
            Band("moderate", "Moderate", 10, 14,
                 "Moderate anxiety. Possible clinically significant condition; "
                 "further evaluation recommended."),
            Band("severe", "Severe", 15, 21,
                 "Severe anxiety. Active treatment is probably warranted."),
        ],
    )
    return ScoringCard(questions=rules, scores=[total])


# --------------------------------------------------------------------------- #
# CAGE-AID
# --------------------------------------------------------------------------- #

def cage_aid(questions: Sequence) -> ScoringCard:
    """CAGE adapted to include drug use. Four yes/no items, total 0-4.

    The fifth item asks whether the answers refer to alcohol or drugs. It is a
    classification, not a symptom, and must not reach the total. Today it does,
    contributing zero because its options carry no number.
    """
    rules = _rules(questions, 5, "CAGE-AID")
    _check_scale(rules[:4], 0, 1, "CAGE-AID")

    # Item five carries the substance, so it is recorded but never scored.
    rules = list(rules[:4]) + [
        QuestionRule(
            identifier=rules[4].identifier,
            domain=rules[4].domain,
            scored=False,
            options=rules[4].options,
        )
    ]

    total = ScoreRule(
        id="total",
        label="CAGE-AID Total",
        questions=[r.identifier for r in rules[:4]],
        min_answered=4,
        bands=[
            Band("negative", "Negative screen", 0, 1,
                 "Below the threshold for a positive screen."),
            Band("positive", "Positive screen", 2, 4,
                 "Two or more positive answers is considered clinically significant "
                 "and warrants further assessment."),
        ],
    )
    return ScoringCard(
        questions=rules,
        scores=[total],
        flags=[FlagRule(
            id="cage-positive",
            message="Two or more positive answers. Further assessment for substance "
                    "use is indicated.",
            severity=REVIEW,
            audience=CLINICIAN,
            score_id="total",
            operator=">=",
            value=2,
        )],
    )


BUILDERS = {
    "phq9": phq9,
    "gad7": gad7,
    "cage_aid": cage_aid,
}
