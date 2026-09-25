"""Scoring cards for the ABA parent training assessments.

The trainer observation form already names a skill area on every question, ten of
them with five items each, and then adds all fifty into one figure. A trainer
reading that figure learns roughly how the parent is doing overall and nothing
at all about where to spend the next session, which is the only question a
training assessment exists to answer.

Its questions are interleaved rather than grouped, so the sections are read from
the tag on each question and never inferred from position.

The competency ranges supplied for this instrument genuinely are total ranges:
they run to 250, which is the total's own maximum. They are reproduced unchanged.
No ranges are set on the individual sections, because none were supplied and a
threshold nobody has stated is not ours to invent.
"""
from __future__ import annotations

from typing import List, Sequence

from .baker_street import _bands, _require_scale, _rules
from .card import CardError, QuestionRule, ScoreRule, ScoringCard

# The ten skill areas, exactly as the questions are tagged.
SKILL_AREAS = [
    ("understanding_aba", "Understanding ABA Principles"),
    ("reinforcement", "Implementing Reinforcement Strategies"),
    ("challenging_behaviors", "Managing Challenging Behaviors"),
    ("communication", "Teaching Functional Communication"),
    ("daily_living", "Teaching Daily Living Skills"),
    ("social_play", "Promoting Social and Play Skills"),
    ("structured_environments", "Creating Structured Environments"),
    ("generalization", "Promoting Skill Generalization"),
    ("collaboration", "Collaborating with ABA Professionals"),
    ("self_care", "Self-Care and Stress Management"),
]

ITEMS_PER_AREA = 5

NOTICE = (
    "Section scores are reported as figures out of 25 so that training can be "
    "directed at the areas that need it. No interpretation ranges have been set "
    "for individual sections; the competency ranges shown apply to the total."
)


def _sections_from_tags(rules: Sequence[QuestionRule]) -> None:
    """Check every question is tagged with a known area, five to each.

    The questions are interleaved, so this is the only thing standing between a
    mistagged item and a section that quietly scores out of the wrong maximum.
    """
    counts = {}
    for rule in rules:
        counts[rule.domain] = counts.get(rule.domain, 0) + 1

    expected = {label for _, label in SKILL_AREAS}
    unknown = sorted(set(counts) - expected)
    missing = sorted(expected - set(counts))
    if unknown or missing:
        raise CardError(
            "ABA trainer observation expects the ten tagged skill areas; "
            + (f"found unexpected {unknown}; " if unknown else "")
            + (f"nothing tagged {missing}" if missing else "")
        )

    wrong = {area: n for area, n in counts.items() if n != ITEMS_PER_AREA}
    if wrong:
        raise CardError(
            f"ABA trainer observation expects {ITEMS_PER_AREA} questions in every "
            f"skill area; got {wrong}."
        )


def aba_trainer_observation(questions: Sequence) -> ScoringCard:
    """ABA Parent Training Skills Assessment, trainer observation form.

    Fifty items on 1-5 across ten skill areas of five, so each area runs 5-25 and
    the total runs 50-250.

    The total keeps the competency ranges already configured, which are correct:
    they cover the scale to its maximum without a gap. What is added is the ten
    area scores, so the form reports where a parent is strong and where the next
    session should go rather than one number standing in for all of it.
    """
    base = _rules(questions, 50, "ABA trainer observation")
    _require_scale(base, 1, 5, "ABA trainer observation")
    _sections_from_tags(base)

    sections: List[ScoreRule] = [
        ScoreRule(id=key, label=label, domain=label)
        for key, label in SKILL_AREAS
    ]

    total = ScoreRule(
        id="total",
        label="Total Score",
        scores=[key for key, _ in SKILL_AREAS],
        # Every area must be calculable; a missing one would understate the total
        # by simply leaving twenty-five points out of it.
        min_answered=len(SKILL_AREAS),
        bands=_bands(
            ("limited", "Limited Competency", 0, 100,
             "Limited competency; begin with intensive training and close support."),
            ("basic", "Basic Competency", 101, 149,
             "Basic competency; prioritize foundational skills with continued guidance."),
            ("moderate", "Moderate Competency", 150, 199,
             "Moderate competency; target specific areas for improvement."),
            ("strong", "Strong Competency", 200, 250,
             "Strong competency across most areas; focus on refinement and generalization."),
        ),
    )

    return ScoringCard(
        questions=base,
        scores=sections + [total],
        primary_score="total",
        standing_notice=NOTICE,
    )

# --------------------------------------------------------------------------- #
# The caregiver skills assessment, parent report plus clinician observation
# --------------------------------------------------------------------------- #

# The document's own split: the parent rates the first thirty, the clinician
# observes the last twenty.
ABA_SELF_REPORT_ITEMS = 30
ABA_OBSERVATION_ITEMS = 20

ABA_SECTIONS = [
    ("self_report", "Parent self-report", "self-report"),
    ("clinician_observation", "Clinician observation", "clinician-observation"),
]


def aba_caregiver_skills(questions: Sequence) -> ScoringCard:
    """ABA Caregiver Skills Assessment, parent report and clinician observation.

    Fifty items on 1-5, so the total runs 50-250. The instrument document is
    explicit about the scale:

        "rating their knowledge and confidence on a 5-point scale
         (1 = Not at All Competent, 5 = Highly Competent)"

    The live assessment carries the editor's default four-point frequency scale
    instead, which caps the total at 150. Its competency ranges run to 250, so
    "Strong Competency" has never been reachable and "Moderate Competency" only
    at exactly 150 — two of its four levels could not be reported at all.
    ``_require_scale`` refuses rather than scoring it on the wrong scale.

    The two halves are reported separately as well as together, because the
    document describes them as different acts: the parent rating their own
    knowledge and confidence, and the clinician observing what the parent
    actually does. A gap between the two is the finding, and a single total hides
    it entirely.
    """
    base = _rules(questions, 50, "ABA caregiver skills")
    _require_scale(base, 1, 5, "ABA caregiver skills")

    counts = {}
    for rule in base:
        counts[rule.domain] = counts.get(rule.domain, 0) + 1
    expected = {"self-report": ABA_SELF_REPORT_ITEMS,
                "clinician-observation": ABA_OBSERVATION_ITEMS}
    if counts != expected:
        raise CardError(
            f"ABA caregiver skills expects {expected} but the assessment has {counts}."
        )

    sections = [
        ScoreRule(id=key, label=label, domain=domain)
        for key, label, domain in ABA_SECTIONS
    ]

    total = ScoreRule(
        id="total",
        label="Total Score",
        scores=[key for key, _, _ in ABA_SECTIONS],
        min_answered=len(ABA_SECTIONS),
        bands=_bands(
            ("limited", "Limited Competency", 0, 99,
             "Limited competency; begin with intensive training and close support."),
            ("basic", "Basic Competency", 100, 149,
             "Basic competency; prioritize foundational skills with continued guidance."),
            ("moderate", "Moderate Competency", 150, 199,
             "Moderate competency; target specific areas for improvement."),
            ("strong", "Strong Competency", 200, 250,
             "Strong competency across most areas; focus on refinement and generalization."),
        ),
    )

    return ScoringCard(
        questions=base,
        scores=sections + [total],
        primary_score="total",
        standing_notice=(
            "The parent's self-report and the clinician's observation are reported "
            "separately as well as in the total. Where they differ markedly, the "
            "difference is worth reading: the two halves ask about knowledge and "
            "confidence on one side and observed practice on the other."
        ),
    )


BUILDERS = {
    "aba_trainer_observation": aba_trainer_observation,
    "aba_caregiver_skills": aba_caregiver_skills,
}
