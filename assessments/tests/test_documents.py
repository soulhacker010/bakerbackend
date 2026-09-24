"""Reading questions out of a source document.

Extraction is only trustworthy if it fails loudly, so most of these tests are
about refusing rather than succeeding: a document that has drifted must not
produce a plausible-looking partial set of questions.

The documents themselves are not in this repository, so the fixtures here
reproduce their shape rather than their content.
"""
from django.test import SimpleTestCase

from assessments.scoring.documents import (
    DocumentError,
    as_question_payload,
    extract_lettered_options,
    extract_by_counted_headings,
    extract_by_numbered_sections,
    strip_leading_number,
)

COUNTED = """
Screening Questions
Depression (3 questions, Score Range: 0–9)
Have you felt sad, empty, or hopeless?
Have you lost interest in things you usually enjoy?
Have you had trouble sleeping or slept too much?
Anxiety (2 questions, Score Range: 0–6)
Have you felt nervous, anxious, or on edge?
Have you had trouble controlling excessive worrying?
Scoring
Sum the scores for the total measure.
"""

NUMBERED = """
Rating Scale
1 = Rarely 2 = Occasionally 3 = Sometimes 4 = Often 5 = Almost Always
Domain 1: Game Keys and Performance Routines
1. I identify specific actions that improve my performance.
2. I use pre-performance routines to prepare mentally.
Domain 2: Self-Awareness and Emotional Control
1. I recognise my emotional state before competition.
2. I use breathing techniques to calm myself under pressure.
Scoring & Interpretation
Domain Score = Average of the items in that domain.
"""

LAYOUT = [("depression", 3), ("anxiety", 2)]


class CountedHeadingTests(SimpleTestCase):
    def test_reads_every_question_into_its_section(self):
        questions = extract_by_counted_headings(COUNTED, LAYOUT)
        self.assertEqual(len(questions), 5)
        self.assertEqual([q.section for q in questions], ["depression"] * 3 + ["anxiety"] * 2)
        self.assertEqual([q.number for q in questions], [1, 2, 3, 4, 5])
        self.assertEqual(questions[0].text, "Have you felt sad, empty, or hopeless?")
        self.assertEqual(questions[4].text, "Have you had trouble controlling excessive worrying?")

    def test_does_not_mistake_instructions_for_questions(self):
        questions = extract_by_counted_headings(COUNTED, LAYOUT)
        self.assertNotIn("Sum the scores for the total measure.", [q.text for q in questions])
        self.assertNotIn("Screening Questions", [q.text for q in questions])

    def test_refuses_when_the_document_has_a_different_number_of_sections(self):
        with self.assertRaises(DocumentError) as caught:
            extract_by_counted_headings(COUNTED, LAYOUT + [("stress", 4)])
        self.assertIn("Expected 3 sections", str(caught.exception))

    def test_refuses_when_a_section_declares_a_different_count(self):
        with self.assertRaises(DocumentError) as caught:
            extract_by_counted_headings(COUNTED, [("depression", 4), ("anxiety", 2)])
        self.assertIn("declares 3 questions but 4 were expected", str(caught.exception))

    def test_refuses_when_a_section_is_short_of_questions(self):
        truncated = COUNTED.replace("Have you had trouble sleeping or slept too much?\n", "")
        with self.assertRaises(DocumentError) as caught:
            extract_by_counted_headings(truncated, LAYOUT)
        self.assertIn("could be read from the document", str(caught.exception))

    def test_never_returns_a_partial_set(self):
        truncated = COUNTED.replace("Have you had trouble sleeping or slept too much?\n", "")
        with self.assertRaises(DocumentError):
            extract_by_counted_headings(truncated, LAYOUT)


class NumberedSectionTests(SimpleTestCase):
    HEADINGS = [("domain1", "Domain 1:"), ("domain2", "Domain 2:")]

    def test_reads_a_fixed_number_of_items_per_section(self):
        questions = extract_by_numbered_sections(NUMBERED, self.HEADINGS, per_section=2)
        self.assertEqual(len(questions), 4)
        self.assertEqual([q.section for q in questions], ["domain1", "domain1", "domain2", "domain2"])
        self.assertTrue(questions[0].text.startswith("1. I identify"))

    def test_refuses_a_heading_it_cannot_find(self):
        with self.assertRaises(DocumentError) as caught:
            extract_by_numbered_sections(NUMBERED, self.HEADINGS + [("domain3", "Domain 3:")], 2)
        self.assertIn("Could not find the section heading", str(caught.exception))

    def test_refuses_when_a_section_is_short(self):
        with self.assertRaises(DocumentError) as caught:
            extract_by_numbered_sections(NUMBERED, self.HEADINGS, per_section=5)
        self.assertIn("should hold 5 questions", str(caught.exception))

    def test_refuses_headings_given_out_of_order(self):
        with self.assertRaises(DocumentError) as caught:
            extract_by_numbered_sections(
                NUMBERED, [("domain2", "Domain 2:"), ("domain1", "Domain 1:")], 2
            )
        self.assertIn("do not appear in the order given", str(caught.exception))


NUMBERED_WITH_NOISE = """
Section I - Sleep Quantity
1. On a typical night, how much sleep do you actually get?
Do not include time spent awake in bed.
2. On most nights, how much time do you allow yourself for sleep?
Section II - Sleep Red Flags
The following questions are not included in the total score.
A "Yes" response may indicate the need for additional evaluation.
3. Has anyone told you that you snore loudly or regularly?
4. Has anyone observed you stop breathing while sleeping?
"""


