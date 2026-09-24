"""Scoring cards for Baker Street's own instruments.

Interim home. These belong in the editor once it can express them, and this
module exists because several are live and scoring incorrectly today. Everything
here is taken from the instrument documents supplied by the client, and the tests
beside it hold the engine to the figures those documents state.

Unlike the published instruments, these are the client's own work and may change.
Where a document and the live configuration disagree, the document wins and the
difference is written down.
"""
from __future__ import annotations

from typing import List, Sequence

from .card import (
    Band,
    CardError,
    QuestionRule,
    ScoreRule,
    ScoringCard,
    Transform,
)
from .loader import question_rule


def _rules(questions: Sequence, expected: int, name: str) -> List[QuestionRule]:
    ordered = sorted(questions, key=lambda q: getattr(q, "order", 0))
    if len(ordered) != expected:
        raise CardError(
            f"{name} expects {expected} questions but this assessment has {len(ordered)}."
        )
    return [question_rule(q) for q in ordered]


def health_in_motion(questions: Sequence) -> ScoringCard:
    """Baker Street Health in Motion, General Foot Health Screener.

    Fifteen items on 0-4, giving a raw total of 0-60. The document then states:

        "Total score is calculated by summing all responses, multiplying by 5,
         and dividing by 3 to yield a score from 0 (best) to 100 (worst)."

    That conversion has never been applied. The live assessment compares the raw
    0-60 total against ranges written for 0-100, so every result reads lower than
    the instrument intends. A raw 35 should report 58.3 and read "urgent
    evaluation recommended"; today it reports 35 and reads "evaluation advised".

    The ranges themselves are already correct and are reproduced unchanged.
    """
    rules = _rules(questions, 15, "Health in Motion")
    for rule in rules:
        if rule.scale_min != 0 or rule.scale_max != 4:
            raise CardError(
                f"Health in Motion is scored on 0-4, but question {rule.identifier!r} "
                f"offers {rule.scale_min:g}-{rule.scale_max if rule.scale_max is not None else '?'}."
            )

    total = ScoreRule(
        id="total",
        label="Foot Health Score",
        questions=[r.identifier for r in rules],
        min_answered=15,
        transform=Transform(kind="linear", multiply=5, divide=3),
        # The raw total moves in whole numbers and the conversion multiplies by
        # 5/3, so converted scores step by 5/3 and never land between 24 and 25.
        granularity=5 / 3,
        precision=2,
        bands=[
            Band("level-1", "Level 1", 0, 24,
                 "Mild or no foot health issues; follow up and preventative care "
                 "visits will suffice."),
            Band("level-2", "Level 2", 25, 50,
                 "Moderate foot health issues; evaluation advised."),
            Band("level-3", "Level 3", 51, 100,
                 "Significant foot health issues; urgent evaluation recommended."),
        ],
    )
    return ScoringCard(questions=rules, scores=[total])


BUILDERS = {
    "health_in_motion": health_in_motion,
}
