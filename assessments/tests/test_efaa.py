"""EFAA, held to the figures in its document.

This instrument exercises most of the engine at once, so these tests double as a
check that reverse scoring, not-applicable handling, section thresholds and a
total built from sections all work together rather than only in isolation.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.executive_functioning import DOMAINS, efaa
from assessments.scoring.validation import ERROR, achievable_range, validate_card

SCALE = ["0 - Never", "1 - Sometimes", "2 - Often", "3 - Almost always"]
REVERSED_ITEMS = (8, 16, 24, 32, 40, 48)


def questions(count=48, options=SCALE):
    return [
        AssessmentQuestion(
            identifier=f"e{i}", order=i, text=f"item {i}",
            response_type=AssessmentQuestion.ResponseType.LIKERT,
            config={"options": list(options)}, domain="general",
        )
        for i in range(1, count + 1)
    ]


class EfaaTests(SimpleTestCase):
    def setUp(self):
        self.card = efaa(questions())

    def answers(self, default=0, overrides=None):
        payload = {f"e{i}": SCALE[default] for i in range(1, 49)}
        for item, value in (overrides or {}).items():
            payload[f"e{item}"] = SCALE[value] if isinstance(value, int) else value
        return payload

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_the_documented_ranges(self):
        ranges = achievable_range(self.card)
        for key, _ in DOMAINS:
            self.assertEqual(ranges[key], (0, 24), key)
        self.assertEqual(ranges["total"], (0, 144))

    def test_six_sections_of_eight(self):
        counts = {}
        for rule in self.card.questions:
            counts[rule.domain] = counts.get(rule.domain, 0) + 1
        self.assertEqual(sorted(counts.values()), [8] * 6)
        self.assertEqual(sorted(counts), sorted(key for key, _ in DOMAINS))

    def test_the_eighth_item_of_every_section_is_reversed(self):
        reversed_items = {
            int(rule.identifier[1:]) for rule in self.card.questions if rule.reverse
        }
        self.assertEqual(reversed_items, set(REVERSED_ITEMS))

    def test_answering_zero_everywhere_still_scores_the_reversed_items(self):
        result = score_assessment(self.card, self.answers(default=0))
        # Each section's eighth item flips 0 to 3.
        self.assertEqual(result.score("working_memory").value, 3)
        self.assertEqual(result.score("total").value, 18)
        self.assertEqual(result.score("total").band_id, "minimal")

    def test_the_documented_maximum_of_one_hundred_and_forty_four(self):
        overrides = {item: 0 for item in REVERSED_ITEMS}
        result = score_assessment(self.card, self.answers(default=3, overrides=overrides))
        self.assertEqual(result.score("total").value, 144)
        self.assertEqual(result.score("total").band_id, "significant")
        for key, _ in DOMAINS:
            self.assertEqual(result.score(key).value, 24, key)

    def test_a_section_at_twelve_raises_its_own_flag_only(self):
        # Working memory is items 1-8. Four items at 3 plus the reversed eighth
        # at 0 gives 12 + 3 = 15.
        result = score_assessment(self.card, self.answers(overrides={1: 3, 2: 3, 3: 3, 4: 3}))
        self.assertEqual(result.score("working_memory").value, 15)
        raised = [flag.id for flag in result.flags]
        self.assertIn("working_memory-elevated", raised)
        self.assertNotIn("inhibition-elevated", raised)

    def test_the_threshold_is_at_twelve_not_above_it(self):
        # Three items at 3 plus the reversed eighth at 0 gives 9 + 3 = 12.
        result = score_assessment(self.card, self.answers(overrides={1: 3, 2: 3, 3: 3}))
        self.assertEqual(result.score("working_memory").value, 12)
        self.assertIn("working_memory-elevated", [flag.id for flag in result.flags])

    def test_every_section_is_reported_even_when_none_is_elevated(self):
        result = score_assessment(self.card, self.answers(default=0))
        reported = {score.id for score in result.scores}
        for key, _ in DOMAINS:
            self.assertIn(key, reported)

    def test_not_applicable_shrinks_the_maximum_rather_than_counting_as_zero(self):
        overrides = {item: 0 for item in REVERSED_ITEMS}
        overrides[1] = "N/A"
        result = score_assessment(self.card, self.answers(default=3, overrides=overrides))
        working_memory = result.score("working_memory")
        self.assertEqual(working_memory.answered, 7)
        self.assertEqual(working_memory.max_possible, 21)
        self.assertEqual(working_memory.value, 21)

    def test_a_section_with_too_few_answers_is_not_scored(self):
        overrides = {item: "N/A" for item in range(1, 5)}
        result = score_assessment(self.card, self.answers(default=3, overrides=overrides))
        self.assertEqual(result.score("working_memory").status, "insufficient_data")

    def test_the_total_is_withheld_when_a_section_cannot_be_scored(self):
        """Summing the remaining sections would quietly understate the total."""
        overrides = {item: "N/A" for item in range(1, 5)}
        result = score_assessment(self.card, self.answers(default=3, overrides=overrides))
        self.assertEqual(result.score("total").status, "insufficient_data")
        self.assertIsNone(result.score("total").value)

    def test_a_section_that_cannot_be_scored_raises_no_flag(self):
        overrides = {item: "N/A" for item in range(1, 5)}
        result = score_assessment(self.card, self.answers(default=3, overrides=overrides))
        self.assertNotIn("working_memory-elevated", [flag.id for flag in result.flags])

    def test_the_provisional_notice_is_carried(self):
        result = score_assessment(self.card, self.answers())
        self.assertIn("awaiting pilot norms", result.notice)

    def test_the_wrong_number_of_questions_is_refused(self):
        with self.assertRaises(CardError):
            efaa(questions(47))

    def test_the_wrong_answer_scale_is_refused(self):
        with self.assertRaises(CardError):
            efaa(questions(options=["0 - No", "1 - Yes"]))
