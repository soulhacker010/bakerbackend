"""Scoring engine tests, built from the client's own instruments.

Each card below mirrors a real document. The expected numbers are taken from the
scoring section of that document, so if the engine drifts, these fail rather than
the drift reaching a clinician.
"""
from django.test import SimpleTestCase

from assessments.scoring import (
    AVERAGE,
    Band,
    CardError,
    CLINICIAN,
    FlagRule,
    INSUFFICIENT_DATA,
    OK,
    PATIENT,
    QuestionRule,
    ScoreRule,
    ScoringCard,
    THRESHOLD_COUNT,
    Transform,
    URGENT,
    score_assessment,
)


# --------------------------------------------------------------------------- #
# Mental Health Quick-Check: 20 items, 0-3, one total
# --------------------------------------------------------------------------- #

def quick_check_card():
    questions = [
        QuestionRule(identifier=f"q{i}", domain="general", scale_max=3)
        for i in range(1, 21)
    ]
    total = ScoreRule(
        id="total",
        label="Total",
        domain="general",
        bands=[
            Band("level-1", "Level 1", 0, 15, "Managing well"),
            Band("level-2", "Level 2", 16, 30, "Some strain present"),
            Band("level-3", "Level 3", 31, 45, "Significant stress"),
            Band("level-4", "Level 4", 46, 60, "Serious concern"),
        ],
    )
    return ScoringCard(questions=questions, scores=[total])


class QuickCheckTests(SimpleTestCase):
    def test_all_twos_totals_forty_and_lands_in_level_three(self):
        answers = {f"q{i}": 2 for i in range(1, 21)}
        result = score_assessment(quick_check_card(), answers)
        total = result.score("total")
        self.assertEqual(total.value, 40)
        self.assertEqual(total.band_id, "level-3")
        self.assertEqual(total.max_possible, 60)

    def test_maximum_is_sixty(self):
        answers = {f"q{i}": 3 for i in range(1, 21)}
        total = score_assessment(quick_check_card(), answers).score("total")
        self.assertEqual(total.value, 60)
        self.assertEqual(total.band_id, "level-4")


# --------------------------------------------------------------------------- #
# Foot Health: sum of 15 items on 0-4, converted by (sum x 5) / 3 onto 0-100
# --------------------------------------------------------------------------- #

def foot_health_card():
    questions = [
        QuestionRule(identifier=f"f{i}", domain="foot", scale_max=4)
        for i in range(1, 16)
    ]
    total = ScoreRule(
        id="total",
        label="Foot Health Score",
        domain="foot",
        transform=Transform(kind="linear", multiply=5, divide=3),
        bands=[
            Band("mild", "Mild or none", 0, 24, "Follow up and preventative care will suffice"),
            Band("moderate", "Moderate", 25, 50, "Evaluation advised"),
            Band("significant", "Significant", 51, 100, "Urgent evaluation recommended"),
        ],
    )
    return ScoringCard(questions=questions, scores=[total])


class FootHealthTests(SimpleTestCase):
    def test_conversion_puts_a_raw_thirty_at_fifty(self):
        answers = {f"f{i}": 2 for i in range(1, 16)}
        total = score_assessment(foot_health_card(), answers).score("total")
        self.assertEqual(total.value, 50)
        self.assertEqual(total.band_id, "moderate")

    def test_raw_sixty_converts_to_the_documented_hundred(self):
        answers = {f"f{i}": 4 for i in range(1, 16)}
        total = score_assessment(foot_health_card(), answers).score("total")
        self.assertEqual(total.value, 100)
        self.assertEqual(total.band_id, "significant")


# --------------------------------------------------------------------------- #
# Postpartum: per-question weights and a critical item on question 6
# --------------------------------------------------------------------------- #

def postpartum_card():
    heavy = {"p2", "p4", "p6"}
    questions = [
        QuestionRule(
            identifier=f"p{i}",
            domain="depression",
            scale_max=3,
            weight=1.5 if f"p{i}" in heavy else 1.0,
        )
        for i in range(1, 11)
    ]
    depression = ScoreRule(
        id="depression",
        label="Depression",
        domain="depression",
        bands=[
            Band("minimal", "Minimal", 0, 8, "Focus on self-care"),
            Band("mild", "Mild", 9, 17, "Consider a support group"),
            Band("moderate", "Moderate", 18, 26, "Consult a therapist"),
            Band("severe", "Severe", 27, 34.5, "Seek an urgent psychiatric evaluation"),
        ],
    )
    critical = FlagRule(
        id="pp-q6",
        message="Contact a healthcare provider immediately.",
        severity=URGENT,
        audience="both",
        questions=["p6"],
        operator=">=",
        value=1,
    )
    return ScoringCard(questions=questions, scores=[depression], flags=[critical])


