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
