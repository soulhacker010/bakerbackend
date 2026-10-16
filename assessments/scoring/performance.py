"""Scoring cards for the performance and leadership instruments.

Built to what each document states, including where that produces a card the
validator refuses. Widening a range so it saves would be exactly the reshaping
this whole rebuild exists to stop, so the problem is left visible and recorded
here instead.
"""
from __future__ import annotations

from typing import List, Sequence

from .baker_street import _bands, _require_scale, _rules, _sequential_domains
from .card import (
    AVERAGE,
    CLINICIAN,
    REVIEW,
    FlagRule,
    QuestionRule,
    ScoreRule,
    ScoringCard,
)
from .loader import question_rule

SLEEP_NOTICE = (
    "These categories are intended for pilot research and development only. They "
    "should not be represented as clinically validated cut scores until the "
    "measure has undergone formal validation."
)


def sleep_and_recovery(questions: Sequence) -> ScoringCard:
    """High Performer Sleep & Recovery Screener.

    Twenty-two questions, of which only the first fifteen are scored. Items 16-22
    are yes/no red flags, and the document is explicit that they "are not included
    in the total score" while a "yes" on any of them "may indicate the need for
    additional evaluation even when the overall HPSRS score is relatively low".

    So they are collected, excluded from every score, and raise a flag on their
    own. Summing all twenty-two, as the current engine would, is exactly the
    failure the document warns about.
    """
    ordered = sorted(questions, key=lambda q: getattr(q, "order", 0))
    if len(ordered) != 22:
        raise ValueError(
            f"Sleep & Recovery expects 22 questions but this assessment has {len(ordered)}."
        )

    scored = _sequential_domains(
        [question_rule(q) for q in ordered[:15]],
        [("quantity", 2), ("continuity", 3), ("restoration", 3),
         ("circadian", 2), ("performance", 5)],
    )
    _require_scale(scored, 0, 3, "Sleep & Recovery")

    # Items 16-22 keep their answers but never reach a score.
    red_flags: List[QuestionRule] = [
        QuestionRule(
            identifier=rule.identifier,
            domain="red_flags",
            scored=False,
            options=rule.options,
        )
        for rule in (question_rule(q) for q in ordered[15:])
    ]

    sections = [
        ScoreRule(id="quantity", label="Sleep Quantity", domain="quantity", min_answered=2),
        ScoreRule(id="continuity", label="Sleep Continuity", domain="continuity", min_answered=3),
        ScoreRule(id="restoration", label="Restoration & Recovery", domain="restoration", min_answered=3),
        ScoreRule(id="circadian", label="Circadian / Occupational Risk", domain="circadian", min_answered=2),
        ScoreRule(id="performance", label="Performance Impact", domain="performance", min_answered=5),
    ]

    overall = ScoreRule(
        id="overall", label="Overall HPSRS Score",
        questions=[rule.identifier for rule in scored],
        min_answered=15,
        bands=_bands(
            ("low", "Low Concern", 0, 8,
             "Relatively few reported sleep or recovery concerns. Continue monitoring, "
             "particularly during periods of increased workload, travel, shift work or illness."),
            ("elevated", "Elevated Concern", 9, 17,
             "Some sleep or recovery difficulties. Review sleep habits, schedule demands and "
             "recovery practices. Consider additional assessment if concerns persist."),
            ("high", "High Concern", 18, 26,
             "Meaningful concerns that may be affecting daily functioning or performance. "
             "Further evaluation is recommended."),
            ("very-high", "Very High Concern", 27, 45,
             "Substantial sleep, recovery and performance concerns. Further evaluation is "
             "strongly recommended."),
        ),
    )

    return ScoringCard(
        questions=list(scored) + red_flags,
        scores=sections + [overall],
        primary_score="overall",
        standing_notice=SLEEP_NOTICE,
        flags=[FlagRule(
            id="sleep-red-flag",
            message="A red-flag item was answered yes. This may indicate the need for "
                    "additional evaluation even when the overall score is relatively low.",
            severity=REVIEW, audience=CLINICIAN,
            questions=[rule.identifier for rule in red_flags],
            operator="==", value="yes", match="any",
        )],
    )


