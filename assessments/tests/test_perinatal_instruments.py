"""The two perinatal screeners, held to the figures in their documents.

The case that matters most in both is a low total sitting over an endorsed
high-risk item. If a flag ever stops firing there, these fail.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.perinatal import expectant_mothers, postpartum_fathers
from assessments.scoring.validation import ERROR, achievable_range, validate_card

SCALE = ["0 - Not at all", "1 - Several days", "2 - More than half the days", "3 - Nearly everyday"]


def questions(count, options=SCALE, prefix="q"):
    return [
        AssessmentQuestion(
            identifier=f"{prefix}{i}", order=i, text=f"item {i}",
            response_type=AssessmentQuestion.ResponseType.LIKERT,
            config={"options": list(options)}, domain="general",
        )
        for i in range(1, count + 1)
    ]


class PostpartumFathersTests(SimpleTestCase):
    def setUp(self):
        self.card = postpartum_fathers(questions(20))

    def answers(self, values):
        return {f"q{i}": SCALE[v] for i, v in enumerate(values, 1)}

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_the_documented_section_ranges(self):
        ranges = achievable_range(self.card)
        self.assertEqual(ranges["depression"], (0, 18))
        self.assertEqual(ranges["anxiety"], (0, 15))
        self.assertEqual(ranges["stress"], (0, 15))
        self.assertEqual(ranges["sleep"], (0, 12))
        self.assertEqual(ranges["total"], (0, 60))

    def test_every_answer_at_the_top_reaches_sixty(self):
        result = score_assessment(self.card, self.answers([3] * 20))
        self.assertEqual(result.score("total").value, 60)
        self.assertEqual(result.score("total").band_id, "high")

    def test_sections_are_scored_from_their_own_questions(self):
        # Depression is items 1-6, anxiety 7-11, stress 12-16, sleep 17-20.
        values = [3] * 6 + [0] * 14
        result = score_assessment(self.card, self.answers(values))
        self.assertEqual(result.score("depression").value, 18)
        self.assertEqual(result.score("anxiety").value, 0)
        self.assertEqual(result.score("sleep").value, 0)
        self.assertEqual(result.score("total").value, 18)

    def test_a_high_depression_section_flags_even_at_a_low_total(self):
        values = [3] * 5 + [1] + [0] * 14      # depression 16 of 18, total 16
        result = score_assessment(self.card, self.answers(values))
        self.assertEqual(result.score("depression").value, 16)
        self.assertEqual(result.score("total").value, 16)
        self.assertEqual(result.score("total").band_id, "low")   # "Low Risk" overall
        self.assertIn("depression-high", [f.id for f in result.flags])

    def test_no_flag_when_depression_is_moderate(self):
        values = [3] * 4 + [0] * 16            # depression 12
        result = score_assessment(self.card, self.answers(values))
        self.assertEqual(result.score("depression").band_id, "moderate")
        self.assertEqual(result.flags, [])

    def test_the_wrong_number_of_questions_is_refused(self):
        with self.assertRaises(CardError):
            postpartum_fathers(questions(19))

    def test_the_wrong_answer_options_are_refused(self):
        with self.assertRaises(CardError):
            postpartum_fathers(questions(20, ["0 - No", "1 - Yes"]))


class ExpectantMothersTests(SimpleTestCase):
    def setUp(self):
        self.card = expectant_mothers(questions(25))

    def answers(self, values):
        return {f"q{i}": SCALE[v] for i, v in enumerate(values, 1)}

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_the_documented_section_ranges(self):
        ranges = achievable_range(self.card)
        self.assertEqual(ranges["depression"], (0, 15))
        self.assertEqual(ranges["anxiety"], (0, 15))
        self.assertEqual(ranges["ocd"], (0, 12))
        self.assertEqual(ranges["eating"], (0, 12))
        self.assertEqual(ranges["mood"], (0, 9))
        self.assertEqual(ranges["suicidal"], (0, 6))
        self.assertEqual(ranges["adhd"], (0, 6))
        self.assertEqual(ranges["total"], (0, 75))

    def test_seven_sections_not_eight(self):
        section_ids = [score.id for score in self.card.scores if score.id != "total"]
        self.assertEqual(len(section_ids), 7)

    def test_everything_at_the_top_reaches_seventy_five(self):
        result = score_assessment(self.card, self.answers([3] * 25))
        self.assertEqual(result.score("total").value, 75)
        self.assertEqual(result.score("total").band_id, "high")

    def test_a_single_endorsed_suicidal_item_flags_at_a_low_risk_total(self):
        """The case a total score hides.

        Items 22 and 23 are the suicidal ideation section. One answered at 1,
        everything else zero, gives a total of 1: firmly inside "Low Risk".
        """
        values = [0] * 25
        values[21] = 1                          # question 22
        result = score_assessment(self.card, self.answers(values))

        self.assertEqual(result.score("total").value, 1)
        self.assertEqual(result.score("total").band_id, "low")
        self.assertEqual(result.score("suicidal").value, 1)
        self.assertEqual(result.score("suicidal").band_id, "low-moderate")

        raised = [f.id for f in result.flags]
        self.assertIn("suicidal-any", raised)
        self.assertNotIn("suicidal-high", raised)
        self.assertEqual(result.flags[0].severity, "urgent")

    def test_the_high_suicidal_range_raises_both_flags(self):
        values = [0] * 25
        values[21] = 3
        values[22] = 3                          # suicidal 6 of 6
        result = score_assessment(self.card, self.answers(values))
        self.assertEqual(result.score("suicidal").value, 6)
        self.assertEqual(result.score("suicidal").band_id, "high")
        self.assertEqual(
            sorted(f.id for f in result.flags), ["suicidal-any", "suicidal-high"]
        )

    def test_nothing_flags_when_the_section_is_zero(self):
        values = [3] * 21 + [0, 0] + [3, 3]     # everything high except suicidal
        result = score_assessment(self.card, self.answers(values))
        self.assertEqual(result.score("suicidal").value, 0)
        self.assertEqual(result.score("suicidal").band_id, "none")
        self.assertEqual(result.flags, [])

    def test_a_partial_submission_reports_no_total(self):
        answers = self.answers([1] * 25)
        answers.pop("q22")
        result = score_assessment(self.card, answers)
        self.assertEqual(result.score("suicidal").status, "insufficient_data")
        # The total is built from the sections, so it cannot be reported either.
        self.assertEqual(result.score("total").status, "insufficient_data")

    def test_a_section_that_cannot_be_calculated_raises_no_flag(self):
        answers = self.answers([0] * 25)
        answers.pop("q22")
        answers.pop("q23")
        result = score_assessment(self.card, answers)
        self.assertEqual(result.score("suicidal").status, "insufficient_data")
        self.assertEqual(result.flags, [])
