"""Scoring card for the Executive Functioning Assessment for Autism (EFAA).

The best-specified instrument in the set. Its document states the reverse-scored
items, the conversion for them, the not-applicable handling and every cut-off, and
its ranges cover the whole reachable scale without a gap.

It is also the one that exercises most of the engine at once: six sections,
reverse items, not-applicable answers that shrink the denominator, a total built
from the sections, and section-level thresholds rather than bands.
"""
from __future__ import annotations

from typing import List, Sequence

from .baker_street import _bands, _require_scale, _rules
from .card import (
    CLINICIAN,
    REVIEW,
    CardError,
    FlagRule,
    QuestionRule,
    ScoreRule,
    ScoringCard,
)

DOMAINS = [
    ("working_memory", "Working Memory"),
    ("cognitive_flexibility", "Cognitive Flexibility"),
    ("task_initiation", "Task Initiation / Monitoring"),
    ("emotional_regulation", "Emotional Regulation"),
    ("inhibition", "Inhibition"),
    ("planning", "Planning / Organisation"),
]

NOTICE = (
    "Provisional scoring and interpretation, awaiting pilot norms. Screening, "
    "intervention planning and support for diagnostic formulation; not intended "
    "as a standalone diagnostic instrument."
)


def efaa(questions: Sequence) -> ScoringCard:
    """Executive Functioning Assessment for Autism, 48-item revision.

    Six sections of eight items on 0-3, so each section runs 0-24 and the total
    runs 0-144.

    The eighth item of every section is positively worded and reverse-scored:
    items 8, 16, 24, 32, 40 and 48, converted 0->3, 1->2, 2->1, 3->0 exactly as
    the document states.

    Not-applicable answers are offered throughout. The document directs that such
    an item is "not scored" and the maximum recalculated, which is what
    ``allow_na`` does. It does not state how few answers are too few; five of
    eight is used here and needs the client's confirmation.

    Sections carry a threshold rather than bands — "scores >= 12 (50% of maximum)
    suggest possible domain-specific difficulty" — so each raises a flag instead
    of being banded. The document is explicit that the profile of elevations
    matters more than the total alone, which is why every section is reported.
    """
    base = _rules(questions, 48, "EFAA")
    _require_scale(base, 0, 3, "EFAA")

    rules: List[QuestionRule] = []
    for index, rule in enumerate(base):
        position = index % 8          # 0-7 within the section
        domain = DOMAINS[index // 8][0]
        rules.append(QuestionRule(
            identifier=rule.identifier,
            domain=domain,
            scale_min=rule.scale_min,
            scale_max=rule.scale_max,
            # The eighth item of each section is the positively worded one.
            reverse=(position == 7),
            allow_na=True,
            options=rule.options,
        ))

    sections = [
        ScoreRule(id=key, label=label, domain=key, min_answered=5)
        for key, label in DOMAINS
    ]

    total = ScoreRule(
        id="total", label="Total Score",
        scores=[key for key, _ in DOMAINS],
        # Every section must be calculable, or the total would quietly understate
        # by simply leaving one out.
        min_answered=6,
        bands=_bands(
            ("minimal", "Minimal", 0, 28,
             "Minimal reported executive dysfunction relative to this sample."),
            ("mild", "Mild elevation", 29, 57,
             "Mild elevation. Consider targeted monitoring and supports."),
            ("moderate", "Moderate elevation", 58, 86,
             "Moderate elevation. Comprehensive assessment and structured intervention recommended."),
            ("significant", "Significant elevation", 87, 144,
             "Significant elevation. Prioritise intensive supports and further evaluation."),
        ),
    )

    flags = [
        FlagRule(
            id=f"{key}-elevated",
            message=f"{label} is at or above 12, half of its maximum. This suggests possible "
                    f"domain-specific difficulty worth further observation or intervention "
                    f"planning. Consider the profile of elevations rather than the total alone.",
            severity=REVIEW, audience=CLINICIAN,
            score_id=key, operator=">=", value=12,
        )
        for key, label in DOMAINS
    ]

    return ScoringCard(
        questions=rules,
        scores=sections + [total],
        flags=flags,
        primary_score="total",
        standing_notice=NOTICE,
    )




# --------------------------------------------------------------------------- #
# The two Executive Functioning scales that are live on a single total.
#
# Both list five sections on their questions already, and both are summed into
# one figure whose ranges do not cover the scale that figure can reach:
#
#   Severity Scale         ranges stop at  24 of a possible 120
#   Adults and Adolescents ranges stop at  36 of a possible  90
#
# The consequence is not a rounding difference. A respondent who answers at the
# top of every item — the most impaired the instrument can describe — falls past
# the last range and is reported with no result at all, while a respondent with
# mild difficulty on half the items lands in "Significant Impairment".
# --------------------------------------------------------------------------- #

SEVERITY_SECTIONS = [
    ("working_memory", "Working Memory"),
    ("cognitive_flexibility", "Cognitive Flexibility"),
    ("inhibitory_control", "Inhibitory Control"),
    ("emotional_regulation", "Emotional Regulation"),
    ("planning_organization", "Planning/Organization"),
]

_PENDING_TOTAL = (
    "Section scores are reported against the instrument's own ranges. The total "
    "is reported as a figure only: the ranges supplied describe a section rather "
    "than a total, so no total interpretation is stated until the ranges for one "
    "are confirmed."
)


def _sections_by_domain(rules, sections, name, per_section):
    """Check the stored sections are the ones expected, and evenly filled.

    These two assessments already carry their section on each question, so the
    grouping is read rather than assumed by position. It is still checked: a
    section quietly losing a question would shift every maximum underneath it.
    """
    counts = {}
    for rule in rules:
        counts[rule.domain] = counts.get(rule.domain, 0) + 1

    expected = {label for _, label in sections}
    if set(counts) != expected:
        raise CardError(
            f"{name} expects sections {sorted(expected)} but the assessment has "
            f"{sorted(counts)}."
        )
    wrong = {d: n for d, n in counts.items() if n != per_section}
    if wrong:
        raise CardError(
            f"{name} expects {per_section} questions in every section; got {wrong}."
        )


def ef_severity_scale(questions: Sequence) -> ScoringCard:
    """Executive Functioning Assessment, Severity Scale.

    Thirty items on 0-4 across five sections of six, so each section runs 0-24
    and the total runs 0-120.

    The live ranges are 0-5, 6-16 and 17-24. Twenty-four is exactly six items at
    four points, which is one section's maximum and a fifth of the total's. They
    are reproduced here unchanged and applied to each section, which is the only
    reading on which they cover their scale exactly rather than a fifth of it.

    That inference still needs confirming, and the total is therefore left
    without ranges rather than given ones nobody has stated. Reporting a bare
    figure understates nothing; the previous behaviour reported "Significant
    Impairment" for a total of 17 out of 120, and nothing at all above 24.
    """
    base = _rules(questions, 30, "EF Severity Scale")
    _require_scale(base, 0, 4, "EF Severity Scale")
    _sections_by_domain(base, SEVERITY_SECTIONS, "EF Severity Scale", 6)

    section_bands = lambda: _bands(
        ("band-1", "Minimal Concerns", 0, 5,
         "Severity levels are low; likely not requiring intervention."),
        ("band-2", "Moderate Disruption", 6, 16,
         "Noticeable disruption in functioning; support may be beneficial."),
        ("band-3", "Significant Impairment", 17, 24,
         "High severity; prioritize intervention and referral."),
    )

    sections = [
        ScoreRule(id=key, label=label, domain=label, bands=section_bands())
        for key, label in SEVERITY_SECTIONS
    ]

    total = ScoreRule(
        id="total",
        label="Total Score",
        scores=[key for key, _ in SEVERITY_SECTIONS],
        min_answered=5,
    )

    flags = [
        FlagRule(
            id=f"{key}-significant",
            message=f"{label} is in the Significant Impairment range. Prioritise "
                    f"intervention and referral for this area.",
            severity=REVIEW, audience=CLINICIAN,
            score_id=key, operator=">=", value=17,
        )
        for key, label in SEVERITY_SECTIONS
    ]

    return ScoringCard(
        questions=base,
        scores=sections + [total],
        flags=flags,
        primary_score="total",
        standing_notice=_PENDING_TOTAL,
    )


def ef_adults_adolescents(questions: Sequence) -> ScoringCard:
    """Executive Functioning Assessment for Adults and Adolescents, frequency only.

    Thirty items on 0-3 across five sections of six, so each section runs 0-18
    and the total runs 0-90.

    Its ranges cannot be applied as they stand, and the labels say why:

        Minimal Concerns                     0-10
        Significant Impairment (WM, CF, PO) 18-24
        Significant Impairment (IC, ER)     25-36

    The last two name sections — Working Memory, Cognitive Flexibility,
    Planning/Organization, Inhibitory Control, Emotional Regulation — so they
    were written per section and not as one list. As one list they leave 11-17
    with no result and stop at 36 of a possible 90. As section ranges they do not
    fit either: a section of six items at three points reaches 18, below the
    start of both.

    Neither reading works, so no ranges are set here. Every section is reported
    as a figure and the profile across them is the finding, which is what the
    section-specific labels were reaching for. The ranges need the client's
    clarification before any interpretation is printed against them.
    """
    base = _rules(questions, 30, "EF Adults and Adolescents")
    _require_scale(base, 0, 3, "EF Adults and Adolescents")
    _sections_by_domain(base, SEVERITY_SECTIONS, "EF Adults and Adolescents", 6)

    sections = [
        ScoreRule(id=key, label=label, domain=label)
        for key, label in SEVERITY_SECTIONS
    ]

    total = ScoreRule(
        id="total",
        label="Total Score",
        scores=[key for key, _ in SEVERITY_SECTIONS],
        min_answered=5,
    )

    return ScoringCard(
        questions=base,
        scores=sections + [total],
        primary_score="total",
        standing_notice=(
            "Section scores are reported as figures. The interpretation ranges "
            "supplied for this instrument name individual sections and do not fit "
            "either the sections or the total, so none is printed until they are "
            "confirmed. Read the profile across sections rather than the total."
        ),
    )


# Executive Functioning Assessment (Ages 3-10), parent version: which questions
# make up each section, from the document's "For clinician use only" key.
AGES_3_10_SECTIONS = [
    ("working_memory", "Working Memory", (2, 6, 9, 11, 16, 18, 20, 26, 35, 40)),
    ("inhibitory_control", "Inhibitory Control", (7, 10, 14, 17, 21, 22, 25, 31, 34, 37)),
    ("cognitive_flexibility", "Cognitive Flexibility", (3, 5, 13, 15, 19, 24, 27, 29, 33, 36)),
    ("emotional_regulation", "Emotional Regulation", (1, 4, 8, 12, 23, 28, 30, 32, 38, 39)),
]


def ef_ages_3_10(questions: Sequence) -> ScoringCard:
    """Executive Functioning Assessment for Preschool and Elementary Children (Ages 3-10).

    Forty items on 0-3, parent report. The sections are interleaved rather than
    in blocks, so membership comes from the document's key, not position runs.
    Each section sums to 0-30 and the global score sums all forty to 0-120.

    The document also suggests comparing parent and clinician scores. It holds
    only the parent version, so that comparison is the clinician's reading of
    two results side by side, not a score of its own.
    """
    rules = _rules(questions, 40, "Executive Functioning Ages 3-10")
    _require_scale(rules, 0, 3, "Executive Functioning Ages 3-10")
    domain_of = {n: domain for domain, _, items in AGES_3_10_SECTIONS for n in items}
    if sorted(domain_of) != list(range(1, 41)):
        raise CardError("Executive Functioning Ages 3-10 sections must cover questions 1-40 once each.")
    rules = [
        QuestionRule(
            identifier=rule.identifier, domain=domain_of[position],
            scale_min=rule.scale_min, scale_max=rule.scale_max, options=rule.options,
        )
        for position, rule in enumerate(rules, start=1)
    ]

    sections = [
        ScoreRule(
            id=domain, label=label, domain=domain, min_answered=10,
            bands=_bands(
                ("minimal", "Minimal difficulties", 0, 10, "Typical for age."),
                ("mild", "Mild difficulties", 11, 17,
                 "Monitor and consider targeted support (e.g., classroom accommodations)."),
                ("significant", "Significant difficulties", 18, 30,
                 "Recommend further evaluation by a pediatric psychologist or neuropsychologist."),
            ),
        )
        for domain, label, _ in AGES_3_10_SECTIONS
    ]
    total = ScoreRule(
        id="total", label="Global Executive Functioning",
        scores=[section.id for section in sections], min_answered=4,
        bands=_bands(
            ("minimal", "Minimal difficulties", 0, 40,
             "Minimal executive functioning difficulties; likely age-appropriate."),
            ("mild-moderate", "Mild to moderate difficulties", 41, 70,
             "Consider behavioral interventions or educational supports."),
            ("significant", "Significant difficulties", 71, 120,
             "Recommend comprehensive assessment for conditions like ADHD, autism spectrum "
             "disorder, or developmental delays."),
        ),
    )
    return ScoringCard(questions=rules, scores=sections + [total], primary_score="total")


BUILDERS = {
    "efaa": efaa,
    "ef_severity_scale": ef_severity_scale,
    "ef_adults_adolescents": ef_adults_adolescents,
    "ef_ages_3_10": ef_ages_3_10,
}