class NumberedOnlyTests(SimpleTestCase):
    """Some documents put instructions among their items."""

    HEADINGS = [("quantity", "Section I"), ("red_flags", "Section II")]

    def test_instructions_are_mistaken_for_questions_without_it(self):
        # "Do not include time spent awake in bed." reads as a question, and the
        # real second item is pushed out of the count.
        questions = extract_by_numbered_sections(NUMBERED_WITH_NOISE, self.HEADINGS, [2, 2])
        self.assertIn(
            "Do not include time spent awake in bed.", [q.text for q in questions]
        )

    def test_numbered_only_collects_the_real_items(self):
        questions = extract_by_numbered_sections(
            NUMBERED_WITH_NOISE, self.HEADINGS, [2, 2], numbered_only=True
        )
        self.assertEqual(
            [strip_leading_number(q.text)[:20] for q in questions],
            ["On a typical night, ", "On most nights, how ",
             "Has anyone told you ", "Has anyone observed "],
        )

    def test_it_still_refuses_when_a_section_is_short(self):
        with self.assertRaises(DocumentError):
            extract_by_numbered_sections(
                NUMBERED_WITH_NOISE, self.HEADINGS, [3, 2], numbered_only=True
            )


class VaryingSectionSizeTests(SimpleTestCase):
    def test_each_section_may_hold_a_different_number(self):
        questions = extract_by_numbered_sections(
            NUMBERED_WITH_NOISE, [("quantity", "Section I"), ("red_flags", "Section II")],
            [2, 2], numbered_only=True,
        )
        self.assertEqual([q.section for q in questions],
                         ["quantity", "quantity", "red_flags", "red_flags"])

    def test_a_mismatched_number_of_counts_is_refused(self):
        with self.assertRaises(DocumentError) as caught:
            extract_by_numbered_sections(
                NUMBERED_WITH_NOISE, [("quantity", "Section I")], [2, 2]
            )
        self.assertIn("1 sections were given but 2 counts", str(caught.exception))


class TextTidyingTests(SimpleTestCase):
    def test_removes_a_leading_number(self):
        self.assertEqual(strip_leading_number("12. Forgets instructions."), "Forgets instructions.")

    def test_removes_a_reverse_marker(self):
        self.assertEqual(
            strip_leading_number("(R) Independently remembers instructions."),
            "Independently remembers instructions.",
        )

    def test_leaves_an_ordinary_question_alone(self):
        self.assertEqual(strip_leading_number("Have you felt sad?"), "Have you felt sad?")


class PayloadTests(SimpleTestCase):
    OPTIONS = ["0 - Not at all", "1 - Several days"]

    def test_builds_the_shape_the_api_expects(self):
        questions = extract_by_counted_headings(COUNTED, LAYOUT)
        payload = as_question_payload(questions, self.OPTIONS)
        self.assertEqual(len(payload), 5)
        first = payload[0]
        self.assertEqual(first["identifier"], "q1")
        self.assertEqual(first["order"], 1)
        self.assertEqual(first["domain"], "depression")
        self.assertEqual(first["config"]["options"], self.OPTIONS)
        self.assertTrue(first["required"])

    def test_numbers_run_in_order_without_gaps(self):
        payload = as_question_payload(extract_by_counted_headings(COUNTED, LAYOUT), self.OPTIONS)
        self.assertEqual([entry["order"] for entry in payload], [1, 2, 3, 4, 5])
        self.assertEqual([entry["identifier"] for entry in payload], [f"q{i}" for i in range(1, 6)])


LETTERED = """
Section I - Sleep Quantity
1. On a typical night, approximately how much sleep do you actually get?
Do not include time spent awake in bed.
A. More than 7 hours - 0 points
B. 6-7 hours - 1 point
C. 5-6 hours - 2 points
D. Less than 5 hours - 3 points
2. On most nights, how much time do you allow yourself for sleep?
A. 8 or more hours - 0 points
B. Less than 6 hours - 3 points
Section VI - Sleep Red Flags
Answer Yes or No.
16. Has anyone told you that you snore loudly or regularly?
Yes
No
"""


class LetteredOptionTests(SimpleTestCase):
    """Options whose text contains numbers of its own."""

    def test_reads_the_value_from_the_points_rather_than_the_label(self):
        options = extract_lettered_options(LETTERED)
        self.assertEqual(options[1][1], {"value": 1.0, "label": "6-7 hours"})

    def test_a_label_full_of_numbers_keeps_the_right_score(self):
        # "6-7 hours - 1 point" holds three numbers; only the points count.
        options = extract_lettered_options(LETTERED)
        self.assertEqual([entry["value"] for entry in options[1]], [0.0, 1.0, 2.0, 3.0])
        self.assertEqual(
            [entry["label"] for entry in options[1]],
            ["More than 7 hours", "6-7 hours", "5-6 hours", "Less than 5 hours"],
        )

    def test_options_attach_to_the_question_above_them(self):
        options = extract_lettered_options(LETTERED)
        self.assertEqual(len(options[1]), 4)
        self.assertEqual(len(options[2]), 2)
        self.assertEqual(options[2][1]["label"], "Less than 6 hours")

    def test_questions_without_lettered_options_get_none(self):
        # The yes/no red flags are not scored and carry no point values.
        self.assertNotIn(16, extract_lettered_options(LETTERED))

    def test_an_empty_document_yields_nothing(self):
        self.assertEqual(extract_lettered_options(""), {})
