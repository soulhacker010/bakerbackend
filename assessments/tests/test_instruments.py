"""The published instruments, scored against their published cut-offs.

Question identifiers and answer options here match what is live, because that is
what the cards have to bind to. The question text does not: these instruments are
copyrighted and their wording is not reproduced in this repository.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.instruments import cage_aid, gad7, phq9
from assessments.scoring.validation import ERROR, validate_card

FOUR_POINT = ["0 - Not at all", "1 - Several days",
              "2 - More than half the days", "3 - Nearly everyday"]
YES_NO = ["0 - No", "1 - Yes"]
DEFAULT_FREQUENCY = ["0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often"]


def build(prefix, count, options, suffix="-2"):
    """Questions shaped like the live ones, without their text."""
    return [
        AssessmentQuestion(
            identifier=f"{prefix}_q{i}{suffix}",
            order=i,
            text=f"item {i}",
            response_type=AssessmentQuestion.ResponseType.LIKERT,
            config={"options": list(options)},
            domain="general",
        )
        for i in range(1, count + 1)
    ]


class Phq9Tests(SimpleTestCase):
    def setUp(self):
        self.questions = build("phq9", 9, FOUR_POINT)
        self.card = phq9(self.questions)

    def answers(self, *values):
        return {f"phq9_q{i}-2": FOUR_POINT[v] for i, v in enumerate(values, 1)}

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_the_published_cut_offs(self):
        for total, expected in [
            (0, "none-minimal"), (4, "none-minimal"),
            (5, "mild"), (9, "mild"),
            (10, "moderate"), (14, "moderate"),
            (15, "moderately-severe"), (19, "moderately-severe"),
            (20, "severe"), (27, "severe"),
        ]:
            # Spread the total across the nine items.
            values = [0] * 9
            remaining = total
            for i in range(9):
                take = min(3, remaining)
                values[i] = take
                remaining -= take
            result = score_assessment(self.card, self.answers(*values))
            score = result.score("total")
            self.assertEqual(score.value, total)
            self.assertEqual(score.band_id, expected, f"total {total}")

    def test_maximum_is_twenty_seven(self):
        result = score_assessment(self.card, self.answers(*[3] * 9))
        self.assertEqual(result.score("total").value, 27)

    def test_item_nine_raises_a_flag_even_when_the_total_is_minimal(self):
        # Everything zero except item 9 answered "Several days": total 1.
        result = score_assessment(self.card, self.answers(0, 0, 0, 0, 0, 0, 0, 0, 1))
        score = result.score("total")
        self.assertEqual(score.value, 1)
        self.assertEqual(score.band_id, "none-minimal")

        raised = {f.id: f for f in result.flags}
        self.assertIn("phq9-item-9", raised)
        self.assertEqual(raised["phq9-item-9"].severity, "urgent")
        self.assertEqual(raised["phq9-item-9"].audience, "clinician")
        self.assertIn("phq9-item-9-respondent", raised)
        self.assertEqual(raised["phq9-item-9-respondent"].audience, "patient")

    def test_item_nine_at_zero_raises_nothing(self):
        result = score_assessment(self.card, self.answers(3, 3, 3, 3, 3, 3, 3, 3, 0))
        self.assertEqual(result.flags, [])

    def test_a_partial_submission_produces_no_score(self):
        answers = self.answers(*[1] * 9)
        answers.pop("phq9_q4-2")
        result = score_assessment(self.card, answers)
        self.assertEqual(result.score("total").status, "insufficient_data")

    def test_the_wrong_answer_options_are_refused(self):
        # What is live on PCL-5 and ASRS: the editor's default frequency scale.
        with self.assertRaises(CardError) as caught:
            phq9(build("phq9", 9, ["0 - Never", "1 - Rarely", "2 - Sometimes"]))
        self.assertIn("answer options need correcting", str(caught.exception))

    def test_the_wrong_number_of_questions_is_refused(self):
        with self.assertRaises(CardError):
            phq9(build("phq9", 8, FOUR_POINT))


class Gad7Tests(SimpleTestCase):
    def setUp(self):
        self.questions = build("gad7", 7, FOUR_POINT)
        self.card = gad7(self.questions)

    def answers(self, *values):
        return {f"gad7_q{i}-2": FOUR_POINT[v] for i, v in enumerate(values, 1)}

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_the_published_cut_offs(self):
        cases = [
            ([0] * 7, 0, "minimal"),
            ([1, 1, 1, 1, 0, 0, 0], 4, "minimal"),
            ([1, 1, 1, 1, 1, 0, 0], 5, "mild"),
            ([2, 2, 2, 1, 1, 1, 0], 9, "mild"),
            ([2, 2, 2, 2, 1, 1, 0], 10, "moderate"),
            ([3, 3, 3, 2, 2, 1, 0], 14, "moderate"),
            ([3, 3, 3, 3, 2, 1, 0], 15, "severe"),
            ([3] * 7, 21, "severe"),
        ]
        for values, expected_total, expected_band in cases:
            score = score_assessment(self.card, self.answers(*values)).score("total")
            self.assertEqual(score.value, expected_total)
            self.assertEqual(score.band_id, expected_band, values)


class CageAidTests(SimpleTestCase):
    def setUp(self):
        questions = build("cage", 4, YES_NO)
        questions.append(AssessmentQuestion(
            identifier="cage_q5-2", order=5, text="item 5",
            response_type=AssessmentQuestion.ResponseType.SINGLE_CHOICE,
            config={"options": ["Alcohol", "Drugs"]}, domain="general",
        ))
        self.card = cage_aid(questions)

    def answers(self, *values, substance="Alcohol"):
        payload = {f"cage_q{i}-2": YES_NO[v] for i, v in enumerate(values, 1)}
        payload["cage_q5-2"] = substance
        return payload

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_two_positives_is_a_positive_screen(self):
        result = score_assessment(self.card, self.answers(1, 1, 0, 0))
        score = result.score("total")
        self.assertEqual(score.value, 2)
        self.assertEqual(score.band_id, "positive")
        self.assertEqual([f.id for f in result.flags], ["cage-positive"])

    def test_one_positive_is_not(self):
        result = score_assessment(self.card, self.answers(1, 0, 0, 0))
        self.assertEqual(result.score("total").value, 1)
        self.assertEqual(result.score("total").band_id, "negative")
        self.assertEqual(result.flags, [])

    def test_the_substance_question_never_reaches_the_total(self):
        by_alcohol = score_assessment(self.card, self.answers(1, 1, 1, 1, substance="Alcohol"))
        by_drugs = score_assessment(self.card, self.answers(1, 1, 1, 1, substance="Drugs"))
        self.assertEqual(by_alcohol.score("total").value, 4)
        self.assertEqual(by_drugs.score("total").value, 4)
        self.assertEqual(by_alcohol.score("total").applicable, 4)
