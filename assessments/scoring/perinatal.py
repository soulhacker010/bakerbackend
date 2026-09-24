"""Scoring cards for the two perinatal screeners.

Both are Baker Street's own instruments and both carry a section that, on its
own, directs immediate action. That is the whole reason the flag mechanism
exists: a single endorsed item can matter more than the total it barely moves.

Figures are taken from the instrument documents. Where the 2026 spreadsheet
disagrees with a document, the disagreement is recorded in the builder's
docstring and the document is followed.
"""
from __future__ import annotations

from typing import Sequence

from .baker_street import _bands, _require_scale, _rules, _sequential_domains
from .card import CLINICIAN, URGENT, FlagRule, ScoreRule, ScoringCard


def postpartum_fathers(questions: Sequence) -> ScoringCard:
    """Mental Health Screener for New and Postpartum Fathers.

    Twenty items on 0-3 across four sections, total 0-60.

    Against the 2026 spreadsheet, which records five subscales: the document
    defines four, and its own arithmetic agrees (6 + 5 + 5 + 4 = 20, and
    20 x 3 = 60). The document is followed.
    """
    rules = _sequential_domains(
        _rules(questions, 20, "Postpartum Fathers"),
        [("depression", 6), ("anxiety", 5), ("stress", 5), ("sleep", 4)],
    )
    _require_scale(rules, 0, 3, "Postpartum Fathers")

    sections = [
        ScoreRule(
            id="depression", label="Depression and Mood", domain="depression", min_answered=6,
            bands=_bands(
                ("low", "Low", 0, 6,
                 "Monitor with routine check-ins. Provide resources on paternal mental health."),
                ("moderate", "Moderate", 7, 12,
                 "Refer to a therapist for CBT or interpersonal therapy. Consider father-focused support groups."),
                ("high", "High", 13, 18,
                 "Urgent referral to a psychiatrist. Consider medication evaluation and therapy. Screen for suicidal ideation."),
            ),
        ),
        ScoreRule(
            id="anxiety", label="Anxiety and Worry", domain="anxiety", min_answered=5,
            bands=_bands(
                ("low", "Low", 0, 5,
                 "Offer relaxation techniques and stress management resources tailored for fathers."),
                ("moderate", "Moderate", 6, 10,
                 "Refer for CBT or anxiety-focused therapy. Consider mindfulness-based interventions."),
                ("high", "High", 11, 15,
                 "Urgent referral to a psychiatrist. Assess for generalised anxiety or panic disorder."),
            ),
        ),
        ScoreRule(
            id="stress", label="Stress", domain="stress", min_answered=5,
            bands=_bands(
                ("low", "Low", 0, 5,
                 "Provide education on managing parenting stress and role transitions."),
                ("moderate", "Moderate", 6, 10,
                 "Refer to a therapist for stress management or parenting-focused counselling."),
                ("high", "High", 11, 15,
                 "Urgent referral. Assess the impact of stress on functioning and family relationships."),
            ),
        ),
        ScoreRule(
            id="sleep", label="Sleep Quality", domain="sleep", min_answered=4,
            bands=_bands(
                ("low", "Low", 0, 4,
                 "Monitor sleep patterns and provide sleep hygiene education."),
                ("moderate", "Moderate", 5, 8,
                 "Refer to a therapist or sleep specialist for behavioural interventions."),
                ("high", "High", 9, 12,
                 "Urgent referral to a psychiatrist or sleep specialist."),
            ),
        ),
    ]

    total = ScoreRule(
        id="total", label="Total Score",
        scores=[section.id for section in sections],
        min_answered=4,
        bands=_bands(
            ("low", "Low Risk", 0, 20,
             "Minimal symptoms. Monitor and provide psychoeducation on mental health during the postpartum period."),
            ("moderate", "Moderate Risk", 21, 40,
             "Possible mental health concerns. Refer to a mental health professional for further assessment."),
            ("high", "High Risk", 41, 60,
             "Significant symptoms requiring urgent attention. Immediate referral for comprehensive evaluation."),
        ),
    )

    return ScoringCard(
        questions=rules,
        scores=sections + [total],
        primary_score="total",
        flags=[FlagRule(
            id="depression-high",
            message="Depression and Mood is in the high range. The instrument directs that "
                    "suicidal ideation be screened for.",
            severity=URGENT, audience=CLINICIAN,
            score_id="depression", operator=">=", value=13,
        )],
    )


