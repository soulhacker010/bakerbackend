"""Executive Functioning Assessment (Ages 3-10), held to its document.

The sections are interleaved (Working Memory is questions 2, 6, 9, ...), so the
case that matters is a section scored from the right questions.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.executive_functioning import AGES_3_10_SECTIONS, ef_ages_3_10
from assessments.scoring.validation import ERROR, achievable_range, validate_card

SCALE = ["0 - Never", "1 - Sometimes", "2 - Often", "3 - Almost Always"]


def questions(count=40):
    return [
        AssessmentQuestion(
            identifier=f"q{i}", order=i, text=f"item {i}",
            response_type=AssessmentQuestion.ResponseType.LIKERT,
            config={"options": list(SCALE)}, domain="general",
        )
        for i in range(1, count + 1)
    ]


class EfAges3To10Tests(SimpleTestCase):
    def setUp(self):
        self.card = ef_ages_3_10(questions())

    def score(self, values):
        return score_assessment(self.card, {f"q{i}": SCALE[v] for i, v in enumerate(values, 1)})

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_the_documented_ranges(self):
        ranges = achievable_range(self.card)
        for domain, _, _ in AGES_3_10_SECTIONS:
            self.assertEqual(ranges[domain], (0, 30))
        self.assertEqual(ranges["total"], (0, 120))

    def test_a_section_is_scored_from_its_own_questions(self):
        values = [0] * 40
        for n in (2, 6, 9, 11, 16, 18, 20, 26, 35, 40):   # Working Memory
            values[n - 1] = 3
        result = self.score(values)
        self.assertEqual(result.score("working_memory").value, 30)
        self.assertEqual(result.score("working_memory").band_id, "significant")
        self.assertEqual(result.score("emotional_regulation").value, 0)
        self.assertEqual(result.score("total").value, 30)
        self.assertEqual(result.score("total").band_id, "minimal")

    def test_section_and_global_cut_offs(self):
        # Inhibitory Control at 11 is mild; the global 41 is mild to moderate.
        values = [0] * 40
        for n in (7, 10, 14, 17, 21):
            values[n - 1] = 2
        values[22 - 1] = 1
        result = self.score(values)
        self.assertEqual(result.score("inhibitory_control").value, 11)
        self.assertEqual(result.score("inhibitory_control").band_id, "mild")
        result = self.score([1] * 40 + [])
        self.assertEqual(result.score("total").value, 40)
        self.assertEqual(result.score("total").band_id, "minimal")
        values = [1] * 40
        values[0] = 2
        self.assertEqual(self.score(values).score("total").band_id, "mild-moderate")

    def test_every_answer_at_the_top_reaches_one_twenty(self):
        result = self.score([3] * 40)
        self.assertEqual(result.score("total").value, 120)
        self.assertEqual(result.score("total").band_id, "significant")

    def test_refuses_the_wrong_number_of_questions(self):
        with self.assertRaises(CardError):
            ef_ages_3_10(questions(39))