class PostpartumWeightingTests(SimpleTestCase):
    def test_documented_maximum_of_thirty_four_point_five(self):
        answers = {f"p{i}": 3 for i in range(1, 11)}
        result = score_assessment(postpartum_card(), answers)
        depression = result.score("depression")
        # 7 items x 3 plus 3 items x 4.5 = 21 + 13.5
        self.assertEqual(depression.value, 34.5)
        self.assertEqual(depression.band_id, "severe")

    def test_half_points_are_not_rounded_away(self):
        answers = {f"p{i}": 0 for i in range(1, 11)}
        answers["p2"] = 1          # weighted 1.5
        result = score_assessment(postpartum_card(), answers)
        self.assertEqual(result.score("depression").value, 1.5)

    def test_critical_item_fires_on_a_single_answer_with_everything_else_zero(self):
        answers = {f"p{i}": 0 for i in range(1, 11)}
        answers["p6"] = 1
        result = score_assessment(postpartum_card(), answers)
        # The total is far inside the "minimal" band, and the flag must fire anyway.
        self.assertEqual(result.score("depression").band_id, "minimal")
        self.assertEqual([f.id for f in result.flags], ["pp-q6"])
        self.assertEqual(result.flags[0].severity, URGENT)

    def test_critical_item_stays_quiet_at_zero(self):
        answers = {f"p{i}": 3 for i in range(1, 11)}
        answers["p6"] = 0
        result = score_assessment(postpartum_card(), answers)
        self.assertEqual(result.flags, [])


# --------------------------------------------------------------------------- #
# Sleep & Recovery: 15 scored items, 7 yes/no items that must never be counted
# --------------------------------------------------------------------------- #

def hpsrs_card():
    scored = [
        QuestionRule(identifier=f"s{i}", domain="sleep", scale_max=3)
        for i in range(1, 16)
    ]
    # Same domain as the scored items on purpose: the only thing that may keep
    # these out of the total is scored=False, so the flag itself is under test.
    red_flags = [
        QuestionRule(identifier=f"s{i}", domain="sleep", scored=False)
        for i in range(16, 23)
    ]
    overall = ScoreRule(
        id="overall",
        label="Overall",
        domain="sleep",
        bands=[
            Band("low", "Low Concern", 0, 8, ""),
            Band("elevated", "Elevated Concern", 9, 17, ""),
            Band("high", "High Concern", 18, 26, ""),
            Band("very-high", "Very High Concern", 27, 45, ""),
        ],
    )
    flag = FlagRule(
        id="sleep-red-flag",
        message="A yes response may indicate the need for additional evaluation "
                "even when the overall score is relatively low.",
        severity="review",
        audience=CLINICIAN,
        questions=[f"s{i}" for i in range(16, 23)],
        operator="==",
        value="yes",
        match="any",
    )
    return ScoringCard(questions=scored + red_flags, scores=[overall], flags=[flag])


class UnscoredQuestionTests(SimpleTestCase):
    def test_yes_no_items_never_reach_the_total(self):
        answers = {f"s{i}": 1 for i in range(1, 16)}
        answers.update({f"s{i}": "No" for i in range(16, 23)})
        result = score_assessment(hpsrs_card(), answers)
        overall = result.score("overall")
        self.assertEqual(overall.value, 15)
        self.assertEqual(overall.applicable, 15)
        self.assertEqual(result.flags, [])

    def test_a_single_yes_raises_a_flag_without_changing_the_score(self):
        answers = {f"s{i}": 1 for i in range(1, 16)}
        answers.update({f"s{i}": "No" for i in range(16, 23)})
        answers["s17"] = "Yes"
        result = score_assessment(hpsrs_card(), answers)
        self.assertEqual(result.score("overall").value, 15)
        self.assertEqual([f.id for f in result.flags], ["sleep-red-flag"])

    def test_flag_can_fire_while_the_score_sits_in_the_lowest_band(self):
        answers = {f"s{i}": 0 for i in range(1, 16)}
        answers.update({f"s{i}": "No" for i in range(16, 23)})
        answers["s20"] = "Yes"
        result = score_assessment(hpsrs_card(), answers)
        self.assertEqual(result.score("overall").band_id, "low")
        self.assertEqual(len(result.flags), 1)


