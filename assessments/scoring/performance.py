"""Scoring cards for the performance and leadership instruments.

Built to what each document states, including where that produces a card the
validator refuses. Widening a range so it saves would be exactly the reshaping
this whole rebuild exists to stop, so the problem is left visible and recorded
here instead.
"""
from __future__ import annotations

from typing import List, Sequence

from .baker_street import _bands, _require_scale, _rules, _scored_and_notes, _sequential_domains
from .card import (
    AVERAGE,
    CLINICIAN,
    INFO,
    ORGANISATIONAL,
    REVIEW,
    SUM,
    CardError,
    FlagRule,
    QuestionRule,
    ScoreRule,
    ScoringCard,
    Transform,
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
        # One flag per red-flag item, naming it, as the document has each raise
        # its own flag: the clinician needs to know which concern was reported.
        flags=[
            FlagRule(
                id=f"sleep-red-flag-{number}",
                message=(f'Red flag answered yes (item {number}): "{text}". ' if text else
                         f"Red flag item {number} was answered yes. ")
                        + "This may indicate the need for additional evaluation even when "
                          "the overall score is relatively low.",
                severity=REVIEW, audience=CLINICIAN,
                questions=[rule.identifier],
                operator="==", value="yes", match="any",
            )
            for number, (rule, text) in enumerate(
                ((rule, (getattr(q, "text", "") or "").strip()) for rule, q in zip(red_flags, ordered[15:])),
                start=16,
            )
        ],
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
    scored_questions, notes = _scored_and_notes(questions)
    rules = _sequential_domains(
        _rules(scored_questions, 24, "Executive Self-Assessment"),
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
        ("health", "Health Optimization and Self-Care"),
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

    # Organizational Development, per the practice's 2026 spreadsheet.
    return ScoringCard(questions=rules + notes, scores=sections + [total], primary_score="total",
                       report_style=ORGANISATIONAL)


def mental_skills(questions: Sequence) -> ScoringCard:
    """Baker Street Mental Skills Screener.

    Eight domains of five items on 1-5. Each domain score is the average of its
    items, and the overall index is the average of the eight domain averages —
    not a total, which is why this is the instrument that proves the engine can
    average averages.

    The document's bands run "4.0-5.0", "3.0-3.9" and "below 3.0", leaving
    nothing covering 3.9 to 4.0. A domain average moves in steps of 0.2 so cannot
    land there, but the overall index can: eight domains at 4.0, 4.0, 4.0, 4.0,
    4.0, 4.0, 3.8, 3.8 average to 3.95. The practice answered on 16 October 2026:
    "Lower band. Anything up until the minimum threshold of the next level stays
    below." So each band runs up to just short of the next one's minimum.

    The document also defines a self-versus-observer discrepancy flag of 1.5
    points or more. That needs the observer module, which is a separate short form
    and awaits a decision on how the two are paired.
    """
    scored_questions, notes = _scored_and_notes(questions)
    rules = _sequential_domains(
        _rules(scored_questions, 40, "Mental Skills"),
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
            ("developing", "Developing", 3.0, 3.99, "Targeted training recommended."),
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
        questions=rules + notes,
        scores=sections + [overall],
        primary_score="overall",
        flags=[FlagRule(
            id="multiple-domains-below-3",
            message="Multiple domains are below 3.0. Prioritize foundational work "
                    "(often emotional control, focus, or recovery first).",
            severity=REVIEW, audience=CLINICIAN,
            scores=[f"domain{i}" for i in range(1, 9)], operator="<", value=3.0, at_least=2,
        )],
    )


MENTAL_SKILLS_LABELS = [
    "Game Keys and Performance Routines",
    "Self-Awareness and Emotional Control",
    "Grit, Resilience and Growth Mindset",
    "Coachability and Trust",
    "Controllables Framework and Focal Control",
    "Self-Care and Recovery",
    "Confidence and Playing Big",
    "Tactical Adjustments and Team Orientation",
]


def mental_skills_observer(questions: Sequence) -> ScoringCard:
    """Mental Skills Screener, Optional Brief Observer Module (8 items).

    A coach or rater observes the athlete and rates one behavior per domain on
    the screener's 1-5 scale. "Observer Score (if completed) = Single rating for
    that domain", so each item is its domain's score, under the same ids and
    bands as the self-report screener: the two are compared domain by domain on
    the client's page, and a gap of 1.5 points or more is flagged there ("Large
    self-observer discrepancy"). The rater's name and observation context are
    collected as notes.
    """
    scored_questions, notes = _scored_and_notes(questions)
    rules = _sequential_domains(
        _rules(scored_questions, 8, "Mental Skills observer"),
        [(f"domain{i}", 1) for i in range(1, 9)],
    )
    _require_scale(rules, 1, 5, "Mental Skills observer")
    bands = lambda: _bands(
        ("growth", "Priority growth area", 1.0, 2.99, "A priority area for development."),
        ("developing", "Developing", 3.0, 3.99, "Targeted training recommended."),
        ("strength", "Strength", 4.0, 5.0, "A strength to maintain and leverage."),
    )
    sections = [
        ScoreRule(id=f"domain{i}", label=MENTAL_SKILLS_LABELS[i - 1], domain=f"domain{i}",
                  method=AVERAGE, min_answered=1, granularity=1.0, precision=2, bands=bands())
        for i in range(1, 9)
    ]
    overall = ScoreRule(
        id="overall", label="Overall Mental Skills Index (observer)",
        scores=[f"domain{i}" for i in range(1, 9)], method=AVERAGE, min_answered=8,
        granularity=0.125, precision=2, bands=bands(),
    )
    return ScoringCard(
        questions=rules + notes,
        scores=sections + [overall],
        primary_score="overall",
        standing_notice="Observer ratings. Compare with the athlete's own Mental Skills Screener on the "
                        "client's page; a gap of 1.5 points or more in a domain is worth discussing.",
    )


# --------------------------------------------------------------------------- #
# Return-to-Play Readiness Screener
# --------------------------------------------------------------------------- #

# Section, label, how many scored items, and how many of those are worded the
# wrong way round. Read from the tag rather than from position, because the
# screener is preceded by intake questions whose number is not fixed.
RTP_DOMAINS = (
    ("pain", "Pain & Symptom Experience", 5, 4),
    ("mood", "Mood & Emotional Well-Being", 5, 0),
    ("fear", "Fear of Movement & Re-Injury", 4, 0),
    ("confidence", "Performance Confidence", 5, 0),
    ("sport_readiness", "Sport-Specific Readiness", 5, 0),
)

RTP_NOTICE = (
    "These ranges are provisional for pilot testing and are not validated "
    "clinical cut scores. The screener does not provide medical clearance and "
    "must not be used on its own to decide whether an athlete is safe to return "
    "to play. Items marked 'not yet attempted' are excluded from the domain they "
    "belong to rather than counted as zero, so a domain is scored against the "
    "items that applied. A domain answered by fewer than half its items is "
    "reported as insufficient data rather than scored."
)


def return_to_play(questions: Sequence) -> ScoringCard:
    """Baker Street Return-to-Play Readiness Screener.

    Five domains, each reported out of 20, summing to a readiness score of
    0-100. High is favorable throughout: this measures readiness, not symptoms.

    **The four reversed items.** The document states that "Questions 9-22 use a
    0-4 scale" where "4 = Most favorable", but the first four items of the pain
    domain are written the other way round - question 9 runs from "0 - None" to
    "4 - Severe and difficult to function with". Taken literally, an athlete in
    severe pain whose symptoms stop them functioning scores full marks for
    readiness. Asked which way to resolve it, the practice replied on 16 October
    2026: "Can these four items be reverse scored? Or is it better to change the
    responses?"

    They are reversed here rather than re-lettered. Rewriting the options would
    put "4 - None" in front of an athlete, which reads as a scoring instruction
    rather than a description of their pain, and would silently change what
    every already-stored answer meant. Reversing changes only the arithmetic.

    Every other item on the screener was checked and runs the right way: item 13
    rates predictability, where high is genuinely favorable, and the mood and
    fear domains are all worded from worst to best already.

    Domains 1-3 sum their items and are scaled to 20. Domains 4 and 5 average
    their 0-10 confidence ratings and scale the average to 20, which is what the
    document asks for and is not the same thing when items are skipped.
    """
    rules = [question_rule(question) for question in questions]
    scored = [rule for rule in rules if rule.scored]

    by_domain = {}
    for rule in scored:
        by_domain.setdefault(rule.domain, []).append(rule)

    known = {key for key, _, _, _ in RTP_DOMAINS} | {"global"}
    unexpected = sorted(set(by_domain) - known)
    if unexpected:
        raise CardError(
            "Return to Play does not recognize the section(s) "
            + ", ".join(repr(name) for name in unexpected)
        )

    rebuilt: List[QuestionRule] = []
    scores: List[ScoreRule] = []
    flags: List[FlagRule] = []

    for key, label, expected, reversed_count in RTP_DOMAINS:
        held = by_domain.get(key, [])
        if len(held) != expected:
            raise CardError(
                f"Return to Play expects {expected} questions tagged {key!r} but "
                f"this assessment has {len(held)}."
            )

        low, high = (0, 10) if key in {"confidence", "sport_readiness"} else (0, 4)
        _require_scale(held, low, high, f"Return to Play ({label})")

        for index, rule in enumerate(held):
            rebuilt.append(QuestionRule(
                identifier=rule.identifier,
                domain=key,
                weight=rule.weight,
                # The document lists the badly worded items first in the domain.
                reverse=index < reversed_count,
                scale_min=rule.scale_min,
                scale_max=rule.scale_max,
                scored=True,
                # "Responses marked N/A are not scored as zero. They should be
                # excluded from the denominator." Every item is allowed to be
                # skipped; only some offer the option, and the rest simply never
                # carry one.
                allow_na=True,
                options=rule.options,
            ))

        # Half the items, rounded up. The document says a domain with too few
        # answers is "Unable to Calculate - Insufficient Data" without saying how
        # few, so this is ours and is stated in the notice rather than hidden.
        minimum = (expected + 1) // 2

        scores.append(ScoreRule(
            id=key,
            label=label,
            domain=key,
            method=AVERAGE if key in {"confidence", "sport_readiness"} else SUM,
            min_answered=minimum,
            transform=Transform(kind="normalize", to=20),
            precision=1,
            granularity=0.1,
        ))

        flags.append(FlagRule(
            id=f"rtp-{key.replace('_', '-')}-concern",
            message=f"{label} is at or below 10 out of 20. The document marks this "
                    f"a significant domain concern.",
            severity=REVIEW,
            audience=CLINICIAN,
            score_id=key,
            operator="<=",
            value=10,
        ))
        flags.append(FlagRule(
            id=f"rtp-{key.replace('_', '-')}-review",
            message=f"{label} is below 15 out of 20, a potential meaningful barrier.",
            severity=INFO,
            audience=CLINICIAN,
            score_id=key,
            operator="<",
            value=15,
        ))

    # The two standalone ratings. Neither belongs in the readiness score - the
    # document keeps them apart from it - but the gap between what the athlete
    # rates and what the clinician rates is a finding, and one number cannot
    # show it.
    for rule in by_domain.get("global", []):
        rebuilt.append(QuestionRule(
            identifier=rule.identifier, domain="global", scale_min=rule.scale_min,
            scale_max=rule.scale_max, scored=True, options=rule.options,
        ))
    globals_held = by_domain.get("global", [])
    if globals_held:
        if len(globals_held) != 2:
            raise CardError(
                "Return to Play expects two questions tagged 'global', the "
                f"athlete's rating and the clinician's, but has {len(globals_held)}."
            )
        _require_scale(globals_held, 0, 10, "Return to Play (overall ratings)")
        scores.append(ScoreRule(
            id="athlete_rating", label="Athlete's Overall Readiness Rating",
            questions=[globals_held[0].identifier], min_answered=1, precision=0,
        ))
        scores.append(ScoreRule(
            id="clinician_rating", label="Clinician's Readiness Rating",
            questions=[globals_held[1].identifier], min_answered=1, precision=0,
        ))

    scores.append(ScoreRule(
        id="overall",
        label="Return-to-Play Readiness Score",
        scores=[key for key, _, _, _ in RTP_DOMAINS],
        min_answered=5,
        precision=0,
        bands=_bands(
            ("significant-barriers", "Significant Reported Barriers", 0, 39,
             "The athlete reports substantial barriers to return. Further "
             "evaluation and individualised intervention should be considered."),
            ("reduced", "Reduced Readiness", 40, 54,
             "Substantial barriers may be present. Further evaluation and targeted "
             "intervention should be considered."),
            ("mixed", "Mixed Readiness", 55, 69,
             "Meaningful barriers may be present. Review individual domains and "
             "consider targeted intervention or further evaluation."),
            ("favourable", "Generally Favorable", 70, 84,
             "Some barriers may be present. Review individual domain scores and "
             "consider monitored progression or targeted support."),
            ("higher", "Higher Reported Readiness", 85, 100,
             "Relatively few symptom, emotional, fear or confidence-related "
             "barriers. Continue standard return-to-play evaluation."),
        ),
    ))

    # The intake questions (sport, team, position...) score nothing, but the card
    # still has to name them, or the assessment cannot be saved with it.
    rebuilt += [rule for rule in rules if not rule.scored]

    return ScoringCard(
        questions=rebuilt,
        scores=scores,
        flags=flags,
        primary_score="overall",
        standing_notice=RTP_NOTICE,
    )


BUILDERS = {
    "mental_skills_observer": mental_skills_observer,
    "return_to_play": return_to_play,
    "sleep_and_recovery": sleep_and_recovery,
    "executive_self_assessment": executive_self_assessment,
    "mental_skills": mental_skills,
}
