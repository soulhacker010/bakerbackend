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
    INFO,
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

    The instrument document gives two thresholds, not one:

        "A total score of two or greater is considered clinically significant."
        "If score is one or higher, seek further evaluation."

    Both are reported. A single positive answer is not a positive screen, but it
    is not nothing either, and reporting only the higher threshold would drop a
    direction the document states plainly.
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
            Band("negative", "No positive answers", 0, 0,
                 "No items endorsed."),
            Band("sub_threshold", "Below the clinical threshold", 1, 1,
                 "One positive answer. Below the threshold of two, but the "
                 "instrument directs that a score of one or higher is followed up."),
            Band("positive", "Positive screen", 2, 4,
                 "Two or more positive answers is considered clinically significant "
                 "and warrants further assessment."),
        ],
    )
    return ScoringCard(
        questions=rules,
        scores=[total],
        flags=[
            FlagRule(
                id="cage-positive",
                message="Two or more positive answers, which the instrument treats as "
                        "clinically significant. Further assessment for substance use "
                        "is indicated.",
                severity=REVIEW,
                audience=CLINICIAN,
                score_id="total",
                operator=">=",
                value=2,
            ),
            FlagRule(
                id="cage-seek-evaluation",
                message="At least one positive answer. The instrument directs that a "
                        "score of one or higher is followed up, even where it is below "
                        "the clinical threshold of two.",
                severity=INFO,
                audience=CLINICIAN,
                score_id="total",
                operator=">=",
                value=1,
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# PCL-5
# --------------------------------------------------------------------------- #

# The DSM-5 symptom clusters, as item ranges in the published order.
PCL5_CLUSTERS = [
    ("intrusion", "Intrusion (Cluster B)", 1, 5),
    ("avoidance", "Avoidance (Cluster C)", 6, 7),
    ("cognition_mood", "Negative alterations in cognitions and mood (Cluster D)", 8, 14),
    ("arousal", "Alterations in arousal and reactivity (Cluster E)", 15, 20),
]

# The published provisional cut-off. The guidance gives a range of 31-33 pending
# further validation; the lower end is used, and the band says so.
PCL5_CUTOFF = 31


def pcl5(questions: Sequence) -> ScoringCard:
    """PTSD Checklist for DSM-5.

    Twenty items on 0-4, giving a total of 0-80, reported alongside the four DSM-5
    symptom clusters.

    The live assessment carries the editor's default four-point frequency scale,
    so its total runs 0-60 and cannot be read against any published threshold: a
    respondent scoring 31 there has answered far more severely than one scoring 31
    on the real instrument. ``_check_scale`` refuses rather than scoring it anyway.

    Only the total carries a range. The published guidance gives a provisional
    cut-off for the total and none for individual clusters, so the clusters are
    reported as figures and the profile is left to be read.
    """
    rules = _rules(questions, 20, "PCL-5")
    _check_scale(rules, 0, 4, "PCL-5")

    by_cluster: List[QuestionRule] = []
    for index, rule in enumerate(rules, start=1):
        domain = next(
            key for key, _, first, last in PCL5_CLUSTERS if first <= index <= last
        )
        by_cluster.append(
            QuestionRule(
                identifier=rule.identifier,
                domain=domain,
                scale_min=rule.scale_min,
                scale_max=rule.scale_max,
                options=rule.options,
            )
        )

    clusters = [
        ScoreRule(id=key, label=label, domain=key)
        for key, label, _, _ in PCL5_CLUSTERS
    ]

    total = ScoreRule(
        id="total",
        label="PCL-5 Total",
        scores=[key for key, _, _, _ in PCL5_CLUSTERS],
        min_answered=len(PCL5_CLUSTERS),
        bands=[
            Band("below", "Below the provisional cut-off", 0, PCL5_CUTOFF - 1,
                 "Below the provisional cut-off of 31. Read alongside clinical "
                 "judgement; a low total does not rule out PTSD."),
            Band("at_or_above", "At or above the provisional cut-off", PCL5_CUTOFF, 80,
                 "At or above the provisional cut-off of 31, which the guidance gives "
                 "as 31-33 pending further validation. Indicates a structured "
                 "diagnostic interview, not a diagnosis in itself."),
        ],
    )

    return ScoringCard(
        questions=by_cluster,
        scores=clusters + [total],
        flags=[FlagRule(
            id="pcl5-cutoff",
            message="PCL-5 total is at or above the provisional cut-off of 31. The "
                    "guidance directs a structured diagnostic interview; the total is "
                    "not a diagnosis.",
            severity=REVIEW, audience=CLINICIAN,
            score_id="total", operator=">=", value=PCL5_CUTOFF,
        )],
        standing_notice=(
            "The PCL-5 cut-off is provisional. The guidance gives 31-33 pending "
            "further psychometric work, and directs that a positive screen leads to "
            "a structured diagnostic interview rather than a diagnosis."
        ),
    )


# --------------------------------------------------------------------------- #
# ASRS v1.1
# --------------------------------------------------------------------------- #

# Part A is the official screener: the first six items, each with its own
# threshold. Items 1-3 count from "Sometimes" upwards and items 4-6 only from
# "Often" upwards, which is what the shaded boxes on the paper form mean.
ASRS_PART_A_THRESHOLDS = {1: 2, 2: 2, 3: 2, 4: 3, 5: 3, 6: 3}
ASRS_POSITIVE_AT = 4

# The practice's own document states a different rule, directly under Part A:
#
#     "Threshold: A total score of 14 or more suggests a high probability of
#      adult ADHD."
#     "Part B (score separately)"
#
# Part A is six items on 0-4, so that threshold is 14 out of 24. It is not the
# same rule as the shaded boxes and the two can disagree: six items answered
# "Sometimes" totals 12 and counts three, so it is positive on neither; three at
# "Very Often" and three at "Rarely" totals 15 and counts three, so it is
# positive on the document's rule and negative on the official one.
ASRS_DOCUMENT_THRESHOLD = 14


def _labels_at_or_above(rule: QuestionRule, threshold: float) -> frozenset:
    """The answers on this question worth ``threshold`` or more.

    Read from the question's own options rather than written out here, because
    the wording differs between installations and the number is what matters.
    """
    if not rule.options:
        raise CardError(
            f"ASRS question {rule.identifier!r} has no answer options to count."
        )
    qualifying = {label for label, value in rule.options.items() if value >= threshold}
    if not qualifying:
        raise CardError(
            f"ASRS question {rule.identifier!r} offers no answer worth {threshold:g} "
            "or more; the published scale reaches 'Very Often'."
        )
    return frozenset(qualifying)


def asrs(questions: Sequence) -> ScoringCard:
    """Adult ADHD Self-Report Scale v1.1.

    Eighteen items on 0-4, with Part A the screening section and Part B, in the
    document's own words, "scored separately".

    Two rules are reported for Part A, because two exist and they can disagree:

    * the practice's document states "a total score of 14 or more suggests a high
      probability of adult ADHD", which is a sum out of 24. This is the headline,
      because it is the rule the practice wrote down.
    * the WHO screener counts items rather than summing them: an item counts only
      if answered at or above its own threshold, and four of six is positive. It
      is reported beside the total rather than dropped, so a reader can see when
      the two point different ways.

    The live assessment carries the editor's default four-point scale, which has
    no "Very Often" at all. Three of the six Part A items only count from "Often"
    upwards, so on that scale the screener cannot reach its own threshold — it is
    not merely inaccurate, it cannot return a positive screen. ``_check_scale``
    refuses it.

    Part B is reported as a figure. Whether a dimensional total should be reported
    alongside the screen is a question for the practice, so none is claimed here.
    """
    rules = _rules(questions, 18, "ASRS")
    _check_scale(rules, 0, 4, "ASRS")

    prepared: List[QuestionRule] = []
    for index, rule in enumerate(rules, start=1):
        part_a = index in ASRS_PART_A_THRESHOLDS
        prepared.append(
            QuestionRule(
                identifier=rule.identifier,
                domain="part_a" if part_a else "part_b",
                scale_min=rule.scale_min,
                scale_max=rule.scale_max,
                options=rule.options,
                qualifying_values=(
                    _labels_at_or_above(rule, ASRS_PART_A_THRESHOLDS[index])
                    if part_a else None
                ),
            )
        )

    return ScoringCard(
        questions=prepared,
        scores=[
            ScoreRule(
                id="part_a", label="Part A total", domain="part_a",
                bands=[
                    Band("below", "Below the threshold", 0, ASRS_DOCUMENT_THRESHOLD - 1,
                         "Below the stated threshold of 14."),
                    Band("at_or_above", "At or above the threshold",
                         ASRS_DOCUMENT_THRESHOLD, 24,
                         "At or above the stated threshold of 14, which the instrument "
                         "document reads as a high probability of adult ADHD. A screen, "
                         "not a diagnosis."),
                ],
            ),
            ScoreRule(
                id="part_a_screen", label="Part A screen (WHO item count)",
                questions=[r.identifier for r in prepared if r.domain == "part_a"],
                method=THRESHOLD_COUNT, positive_at=ASRS_POSITIVE_AT,
            ),
            ScoreRule(id="part_b", label="Part B symptoms", domain="part_b"),
        ],
        flags=[
            FlagRule(
                id="asrs-total",
                message="Part A total is at or above 14, the threshold this "
                        "instrument document states for a high probability of adult "
                        "ADHD. A screen, not a diagnosis.",
                severity=REVIEW, audience=CLINICIAN,
                score_id="part_a", operator=">=", value=ASRS_DOCUMENT_THRESHOLD,
            ),
            FlagRule(
                id="asrs-screen",
                message="Four or more Part A items were answered at or above their own "
                        "threshold, which is the WHO screener's positive result. Read "
                        "alongside the Part A total; the two rules can disagree.",
                severity=INFO, audience=CLINICIAN,
                score_id="part_a_screen", operator=">=", value=ASRS_POSITIVE_AT,
            ),
        ],
        primary_score="part_a",
        standing_notice=(
            "Part A is reported two ways. The total is scored against the threshold "
            "of 14 stated in this instrument's documentation; the screen counts items "
            "answered at or above their own threshold, which is the WHO rule, and is "
            "positive at four of six. The two can disagree, and where they do the "
            "profile is worth reading rather than either figure alone. Part B is "
            "scored separately and carries no stated cut-off. Neither result is a "
            "diagnosis."
        ),
    )


BUILDERS = {
    "phq9": phq9,
    "gad7": gad7,
    "cage_aid": cage_aid,
    "pcl5": pcl5,
    "asrs": asrs,
}