# --------------------------------------------------------------------------- #
# Mental Skills: domain averages, then an average of those averages
# --------------------------------------------------------------------------- #

def mental_skills_card():
    questions = []
    for d in range(1, 9):
        for i in range(1, 6):
            questions.append(
                QuestionRule(identifier=f"d{d}i{i}", domain=f"domain{d}", scale_max=5)
            )
    domain_scores = [
        ScoreRule(id=f"domain{d}", label=f"Domain {d}", domain=f"domain{d}", method=AVERAGE)
        for d in range(1, 9)
    ]
    overall = ScoreRule(
        id="overall",
        label="Overall Mental Skills Index",
        scores=[f"domain{d}" for d in range(1, 9)],
        method=AVERAGE,
        bands=[
            Band("growth", "Priority growth area", 1, 2.99, ""),
            Band("developing", "Developing", 3, 3.99, ""),
            Band("strength", "Strength", 4, 5, ""),
        ],
    )
    return ScoringCard(questions=questions, scores=domain_scores + [overall])


class AverageOfAveragesTests(SimpleTestCase):
    def test_overall_is_the_mean_of_the_eight_domain_means(self):
        answers = {f"d{d}i{i}": 4 for d in range(1, 9) for i in range(1, 6)}
        result = score_assessment(mental_skills_card(), answers)
        self.assertEqual(result.score("domain1").value, 4.0)
        self.assertEqual(result.score("overall").value, 4.0)
        self.assertEqual(result.score("overall").band_id, "strength")

    def test_one_weak_domain_moves_the_index_but_not_the_others(self):
        answers = {f"d{d}i{i}": 5 for d in range(1, 9) for i in range(1, 6)}
        for i in range(1, 6):
            answers[f"d1i{i}"] = 1
        result = score_assessment(mental_skills_card(), answers)
        self.assertEqual(result.score("domain1").value, 1.0)
        self.assertEqual(result.score("domain2").value, 5.0)
        # (1 + 5*7) / 8
        self.assertEqual(result.score("overall").value, 4.5)


# --------------------------------------------------------------------------- #
# EFAA: six domains of eight, the last item of each reverse-scored
# --------------------------------------------------------------------------- #

EFAA_DOMAINS = [
    "working_memory", "cognitive_flexibility", "task_initiation",
    "emotional_regulation", "inhibition", "planning",
]


def efaa_card():
    questions = []
    number = 1
    for domain in EFAA_DOMAINS:
        for position in range(1, 9):
            questions.append(
                QuestionRule(
                    identifier=f"e{number}",
                    domain=domain,
                    scale_max=3,
                    reverse=(position == 8),   # items 8, 16, 24, 32, 40, 48
                    allow_na=True,
                )
            )
            number += 1
    domain_scores = [
        ScoreRule(
            id=domain,
            label=domain.replace("_", " ").title(),
            domain=domain,
            min_answered=5,
        )
        for domain in EFAA_DOMAINS
    ]
    total = ScoreRule(
        id="total",
        label="Total",
        scores=EFAA_DOMAINS,
        bands=[
            Band("minimal", "Minimal", 0, 28, ""),
            Band("mild", "Mild elevation", 29, 57, ""),
            Band("moderate", "Moderate elevation", 58, 86, ""),
            Band("significant", "Significant elevation", 87, 144, ""),
        ],
    )
    domain_flags = [
        FlagRule(
            id=f"{domain}-elevated",
            message=f"{domain.replace('_', ' ').title()} at or above 12 suggests "
                    "possible domain-specific difficulty.",
            severity="review",
            audience=CLINICIAN,
            score_id=domain,
            operator=">=",
            value=12,
        )
        for domain in EFAA_DOMAINS
    ]
    return ScoringCard(
        questions=questions,
        scores=domain_scores + [total],
        flags=domain_flags,
        standing_notice="Provisional scoring, awaiting pilot norms.",
    )


