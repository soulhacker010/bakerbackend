"""Scoring cards for the three perinatal screeners.

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
from .card import CLINICIAN, PATIENT, URGENT, FlagRule, QuestionRule, ScoreRule, ScoringCard


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
                 "Urgent referral to a psychiatrist. Assess for generalized anxiety or panic disorder."),
            ),
        ),
        ScoreRule(
            id="stress", label="Stress", domain="stress", min_answered=5,
            bands=_bands(
                ("low", "Low", 0, 5,
                 "Provide education on managing parenting stress and role transitions."),
                ("moderate", "Moderate", 6, 10,
                 "Refer to a therapist for stress management or parenting-focused counseling."),
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
                 "Refer to a therapist or sleep specialist for behavioral interventions."),
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
                 "Urgent referral to a psychiatrist. Assess for panic or generalized anxiety disorder."),
            ),
        ),
        ScoreRule(
            id="ocd", label="Obsessive-Compulsive", domain="ocd", min_answered=4,
            bands=_bands(
                ("low", "Low", 0, 4,
                 "Monitor for symptom escalation. Provide education on OCD symptoms."),
                ("moderate", "Moderate", 5, 8,
                 "Refer to a therapist specializing in OCD for exposure and response prevention."),
                ("high", "High", 9, 12, "Urgent referral for specialist OCD treatment."),
            ),
        ),
        ScoreRule(
            id="eating", label="Eating", domain="eating", min_answered=4,
            bands=_bands(
                ("low", "Low", 0, 4, "Monitor eating habits and provide nutritional counseling."),
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
                 "Urgent psychiatric referral for mood stabilization and safety planning."),
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
                 "Monitor for functional impairments. Provide organizational strategies."),
                ("moderate", "Moderate", 3, 4,
                 "Refer to a psychologist for ADHD assessment and behavioral strategies."),
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


# Postpartum Mental Health Screener: the items the document weights above 1x.
POSTPARTUM_WEIGHTS = {2: 1.5, 4: 1.5, 6: 1.5, 11: 1.5, 15: 1.5, 19: 1.5,
                      21: 2.0, 22: 2.0, 23: 2.0, 24: 2.0, 25: 2.0}


def postpartum_mothers(questions: Sequence) -> ScoringCard:
    """Postpartum Mental Health Screener (Weighted), for new mothers.

    Twenty-five items on 0-3 in three sections: depression 1-10, anxiety 11-20
    and psychosis 21-25. Items 2, 4, 6, 11, 15 and 19 count 1.5x and the five
    psychosis items 2x, so depression and anxiety run 0-34.5, psychosis 0-30
    and the total 0-99, as the document's own arithmetic states. Its heading
    for depression says 0-36; its sum and its interpretation both say 34.5,
    which is what the weights produce.

    The weights put scores on half points, and the document's ranges stop at
    whole ones (0-8, then 9-17), leaving 8.5 in neither. Joe settled the same
    question for the Mental Skills Screener on 16 October 2026: "Anything up
    until the minimum threshold of the next level stays below." So 8.5 reads
    Minimal and each range runs up to the next one's start.

    Psychosis items count 2x, so that score only lands on even numbers; its
    ranges of 0, 2-8 and 10-30 leave nothing reachable uncovered.
    """
    rules = _sequential_domains(
        _rules(questions, 25, "Postpartum Mothers"),
        [("depression", 10), ("anxiety", 10), ("psychosis", 5)],
    )
    _require_scale(rules, 0, 3, "Postpartum Mothers")
    rules = [
        QuestionRule(
            identifier=rule.identifier, domain=rule.domain,
            weight=POSTPARTUM_WEIGHTS.get(position, 1.0),
            scale_min=rule.scale_min, scale_max=rule.scale_max,
            options=rule.options,
        )
        for position, rule in enumerate(rules, start=1)
    ]

    sections = [
        ScoreRule(
            id="depression", label="Depression", domain="depression",
            min_answered=10, granularity=0.5, precision=1,
            bands=_bands(
                ("minimal", "Minimal", 0, 8.5,
                 "Focus on self-care (rest, nutrition, social support)."),
                ("mild", "Mild", 9, 17.5,
                 "Consider joining a support group or speaking with a therapist."),
                ("moderate", "Moderate", 18, 26.5,
                 "Recommend consulting a therapist and possibly a psychiatrist."),
                ("severe", "Severe", 27, 34.5,
                 "Seek an urgent psychiatric evaluation and therapy."),
            ),
        ),
        ScoreRule(
            id="anxiety", label="Anxiety", domain="anxiety",
            min_answered=10, granularity=0.5, precision=1,
            bands=_bands(
                ("minimal", "Minimal", 0, 8.5,
                 "Practice self-care (mindfulness, relaxation techniques)."),
                ("mild", "Mild", 9, 17.5,
                 "Consider therapy or stress-reduction strategies."),
                ("moderate", "Moderate", 18, 26.5,
                 "Recommend consulting a therapist and possibly a psychiatrist."),
                ("severe", "Severe", 27, 34.5,
                 "Seek an urgent psychiatric evaluation and therapy."),
            ),
        ),
        ScoreRule(
            id="psychosis", label="Psychosis", domain="psychosis",
            min_answered=5, granularity=2, precision=1,
            bands=_bands(
                ("none", "No symptoms", 0, 0, "No action needed."),
                ("mild", "Mild", 2, 8, "Consult a therapist immediately for evaluation."),
                ("moderate-severe", "Moderate to Severe", 10, 30,
                 "Seek an urgent psychiatric evaluation."),
            ),
        ),
    ]

    total = ScoreRule(
        id="total", label="Total Wellness Score",
        scores=[section.id for section in sections],
        min_answered=3, granularity=0.5, precision=1,
        bands=_bands(
            ("good", "Good overall wellness", 0, 24.5, "Continue self-care practices."),
            ("mild", "Mild concerns", 25, 49.5,
             "Consider therapy or support groups for additional support."),
            ("moderate", "Moderate concerns", 50, 74.5,
             "Recommend therapy and possibly a psychiatric consultation."),
            ("severe", "Severe concerns", 75, 99,
             "Seek an urgent psychiatric evaluation and therapy."),
        ),
    )

    harm_item = rules[5].identifier       # 6. Have you thought about harming yourself?
    intrusive_item = rules[20].identifier  # 21. Disturbing thoughts of harming yourself or your baby

    # The document directs immediate contact on either item at 1 or higher,
    # whatever the totals. Weighted at 1.5x and 2x they still barely move a
    # 0-99 total, so only a flag of their own can carry this.
    return ScoringCard(
        questions=rules,
        scores=sections + [total],
        primary_score="total",
        flags=[
            FlagRule(
                id="harm-self",
                message="Question 6 (thoughts of harming herself) was answered 1 or higher. "
                        "The instrument directs that she contact a healthcare provider "
                        "immediately, whatever the total score.",
                severity=URGENT, audience=CLINICIAN,
                questions=[harm_item], operator=">=", value=1,
            ),
            FlagRule(
                id="harm-self-respondent",
                message="You indicated thoughts of harming yourself. Please contact your "
                        "healthcare provider straight away. If you are in immediate danger, "
                        "contact your local emergency services.",
                severity=URGENT, audience=PATIENT,
                questions=[harm_item], operator=">=", value=1,
            ),
            FlagRule(
                id="intrusive-harm",
                message="Question 21 (disturbing thoughts of harming herself or her baby that "
                        "feel out of her control) was answered 1 or higher. The instrument "
                        "directs that she contact a healthcare provider immediately.",
                severity=URGENT, audience=CLINICIAN,
                questions=[intrusive_item], operator=">=", value=1,
            ),
            FlagRule(
                id="intrusive-harm-respondent",
                message="You indicated disturbing thoughts of harming yourself or your baby. "
                        "Please contact your healthcare provider straight away. If you are in "
                        "immediate danger, contact your local emergency services.",
                severity=URGENT, audience=PATIENT,
                questions=[intrusive_item], operator=">=", value=1,
            ),
        ],
    )


BUILDERS = {
    "postpartum_fathers": postpartum_fathers,
    "expectant_mothers": expectant_mothers,
    "postpartum_mothers": postpartum_mothers,
}
