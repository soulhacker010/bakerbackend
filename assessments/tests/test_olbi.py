"""Oldenburg Burnout Inventory, held to the practice's October 2026 update."""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.instruments import OLBI_REVERSED, olbi
from assessments.scoring.validation import ERROR, achievable_range, validate_card

# As the document prints them: 4 = Strongly Disagree ... 1 = Strongly Agree.
SCALE = ["4 - Strongly Disagree", "3 - Disagree", "2 - Agree", "1 - Strongly Agree"]
VALUE = {4: SCALE[0], 3: SCALE[1], 2: SCALE[2], 1: SCALE[3]}


def questions(count=16):
    return [
        AssessmentQuestion(
            identifier=f"q{i}", order=i, text=f"item {i}",
            response_type=AssessmentQuestion.ResponseType.LIKERT,
            config={"options": list(SCALE)}, domain="general",
        )
        for i in range(1, count + 1)
    ]


class OlbiTests(SimpleTestCase):
    def setUp(self):
        self.card = olbi(questions())

    def score(self, values):
        return score_assessment(self.card, {f"q{i}": VALUE[v] for i, v in enumerate(values, 1)})

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_the_documented_ranges(self):
        ranges = achievable_range(self.card)
        self.assertEqual(ranges["exhaustion"], (8, 32))
        self.assertEqual(ranges["disengagement"], (8, 32))
        self.assertEqual(ranges["total"], (16, 64))

    def test_reversed_items_flip_one_to_four(self):
        # Item 2 is reversed: Strongly Agree (1) counts as 4.
        values = [1] * 16
        result = self.score(values)
        reversed_count = len(OLBI_REVERSED)
        self.assertEqual(result.score("total").value, reversed_count * 4 + (16 - reversed_count) * 1)

    def test_most_burnout_reaches_sixty_four(self):
        # Most burnout: disagree with every positive item, agree with every reversed one.
        values = [1 if n in OLBI_REVERSED else 4 for n in range(1, 17)]
        result = self.score(values)
        self.assertEqual(result.score("total").value, 64)
        self.assertEqual(result.score("total").band_id, "high")

    def test_cut_offs(self):
        least = [4 if n in OLBI_REVERSED else 1 for n in range(1, 17)]
        self.assertEqual(self.score(least).score("total").value, 16)
        self.assertEqual(self.score(least).score("total").band_id, "low")
        values = list(least)
        # Raise 14 points: 29 is still low, 30 is medium.
        for n in (1, 5, 7, 10, 13, 14, 15):
            values[n - 1] = 3
        self.assertEqual(self.score(values).score("total").value, 30)
        self.assertEqual(self.score(values).score("total").band_id, "medium")

    def test_sections_use_their_own_items(self):
        values = [4 if n in OLBI_REVERSED else 1 for n in range(1, 17)]
        for n in (2, 4, 8, 12):          # reversed exhaustion items: agree = more exhausted
            values[n - 1] = 1
        result = self.score(values)
        self.assertEqual(result.score("exhaustion").value, 8 + 4 * 3)
        self.assertEqual(result.score("disengagement").value, 8)

    def test_refuses_the_wrong_number_of_questions(self):
        with self.assertRaises(CardError):
            olbi(questions(15))