class ReverseScoringTests(SimpleTestCase):
    def test_answering_zero_everywhere_still_scores_the_reverse_items(self):
        answers = {f"e{i}": 0 for i in range(1, 49)}
        result = score_assessment(efaa_card(), answers)
        # Each domain's eighth item flips 0 to 3.
        self.assertEqual(result.score("working_memory").value, 3)
        self.assertEqual(result.score("total").value, 18)
        self.assertEqual(result.score("total").band_id, "minimal")

    def test_documented_maximum_of_one_hundred_and_forty_four(self):
        answers = {f"e{i}": 3 for i in range(1, 49)}
        for i in (8, 16, 24, 32, 40, 48):
            answers[f"e{i}"] = 0        # reversed, so zero is the worst answer
        result = score_assessment(efaa_card(), answers)
        self.assertEqual(result.score("total").value, 144)
        self.assertEqual(result.score("total").band_id, "significant")

    def test_domain_flag_fires_at_twelve(self):
        answers = {f"e{i}": 0 for i in range(1, 49)}
        for i in range(1, 5):
            answers[f"e{i}"] = 3        # working memory reaches 12 with the reverse item
        result = score_assessment(efaa_card(), answers)
        self.assertEqual(result.score("working_memory").value, 15)
        raised = [f.id for f in result.flags]
        self.assertIn("working_memory-elevated", raised)
        self.assertNotIn("inhibition-elevated", raised)

    def test_standing_notice_is_carried_into_the_result(self):
        answers = {f"e{i}": 1 for i in range(1, 49)}
        result = score_assessment(efaa_card(), answers)
        self.assertEqual(result.notice, "Provisional scoring, awaiting pilot norms.")


class NotApplicableTests(SimpleTestCase):
    def test_na_is_not_treated_as_zero(self):
        answers = {f"e{i}": 3 for i in range(1, 49)}
        answers["e1"] = "N/A"
        result = score_assessment(efaa_card(), answers)
        working_memory = result.score("working_memory")
        # Seven items answered, not eight, and the maximum drops with it.
        self.assertEqual(working_memory.answered, 7)
        self.assertEqual(working_memory.max_possible, 21)

    def test_a_domain_answered_almost_entirely_na_reports_insufficient_data(self):
        answers = {f"e{i}": 3 for i in range(1, 49)}
        for i in range(1, 8):
            answers[f"e{i}"] = "N/A"
        result = score_assessment(efaa_card(), answers)
        working_memory = result.score("working_memory")
        self.assertEqual(working_memory.status, INSUFFICIENT_DATA)
        self.assertIsNone(working_memory.value)

    def test_a_domain_that_cannot_be_calculated_does_not_raise_its_flag(self):
        answers = {f"e{i}": 3 for i in range(1, 49)}
        for i in range(1, 9):
            answers[f"e{i}"] = "N/A"
        result = score_assessment(efaa_card(), answers)
        self.assertNotIn("working_memory-elevated", [f.id for f in result.flags])


# --------------------------------------------------------------------------- #
# Return to Play: two answer scales, N/A out of the denominator, domains
# normalised onto 0-20 so the five make 0-100
# --------------------------------------------------------------------------- #

def return_to_play_card():
    # Domain 1, questions 9-13 on 0-4. Items 9-12 are reverse-scored: the
    # document states 4 = most favourable, but their answer options run the
    # other way, which the item flags confirm.
    pain = [
        QuestionRule(identifier=f"q{i}", domain="pain", scale_max=4,
                     reverse=(i != 13), allow_na=True)
        for i in range(9, 14)
    ]
    # Domain 4, questions 23-27 on 0-10, averaged.
    confidence = [
        QuestionRule(identifier=f"q{i}", domain="confidence", scale_max=10, allow_na=True)
        for i in range(23, 28)
    ]
    pain_score = ScoreRule(
        id="pain",
        label="Pain & Symptom Experience",
        domain="pain",
        transform=Transform(kind="normalize", to=20),
        min_answered=3,
    )
    confidence_score = ScoreRule(
        id="confidence",
        label="Performance Confidence",
        domain="confidence",
        method=AVERAGE,
        transform=Transform(kind="normalize", to=20),
        min_answered=3,
    )
    overall = ScoreRule(
        id="overall",
        label="Return-to-Play Readiness",
        scores=["pain", "confidence"],
        bands=[
            Band("significant", "Significant Reported Barriers", 0, 15.6, ""),
            Band("reduced", "Reduced Readiness", 15.7, 21.6, ""),
            Band("mixed", "Mixed Readiness", 21.7, 27.6, ""),
            Band("favourable", "Generally Favourable", 27.7, 33.6, ""),
            Band("higher", "Higher Reported Readiness", 33.7, 40, ""),
        ],
    )
    flags = [
        FlagRule(id="pain-barrier", message="Potential meaningful symptom-related barrier.",
                 score_id="pain", operator="<", value=15, severity="review"),
        FlagRule(id="confidence-barrier", message="Potential reduced confidence.",
                 score_id="confidence", operator="<", value=15, severity="review"),
    ]
    return ScoringCard(
        questions=pain + confidence,
        scores=[pain_score, confidence_score, overall],
        flags=flags,
        standing_notice="Provisional for pilot testing, not validated clinical cutoffs.",
    )


