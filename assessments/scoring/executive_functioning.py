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


BUILDERS = {"efaa": efaa}
