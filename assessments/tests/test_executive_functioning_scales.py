"""The two Executive Functioning scales that were live on a single total.

Both already name five sections on their questions, and both were summed into one
figure whose ranges stopped well short of the figure's own maximum. These tests
pin the behaviour that was wrong, so that if anyone reinstates the old ranges the
suite says so rather than the reports going quiet again.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.executive_functioning import (
    SEVERITY_SECTIONS,
    ef_adults_adolescents,
    ef_severity_scale,
)
from assessments.scoring.validation import ERROR, achievable_range, validate_card

SEVERITY_SCALE = ["None (0)", "Mild (1)", "Moderate (2)", "Severe (3)", "Very Severe (4)"]
FREQUENCY_SCALE = ["0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often"]

# The ranges the Severity Scale was live with, applied to a 0-120 total.
LIVE_RANGES = [(0, 5, "Minimal Concerns"), (6, 16, "Moderate Disruption"), (17, 24, "Significant Impairment")]


def questions(options, count=30, sections=None):
    """Thirty questions spread evenly across the five sections, in order."""
    labels = [label for _, label in (sections or SEVERITY_SECTIONS)]
    built = []
    for i in range(1, count + 1):
        built.append(
            AssessmentQuestion(
                identifier=f"q{i}", order=i, text=f"item {i}",
                response_type=AssessmentQuestion.ResponseType.LIKERT,
                config={"options": list(options)},
                # Round-robin, matching how the live assessments interleave them.
                domain=labels[(i - 1) % len(labels)],
            )
        )
    return built


def band_for(total, ranges):
    """What the old single-list lookup would have said about a total."""
    for low, high, label in ranges:
        if low <= total <= high:
            return label
    return None


class TheBugThisFixes(SimpleTestCase):
    """What the live ranges did to a 0-120 total, stated as tests.

    These assert against ``LIVE_RANGES`` directly rather than against the card,
    so they document the fault independently of the fix.
    """

    def test_the_most_impaired_respondent_got_no_result_at_all(self):
        # Every item at "Very Severe": 30 items x 4 = 120.
        self.assertIsNone(band_for(120, LIVE_RANGES))

    def test_mild_difficulty_on_every_item_got_no_result_either(self):
        self.assertIsNone(band_for(30, LIVE_RANGES))

    def test_four_fifths_of_the_scale_had_no_result(self):
        missing = [total for total in range(0, 121) if band_for(total, LIVE_RANGES) is None]
        self.assertEqual(len(missing), 96)

    def test_a_low_total_was_called_significant_impairment(self):
        # 17 out of 120 is 14% of the scale.
        self.assertEqual(band_for(17, LIVE_RANGES), "Significant Impairment")

    def test_the_top_range_ends_at_exactly_one_section_maximum(self):
        # Six items at four points. This is the evidence the ranges are per section.
        self.assertEqual(LIVE_RANGES[-1][1], 6 * 4)


class SeverityScaleTests(SimpleTestCase):
    def setUp(self):
        self.card = ef_severity_scale(questions(SEVERITY_SCALE))

    def answers(self, index):
        return {f"q{i}": SEVERITY_SCALE[index] for i in range(1, 31)}

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_it_reports_five_sections_and_a_total(self):
        self.assertEqual(len(self.card.scores), 6)

    def test_each_section_runs_zero_to_twenty_four(self):
        ranges = achievable_range(self.card)
        for key, _ in SEVERITY_SECTIONS:
            self.assertEqual(ranges[key], (0, 24))

    def test_the_total_runs_zero_to_one_hundred_and_twenty(self):
        self.assertEqual(achievable_range(self.card)["total"], (0, 120))

    def test_the_ranges_cover_a_section_exactly(self):
        key = SEVERITY_SECTIONS[0][0]
        rule = next(s for s in self.card.scores if s.id == key)
        low, high = achievable_range(self.card)[key]
        self.assertEqual(min(b.minimum for b in rule.bands), low)
        self.assertEqual(max(b.maximum for b in rule.bands), high)

    def test_the_most_impaired_respondent_now_gets_a_result(self):
        # The regression. Every section reads Significant Impairment rather than
        # the whole report going blank.
        result = score_assessment(self.card, self.answers(4))
        for key, _ in SEVERITY_SECTIONS:
            self.assertEqual(result.score(key).band_label, "Significant Impairment")

    def test_a_respondent_with_no_difficulty_reads_minimal(self):
        result = score_assessment(self.card, self.answers(0))
        for key, _ in SEVERITY_SECTIONS:
            self.assertEqual(result.score(key).band_label, "Minimal Concerns")

    def test_mild_on_every_item_no_longer_reads_as_significant(self):
        # Six items at one point is 6, which is Moderate Disruption for a section.
        result = score_assessment(self.card, self.answers(1))
        self.assertEqual(result.score("working_memory").band_label, "Moderate Disruption")

    def test_the_total_is_reported_without_an_interpretation(self):
        # Deliberate: the ranges describe a section, so none is claimed for a total.
        result = score_assessment(self.card, self.answers(4))
        total = result.score("total")
        self.assertEqual(total.value, 120)
        self.assertIsNone(total.band_label)

    def test_the_notice_says_why_the_total_carries_no_range(self):
        self.assertIn("total", self.card.standing_notice.lower())

    def test_every_section_raises_a_flag_when_significant(self):
        result = score_assessment(self.card, self.answers(4))
        self.assertEqual(len(result.flags), 5)

    def test_no_flag_fires_when_nothing_is_elevated(self):
        self.assertEqual(score_assessment(self.card, self.answers(0)).flags, [])

    def test_a_flag_fires_at_the_range_boundary_and_not_below_it(self):
        base = {f"q{i}": SEVERITY_SCALE[0] for i in range(1, 31)}
        # Working Memory holds q1, q6, q11, q16, q21, q26 under the round robin.
        wm = [1, 6, 11, 16, 21, 26]
        at_sixteen = dict(base)
        for item, value in zip(wm, [4, 4, 4, 4, 0, 0]):
            at_sixteen[f"q{item}"] = SEVERITY_SCALE[value]
        self.assertEqual(score_assessment(self.card, at_sixteen).flags, [])

        at_seventeen = dict(at_sixteen)
        at_seventeen["q21"] = SEVERITY_SCALE[1]
        fired = score_assessment(self.card, at_seventeen).flags
        self.assertEqual([f.id for f in fired], ["working_memory-significant"])

    def test_it_refuses_a_different_number_of_questions(self):
        with self.assertRaises(CardError):
            ef_severity_scale(questions(SEVERITY_SCALE, count=25))

    def test_it_refuses_a_scale_that_is_not_the_published_one(self):
        with self.assertRaises(CardError):
            ef_severity_scale(questions(FREQUENCY_SCALE))

    def test_it_refuses_sections_it_does_not_recognise(self):
        wrong = questions(SEVERITY_SCALE)
        wrong[0].domain = "Attention"
        with self.assertRaises(CardError):
            ef_severity_scale(wrong)

    def test_it_refuses_sections_that_are_not_evenly_filled(self):
        # A section quietly losing a question shifts every maximum underneath it.
        uneven = questions(SEVERITY_SCALE)
        uneven[0].domain = uneven[1].domain
        with self.assertRaises(CardError):
            ef_severity_scale(uneven)


class AdultsAndAdolescentsTests(SimpleTestCase):
    def setUp(self):
        self.card = ef_adults_adolescents(questions(FREQUENCY_SCALE))

    def answers(self, index):
        return {f"q{i}": FREQUENCY_SCALE[index] for i in range(1, 31)}

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_each_section_runs_zero_to_eighteen(self):
        ranges = achievable_range(self.card)
        for key, _ in SEVERITY_SECTIONS:
            self.assertEqual(ranges[key], (0, 18))

    def test_the_total_runs_zero_to_ninety(self):
        self.assertEqual(achievable_range(self.card)["total"], (0, 90))

    def test_no_range_is_claimed_anywhere(self):
        # The supplied ranges name individual sections and start above a section's
        # own maximum, so they fit neither reading. None is invented here.
        for score in self.card.scores:
            self.assertEqual(list(score.bands), [])

    def test_every_section_is_still_reported_as_a_figure(self):
        result = score_assessment(self.card, self.answers(3))
        for key, _ in SEVERITY_SECTIONS:
            self.assertEqual(result.score(key).value, 18)

    def test_the_most_impaired_respondent_gets_every_section_reported(self):
        result = score_assessment(self.card, self.answers(3))
        self.assertEqual(result.score("total").value, 90)

    def test_the_notice_tells_the_reader_to_use_the_profile(self):
        self.assertIn("profile", self.card.standing_notice.lower())

    def test_the_supplied_ranges_start_above_a_section_maximum(self):
        # Why nothing could be applied: 18-24 and 25-36 against a section of 0-18.
        _, section_max = achievable_range(self.card)[SEVERITY_SECTIONS[0][0]]
        self.assertLess(section_max, 25)

    def test_it_refuses_the_severity_scale_answer_options(self):
        with self.assertRaises(CardError):
            ef_adults_adolescents(questions(SEVERITY_SCALE))
