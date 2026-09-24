"""Baker Street's own instruments, held to the figures in their documents."""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.baker_street import health_in_motion
from assessments.scoring.validation import ERROR, achievable_range, validate_card

SEVERITY = ["None (0)", "Mild (1)", "Moderate (2)", "Severe (3)", "Very Severe (4)"]


def questions(count=15, options=SEVERITY):
    return [
        AssessmentQuestion(
            identifier=f"foot{i}", order=i, text=f"item {i}",
            response_type=AssessmentQuestion.ResponseType.LIKERT,
            config={"options": list(options)}, domain="general",
        )
        for i in range(1, count + 1)
    ]


class HealthInMotionTests(SimpleTestCase):
    def setUp(self):
        self.card = health_in_motion(questions())

    def answers(self, *values):
        return {f"foot{i}": SEVERITY[v] for i, v in enumerate(values, 1)}

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_the_converted_scale_runs_zero_to_one_hundred(self):
        self.assertEqual(achievable_range(self.card)["total"], (0, 100))

    def test_the_documented_conversion(self):
        # "summing all responses, multiplying by 5, and dividing by 3"
        for raw, expected in [(0, 0), (15, 25), (30, 50), (45, 75), (60, 100)]:
            values = []
            remaining = raw
            for _ in range(15):
                take = min(4, remaining)
                values.append(take)
                remaining -= take
            score = score_assessment(self.card, self.answers(*values)).score("total")
            self.assertEqual(score.value, expected, f"raw {raw}")

    def test_the_case_the_live_site_gets_wrong(self):
        """Raw 35 reads "evaluation advised" live; the document says urgent."""
        values = [4, 4, 4, 4, 4, 4, 4, 4, 3] + [0] * 6   # 35
        score = score_assessment(self.card, self.answers(*values)).score("total")
        self.assertEqual(sum(values), 35)
        self.assertEqual(score.value, 58.33)
        self.assertEqual(score.band_id, "level-3")
        self.assertIn("urgent", score.interpretation.lower())

    def test_a_raw_thirty_eight_also_moves_up_a_band(self):
        values = [4] * 9 + [2] + [0] * 5   # 38
        score = score_assessment(self.card, self.answers(*values)).score("total")
        self.assertEqual(sum(values), 38)
        self.assertEqual(score.value, 63.33)
        self.assertEqual(score.band_id, "level-3")

    def test_a_genuinely_mild_result_stays_mild(self):
        values = [1] * 5 + [0] * 10       # raw 5 -> 8.33
        score = score_assessment(self.card, self.answers(*values)).score("total")
        self.assertEqual(score.value, 8.33)
        self.assertEqual(score.band_id, "level-1")

    def test_a_real_gap_is_still_caught_at_this_step_size(self):
        """Guards the step size itself.

        Converted scores move in steps of 5/3, so 24 to 25 is not a gap. A wider
        hole still has to be reported, or the step size would have quietly
        disabled the check rather than tuned it.
        """
        from assessments.scoring import Band, ScoreRule, ScoringCard, Transform
        from assessments.scoring.loader import question_rule

        rules = [question_rule(q) for q in questions()]
        holed = ScoringCard(questions=rules, scores=[ScoreRule(
            id="total", label="Total",
            questions=[r.identifier for r in rules],
            transform=Transform(kind="linear", multiply=5, divide=3),
            granularity=5 / 3,
            bands=[
                Band("low", "Low", 0, 20, ""),
                Band("high", "High", 25, 100, ""),   # 21.67 and 23.33 are reachable
            ],
        )])
        problems = [p.message for p in validate_card(holed) if p.severity == ERROR]
        self.assertTrue(any("nothing covers 20 to 25" in m for m in problems), problems)

    def test_a_partial_submission_produces_no_score(self):
        answers = self.answers(*[2] * 15)
        answers.pop("foot7")
        result = score_assessment(self.card, answers)
        self.assertEqual(result.score("total").status, "insufficient_data")

    def test_the_wrong_answer_options_are_refused(self):
        with self.assertRaises(CardError) as caught:
            health_in_motion(questions(options=["0 - Never", "1 - Rarely", "2 - Sometimes"]))
        self.assertIn("scored on 0-4", str(caught.exception))

    def test_the_wrong_number_of_questions_is_refused(self):
        with self.assertRaises(CardError):
            health_in_motion(questions(count=14))