class ReturnToPlayTests(SimpleTestCase):
    def test_an_athlete_in_severe_pain_does_not_read_as_ready(self):
        """The bug found in the source document, pinned so it cannot come back.

        Answering the worst option on every pain item must produce the lowest
        possible domain score, not the highest.
        """
        answers = {f"q{i}": 4 for i in range(9, 13)}   # severe / extremely
        answers["q13"] = 0                             # completely out of control
        answers.update({f"q{i}": 10 for i in range(23, 28)})
        result = score_assessment(return_to_play_card(), answers)
        self.assertEqual(result.score("pain").value, 0)
        self.assertIn("pain-barrier", [f.id for f in result.flags])

    def test_an_athlete_with_no_symptoms_reaches_the_full_domain_score(self):
        answers = {f"q{i}": 0 for i in range(9, 13)}
        answers["q13"] = 4
        answers.update({f"q{i}": 10 for i in range(23, 28)})
        result = score_assessment(return_to_play_card(), answers)
        self.assertEqual(result.score("pain").value, 20)
        self.assertEqual(result.score("confidence").value, 20)
        self.assertEqual(result.score("overall").value, 40)
        self.assertEqual(result.score("overall").band_id, "higher")
        self.assertEqual(result.flags, [])

    def test_na_shrinks_the_denominator_rather_than_counting_as_zero(self):
        answers = {f"q{i}": 0 for i in range(9, 13)}
        answers["q13"] = 4
        answers.update({f"q{i}": 10 for i in range(23, 28)})
        answers["q25"] = "N/A"
        result = score_assessment(return_to_play_card(), answers)
        confidence = result.score("confidence")
        # Four applicable answers of 10 still average 10, so the domain stays 20.
        self.assertEqual(confidence.answered, 4)
        self.assertEqual(confidence.value, 20)

    def test_too_many_na_answers_report_insufficient_data(self):
        answers = {f"q{i}": 0 for i in range(9, 13)}
        answers["q13"] = 4
        answers.update({f"q{i}": "N/A" for i in range(23, 28)})
        result = score_assessment(return_to_play_card(), answers)
        confidence = result.score("confidence")
        self.assertEqual(confidence.status, INSUFFICIENT_DATA)
        # The overall still reports, built from the domain that could be calculated.
        self.assertEqual(result.score("overall").status, OK)


# --------------------------------------------------------------------------- #
# ASRS: no total score, a count of items meeting their own thresholds
# --------------------------------------------------------------------------- #

def asrs_card():
    # Part A: items 1-3 qualify at "sometimes" or above, items 4-6 at "often".
    lenient = frozenset({"2", "3", "4"})
    strict = frozenset({"3", "4"})
    questions = [
        QuestionRule(
            identifier=f"a{i}",
            domain="part_a",
            qualifying_values=lenient if i <= 3 else strict,
        )
        for i in range(1, 7)
    ]
    screen = ScoreRule(
        id="part_a",
        label="Part A Screen",
        domain="part_a",
        method=THRESHOLD_COUNT,
        positive_at=4,
        min_answered=6,
    )
    return ScoringCard(questions=questions, scores=[screen])


class ThresholdCountTests(SimpleTestCase):
    def test_four_qualifying_answers_make_a_positive_screen(self):
        answers = {"a1": "2", "a2": "2", "a3": "2", "a4": "3", "a5": "0", "a6": "0"}
        screen = score_assessment(asrs_card(), answers).score("part_a")
        self.assertEqual(screen.value, 4)
        self.assertTrue(screen.positive)

    def test_three_qualifying_answers_do_not(self):
        answers = {"a1": "2", "a2": "2", "a3": "2", "a4": "0", "a5": "0", "a6": "0"}
        screen = score_assessment(asrs_card(), answers).score("part_a")
        self.assertEqual(screen.value, 3)
        self.assertFalse(screen.positive)

    def test_each_item_is_judged_against_its_own_threshold(self):
        # "Sometimes" qualifies on items 1-3 but not on items 4-6.
        answers = {f"a{i}": "2" for i in range(1, 7)}
        screen = score_assessment(asrs_card(), answers).score("part_a")
        self.assertEqual(screen.value, 3)
        self.assertFalse(screen.positive)