def executive_self_assessment(questions: Sequence) -> ScoringCard:
    """Baker Street Executive Self-Assessment.

    Eight dimensions, three questions each, scored 1-5, so every dimension runs
    3-15 and the total runs 24-120.

    The document originally defined a "0-23 (Poor)" rating, which no submission
    could reach: twenty-four questions that never score below 1 each cannot total
    below 24. The practice resolved this on 16 October 2026 - "Change to 0 - 24
    instead of 0 -23" - so Poor now runs to 24 and Needs Improvement starts at 25.
    The floor of the scale reads as Poor, which is what was asked for.

    The document also asks for a written justification and an improvement step per
    dimension. Those are free-text fields on the assessment, not scored items, and
    are not represented on the card.
    """
    rules = _sequential_domains(
        _rules(questions, 24, "Executive Self-Assessment"),
        [("goal_setting", 3), ("productivity", 3), ("mindset", 3), ("focus", 3),
         ("delegation", 3), ("time_management", 3), ("health", 3), ("self_monitoring", 3)],
    )
    _require_scale(rules, 1, 5, "Executive Self-Assessment")

    labels = [
        ("goal_setting", "Goal Setting"),
        ("productivity", "Productivity"),
        ("mindset", "Mindset and Routines"),
        ("focus", "Focus"),
        ("delegation", "Task Delegation"),
        ("time_management", "Time Management"),
        ("health", "Health Optimisation and Self-Care"),
        ("self_monitoring", "Self-Monitoring"),
    ]
    sections = [
        ScoreRule(id=key, label=label, domain=key, min_answered=3)
        for key, label in labels
    ]

    total = ScoreRule(
        id="total", label="Overall Score",
        scores=[key for key, _ in labels],
        min_answered=8,
        bands=_bands(
            ("poor", "Poor", 0, 24,
             "Immediate improvement is critical. Engage a coach or mentor to create a "
             "comprehensive development plan."),
            ("needs-improvement", "Needs Improvement", 25, 47,
             "Challenges across multiple areas. Develop a structured plan to address gaps."),
            ("adequate", "Adequate", 48, 71,
             "Basic expectations met, with significant inconsistencies. Implement the "
             "improvement steps and seek feedback."),
            ("strong", "Strong", 72, 95,
             "Performing well overall with some areas for refinement."),
            ("excellent", "Excellent", 96, 120,
             "Exceptional leadership effectiveness across all dimensions. Focus on "
             "sustaining strengths and mentoring others."),
        ),
    )

    return ScoringCard(questions=rules, scores=sections + [total], primary_score="total")


def mental_skills(questions: Sequence) -> ScoringCard:
    """Baker Street Mental Skills Screener.

    Eight domains of five items on 1-5. Each domain score is the average of its
    items, and the overall index is the average of the eight domain averages —
    not a total, which is why this is the instrument that proves the engine can
    average averages.

    Known problem with the document: its bands run "4.0-5.0", "3.0-3.9" and
    "below 3.0", leaving nothing covering 3.9 to 4.0. A domain average moves in
    steps of 0.2 so cannot land there, but the overall index is an average of
    eight such figures and can: eight domains at 4.0, 4.0, 4.0, 4.0, 4.0, 4.0,
    3.8, 3.8 average to 3.95. Reproduced as written so the validator reports it.

    The document also defines a self-versus-observer discrepancy flag of 1.5
    points or more. That needs the observer module, which is a separate short form
    and awaits a decision on how the two are paired.
    """
    rules = _sequential_domains(
        _rules(questions, 40, "Mental Skills"),
        [(f"domain{i}", 5) for i in range(1, 9)],
    )
    _require_scale(rules, 1, 5, "Mental Skills")

    labels = [
        "Game Keys and Performance Routines",
        "Self-Awareness and Emotional Control",
        "Grit, Resilience and Growth Mindset",
        "Coachability and Trust",
        "Controllables Framework and Focal Control",
        "Self-Care and Recovery",
        "Confidence and Playing Big",
        "Tactical Adjustments and Team Orientation",
    ]

    def domain_bands():
        return _bands(
            ("growth", "Priority growth area", 1.0, 2.99, "A priority area for development."),
            ("developing", "Developing", 3.0, 3.9, "Targeted training recommended."),
            ("strength", "Strength", 4.0, 5.0, "A strength to maintain and leverage."),
        )

    sections = [
        ScoreRule(
            id=f"domain{i}", label=labels[i - 1], domain=f"domain{i}",
            method=AVERAGE, min_answered=5,
            granularity=0.2, precision=2,
            bands=domain_bands(),
        )
        for i in range(1, 9)
    ]

    overall = ScoreRule(
        id="overall", label="Overall Mental Skills Index",
        scores=[f"domain{i}" for i in range(1, 9)],
        method=AVERAGE, min_answered=8,
        # An average of eight figures that each move in 0.2 steps.
        granularity=0.025, precision=2,
        bands=domain_bands(),
    )

    return ScoringCard(
        questions=rules,
        scores=sections + [overall],
        primary_score="overall",
    )


BUILDERS = {
    "sleep_and_recovery": sleep_and_recovery,
    "executive_self_assessment": executive_self_assessment,
    "mental_skills": mental_skills,
}