def expectant_mothers(questions: Sequence) -> ScoringCard:
    """Expectant Mothers Mental Health Screener.

    Twenty-five items on 0-3 across seven sections, total 0-75.

    Two disagreements with the 2026 spreadsheet. It records eight subscales where
    the document defines seven, and its rubric lists the top response as 4 where
    the document says 3. The document is followed on both: 5 + 5 + 4 + 4 + 3 + 2 + 2
    is 25 questions, and 25 x 3 is the stated total of 75.
    """
    rules = _sequential_domains(
        _rules(questions, 25, "Expectant Mothers"),
        [("depression", 5), ("anxiety", 5), ("ocd", 4), ("eating", 4),
         ("mood", 3), ("suicidal", 2), ("adhd", 2)],
    )
    _require_scale(rules, 0, 3, "Expectant Mothers")

    sections = [
        ScoreRule(
            id="depression", label="Depression", domain="depression", min_answered=5,
            bands=_bands(
                ("low", "Low", 0, 5,
                 "Monitor with routine prenatal care. Provide resources on perinatal mental health."),
                ("moderate", "Moderate", 6, 10,
                 "Refer to a therapist for CBT or interpersonal therapy. Monitor closely."),
                ("high", "High", 11, 15,
                 "Urgent referral to a psychiatrist. Screen for suicidal ideation."),
            ),
        ),
        ScoreRule(
            id="anxiety", label="Anxiety", domain="anxiety", min_answered=5,
            bands=_bands(
                ("low", "Low", 0, 5, "Offer relaxation techniques and stress management resources."),
                ("moderate", "Moderate", 6, 10, "Refer for CBT or anxiety-focused therapy."),
                ("high", "High", 11, 15,
                 "Urgent referral to a psychiatrist. Assess for panic or generalised anxiety disorder."),
            ),
        ),
        ScoreRule(
            id="ocd", label="Obsessive-Compulsive", domain="ocd", min_answered=4,
            bands=_bands(
                ("low", "Low", 0, 4,
                 "Monitor for symptom escalation. Provide education on OCD symptoms."),
                ("moderate", "Moderate", 5, 8,
                 "Refer to a therapist specialising in OCD for exposure and response prevention."),
                ("high", "High", 9, 12, "Urgent referral for specialist OCD treatment."),
            ),
        ),
        ScoreRule(
            id="eating", label="Eating", domain="eating", min_answered=4,
            bands=_bands(
                ("low", "Low", 0, 4, "Monitor eating habits and provide nutritional counselling."),
                ("moderate", "Moderate", 5, 8,
                 "Refer to a therapist with expertise in eating disorders. Coordinate with a dietitian."),
                ("high", "High", 9, 12,
                 "Urgent referral to a multidisciplinary team for eating disorder treatment."),
            ),
        ),
        ScoreRule(
            id="mood", label="Mood", domain="mood", min_answered=3,
            bands=_bands(
                ("low", "Low", 0, 3, "Monitor for mood fluctuations, common in pregnancy."),
                ("moderate", "Moderate", 4, 6,
                 "Refer to a psychiatrist to assess for bipolar disorder or mood instability."),
                ("high", "High", 7, 9,
                 "Urgent psychiatric referral for mood stabilisation and safety planning."),
            ),
        ),
        ScoreRule(
            id="suicidal", label="Suicidal Ideation / History", domain="suicidal", min_answered=2,
            bands=_bands(
                ("none", "None", 0, 0, "Continue routine monitoring."),
                ("low-moderate", "Low to Moderate", 1, 3,
                 "Immediate safety assessment by a mental health professional. Develop a safety plan."),
                ("high", "High", 4, 6,
                 "Urgent referral to a crisis intervention team or psychiatrist. Ensure immediate safety measures."),
            ),
        ),
        ScoreRule(
            id="adhd", label="ADHD", domain="adhd", min_answered=2,
            bands=_bands(
                ("low", "Low", 0, 2,
                 "Monitor for functional impairments. Provide organisational strategies."),
                ("moderate", "Moderate", 3, 4,
                 "Refer to a psychologist for ADHD assessment and behavioural strategies."),
                ("high", "High", 5, 6,
                 "Refer to a psychiatrist for comprehensive evaluation, considering pregnancy risks."),
            ),
        ),
    ]

    total = ScoreRule(
        id="total", label="Total Score",
        scores=[section.id for section in sections],
        min_answered=7,
        bands=_bands(
            ("low", "Low Risk", 0, 25,
             "Minimal symptoms. Monitor and provide psychoeducation on mental health during pregnancy."),
            ("moderate", "Moderate Risk", 26, 50,
             "Possible mental health concerns. Refer to a mental health professional for further assessment."),
            ("high", "High Risk", 51, 75,
             "Significant symptoms requiring urgent attention. Immediate referral for comprehensive evaluation."),
        ),
    )

    return ScoringCard(
        questions=rules,
        scores=sections + [total],
        primary_score="total",
        flags=[
            # The instrument directs an immediate safety assessment at any score
            # above zero here. It has to fire on its own: two items out of
            # twenty-five barely move the total, so a total-only reading would
            # show "Low Risk" over an endorsed suicidal ideation item.
            FlagRule(
                id="suicidal-any",
                message="Suicidal ideation was endorsed. The instrument directs an immediate "
                        "safety assessment and a safety plan, whatever the total score.",
                severity=URGENT, audience=CLINICIAN,
                score_id="suicidal", operator=">=", value=1,
            ),
            FlagRule(
                id="suicidal-high",
                message="Suicidal ideation is in the high range. Urgent referral to a crisis "
                        "intervention team or psychiatrist; ensure immediate safety measures.",
                severity=URGENT, audience=CLINICIAN,
                score_id="suicidal", operator=">=", value=4,
            ),
        ],
    )


BUILDERS = {
    "postpartum_fathers": postpartum_fathers,
    "expectant_mothers": expectant_mothers,
}