# --------------------------------------------------------------------------- #
# Behaviour that protects against the bugs already seen on the live site
# --------------------------------------------------------------------------- #

class SafetyTests(SimpleTestCase):
    def test_free_text_containing_a_number_never_reaches_a_total(self):
        card = ScoringCard(
            questions=[
                QuestionRule(identifier="q1", domain="d", scale_max=3),
                QuestionRule(identifier="note", domain="d", scored=False),
            ],
            scores=[ScoreRule(id="total", label="Total", domain="d")],
        )
        result = score_assessment(card, {"q1": 2, "note": "about 3 times a week"})
        self.assertEqual(result.score("total").value, 2)

    def test_free_text_on_a_scored_question_contributes_nothing(self):
        """The live engine pulled the first number out of any string.

        A respondent typing "about 3 times a week" into a scored free-text box
        added 3 to their clinical total.
        """
        card = ScoringCard(
            questions=[
                QuestionRule(identifier="q1", domain="d", scale_max=3),
                QuestionRule(identifier="q2", domain="d", scale_max=3),
            ],
            scores=[ScoreRule(id="total", label="Total", domain="d")],
        )
        result = score_assessment(card, {"q1": 1, "q2": "about 3 times a week"})
        total = result.score("total")
        self.assertEqual(total.value, 1)
        self.assertEqual(total.answered, 1)

    def test_an_unparseable_answer_is_not_counted_as_zero(self):
        card = ScoringCard(
            questions=[
                QuestionRule(identifier="q1", domain="d", scale_max=3),
                QuestionRule(identifier="q2", domain="d", scale_max=3),
            ],
            scores=[ScoreRule(id="total", label="Total", domain="d")],
        )
        result = score_assessment(card, {"q1": 3, "q2": "dunno"})
        total = result.score("total")
        self.assertEqual(total.value, 3)
        self.assertEqual(total.answered, 1)

    def test_a_score_outside_every_band_reports_no_interpretation_rather_than_a_wrong_one(self):
        # This is the state three live assessments are in today. The engine must
        # not guess; the validator is what stops such a card being saved at all.
        card = ScoringCard(
            questions=[QuestionRule(identifier="q1", domain="d", scale_max=100)],
            scores=[
                ScoreRule(id="total", label="Total", domain="d",
                          bands=[Band("low", "Low", 0, 10, "")])
            ],
        )
        result = score_assessment(card, {"q1": 90})
        total = result.score("total")
        self.assertEqual(total.value, 90)
        self.assertIsNone(total.band_id)
        self.assertEqual(total.interpretation, "")

    def test_no_answers_at_all_produces_no_score(self):
        result = score_assessment(quick_check_card(), {})
        self.assertEqual(result.score("total").status, INSUFFICIENT_DATA)
        self.assertIsNone(result.score("total").value)


class CardValidationTests(SimpleTestCase):
    def test_reverse_without_a_scale_is_rejected(self):
        with self.assertRaises(CardError):
            QuestionRule(identifier="q1", reverse=True)

    def test_a_score_must_have_exactly_one_source(self):
        with self.assertRaises(CardError):
            ScoreRule(id="s", label="S", domain="d", questions=["q1"])

    def test_a_flag_cannot_watch_both_questions_and_a_score(self):
        with self.assertRaises(CardError):
            FlagRule(id="f", message="m", questions=["q1"], score_id="s", value=1)

    def test_scores_that_depend_on_each_other_are_rejected(self):
        card_questions = [QuestionRule(identifier="q1", domain="d", scale_max=3)]
        with self.assertRaises(CardError):
            ScoringCard(
                questions=card_questions,
                scores=[
                    ScoreRule(id="a", label="A", scores=["b"]),
                    ScoreRule(id="b", label="B", scores=["a"]),
                ],
            )

    def test_a_flag_pointing_at_an_unknown_question_is_rejected(self):
        with self.assertRaises(CardError):
            ScoringCard(
                questions=[QuestionRule(identifier="q1", domain="d", scale_max=3)],
                scores=[ScoreRule(id="total", label="Total", domain="d")],
                flags=[FlagRule(id="f", message="m", questions=["nope"], value=1)],
            )
