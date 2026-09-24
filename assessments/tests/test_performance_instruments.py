"""The performance and leadership instruments.

Two of these reproduce a problem in their own document rather than papering over
it. Those tests exist so the problem stays visible until the client decides what
the figure should be.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.performance import (
    executive_self_assessment,
    mental_skills,
    sleep_and_recovery,
)
from assessments.scoring.validation import ERROR, WARNING, achievable_range, validate_card

ZERO_THREE = ["0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often"]
ONE_FIVE = [
    "Not at All Competent (1)", "Somewhat Competent (2)", "Moderately Competent (3)",
    "Very Competent (4)", "Highly Competent (5)",
]
YES_NO = ["No", "Yes"]


def questions(count, options, start=1):
    return [
        AssessmentQuestion(
            identifier=f"q{i}", order=i, text=f"item {i}",
            response_type=AssessmentQuestion.ResponseType.LIKERT,
            config={"options": list(options)}, domain="general",
        )
        for i in range(start, start + count)
    ]


class SleepAndRecoveryTests(SimpleTestCase):
    def setUp(self):
        self.card = sleep_and_recovery(questions(15, ZERO_THREE) + questions(7, YES_NO, start=16))

    def answers(self, scored_values, flags=None):
        payload = {f"q{i}": ZERO_THREE[v] for i, v in enumerate(scored_values, 1)}
        payload.update({f"q{i}": (flags or {}).get(i, "No") for i in range(16, 23)})
        return payload

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_only_the_first_fifteen_questions_are_scored(self):
        self.assertEqual(achievable_range(self.card)["overall"], (0, 45))
        overall = score_assessment(self.card, self.answers([3] * 15)).score("overall")
        self.assertEqual(overall.value, 45)
        self.assertEqual(overall.applicable, 15)

    def test_the_documented_section_ranges(self):
        ranges = achievable_range(self.card)
        self.assertEqual(ranges["quantity"], (0, 6))
        self.assertEqual(ranges["continuity"], (0, 9))
        self.assertEqual(ranges["restoration"], (0, 9))
        self.assertEqual(ranges["circadian"], (0, 6))
        self.assertEqual(ranges["performance"], (0, 15))

    def test_a_red_flag_answered_yes_never_moves_the_score(self):
        without = score_assessment(self.card, self.answers([1] * 15))
        with_flags = score_assessment(
            self.card, self.answers([1] * 15, flags={i: "Yes" for i in range(16, 23)})
        )
        self.assertEqual(without.score("overall").value, 15)
        self.assertEqual(with_flags.score("overall").value, 15)

    def test_a_single_yes_flags_while_the_score_sits_in_the_lowest_band(self):
        """The case the document warns about in as many words."""
        result = score_assessment(self.card, self.answers([0] * 15, flags={17: "Yes"}))
        self.assertEqual(result.score("overall").value, 0)
        self.assertEqual(result.score("overall").band_id, "low")
        self.assertEqual([f.id for f in result.flags], ["sleep-red-flag"])

    def test_no_flag_when_every_red_flag_is_no(self):
        self.assertEqual(score_assessment(self.card, self.answers([3] * 15)).flags, [])

    def test_the_standing_notice_is_carried(self):
        result = score_assessment(self.card, self.answers([1] * 15))
        self.assertIn("not be represented as clinically validated", result.notice)

    def test_the_wrong_number_of_questions_is_refused(self):
        with self.assertRaises(ValueError):
            sleep_and_recovery(questions(15, ZERO_THREE))


class ExecutiveSelfAssessmentTests(SimpleTestCase):
    def setUp(self):
        self.card = executive_self_assessment(questions(24, ONE_FIVE))

    def answers(self, values):
        return {f"q{i}": ONE_FIVE[v - 1] for i, v in enumerate(values, 1)}

    def test_the_scale_starts_at_one_so_the_lowest_total_is_twenty_four(self):
        self.assertEqual(achievable_range(self.card)["total"], (24, 120))

    def test_each_dimension_runs_three_to_fifteen(self):
        ranges = achievable_range(self.card)
        self.assertEqual(ranges["goal_setting"], (3, 15))
        self.assertEqual(ranges["self_monitoring"], (3, 15))

    def test_everything_at_five_reaches_one_hundred_and_twenty(self):
        result = score_assessment(self.card, self.answers([5] * 24))
        self.assertEqual(result.score("total").value, 120)
        self.assertEqual(result.score("total").band_id, "excellent")

    def test_everything_at_one_reaches_the_documented_floor(self):
        result = score_assessment(self.card, self.answers([1] * 24))
        self.assertEqual(result.score("total").value, 24)
        self.assertEqual(result.score("total").band_id, "needs-improvement")

    def test_the_unreachable_poor_band_is_reported_but_does_not_block_saving(self):
        """A problem in the source document, left visible rather than adjusted.

        The document defines "0-23 (Poor)", but twenty-four items that cannot
        score below 1 put the floor at 24. The band can never be reached.
        """
        problems = validate_card(self.card)
        self.assertTrue(
            any(p.severity == WARNING and "can never be reached" in p.message for p in problems),
            [p.message for p in problems],
        )
        self.assertEqual([p for p in problems if p.severity == ERROR], [])

    def test_the_wrong_answer_scale_is_refused(self):
        with self.assertRaises(CardError):
            executive_self_assessment(questions(24, ZERO_THREE))


class MentalSkillsTests(SimpleTestCase):
    def setUp(self):
        self.card = mental_skills(questions(40, ONE_FIVE))

    def answers(self, values):
        return {f"q{i}": ONE_FIVE[v - 1] for i, v in enumerate(values, 1)}

    def test_a_domain_score_is_the_average_of_its_five_items(self):
        values = [4] * 5 + [1] * 35
        result = score_assessment(self.card, self.answers(values))
        self.assertEqual(result.score("domain1").value, 4.0)
        self.assertEqual(result.score("domain2").value, 1.0)

    def test_the_overall_index_is_the_average_of_the_eight_domain_averages(self):
        # Seven domains at 5.0 and one at 1.0 -> (5*7 + 1) / 8 = 4.5
        values = [1] * 5 + [5] * 35
        result = score_assessment(self.card, self.answers(values))
        self.assertEqual(result.score("domain1").value, 1.0)
        self.assertEqual(result.score("overall").value, 4.5)

    def test_the_index_runs_one_to_five_not_forty_to_two_hundred(self):
        self.assertEqual(achievable_range(self.card)["overall"], (1, 5))

    def test_a_domain_average_lands_on_fifths(self):
        values = [5, 5, 5, 5, 4] + [1] * 35     # 24 / 5
        result = score_assessment(self.card, self.answers(values))
        self.assertEqual(result.score("domain1").value, 4.8)

    def test_the_gap_between_three_point_nine_and_four_is_reported(self):
        """A problem in the source document, left visible rather than adjusted.

        Bands run "3.0-3.9" then "4.0-5.0". A domain average moves in steps of
        0.2 so cannot land between them, but the overall index averages eight of
        those figures and can: six domains at 4.0 and two at 3.8 give 3.95.
        """
        problems = [p for p in validate_card(self.card) if p.severity == ERROR]
        self.assertTrue(
            any("nothing covers 3.9 to 4" in p.message for p in problems),
            [p.message for p in problems],
        )

    def test_the_score_that_falls_in_that_gap_is_reachable(self):
        # Six domains at 4.0, two at 3.8.
        values = [4] * 30 + [4, 4, 4, 4, 3] + [4, 4, 4, 4, 3]
        result = score_assessment(self.card, self.answers(values))
        overall = result.score("overall")
        self.assertEqual(overall.value, 3.95)
        # And with the document's bands as written, it matches none of them.
        self.assertIsNone(overall.band_id)

    def test_the_wrong_number_of_questions_is_refused(self):
        with self.assertRaises(CardError):
            mental_skills(questions(39, ONE_FIVE))
