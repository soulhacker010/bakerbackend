"""A clinician reading a client's answers, after the editor renamed the questions.

The practice's October 2026 update: "For all assessments, the clinician needs to
be able to see the clients responses, in addition to the overall score."

The answers were stored. They were not readable: the editor appended "-2" to a
question's identifier on every save, so an answer stored a few saves earlier is
filed under a key its question no longer has. 37 of the 59 stored responses
showed the clinician that key in place of the question - for instance
"1-how-often-do-you-experience-foot-pain-mhxrisj1-1-2-2-2-2-2-2-2".

These run against the database because the serializer reads the questions from
it, which is where the mismatch lives.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from assessments.models import Assessment, AssessmentQuestion, AssessmentResponse
from assessments.serializers import AssessmentResponseSerializer


class StoredAnswerMatchingTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(
            email="clinician@example.com", password="x-Strong-pass-1"
        )
        self.assessment = Assessment.objects.create(
            title="Foot screen", slug="foot-screen", created_by=owner
        )

    def question(self, identifier, order, text):
        return AssessmentQuestion.objects.create(
            assessment=self.assessment, identifier=identifier, order=order, text=text,
            response_type=AssessmentQuestion.ResponseType.SINGLE_CHOICE,
            config={"options": ["0 - No", "1 - Yes"]},
        )

    def shown(self, answers):
        response = AssessmentResponse.objects.create(
            assessment=self.assessment, responses=answers
        )
        return {
            a["question"]: a["selected"]
            for a in AssessmentResponseSerializer().get_answers(response)
        }

    def test_an_answer_stored_before_more_saves_finds_its_question(self):
        """The live case, word for word."""
        self.question("1-how-often-foot-pain-mhxrisj1-1-2-2-2-2-2-2-2-2-2", 1,
                      "How often do you experience foot pain?")
        shown = self.shown({"1-how-often-foot-pain-mhxrisj1-1-2-2-2-2-2-2-2": "1 - Yes"})
        self.assertEqual(shown, {"How often do you experience foot pain?": ["1 - Yes"]})

    def test_the_clinician_sees_the_question_not_the_code(self):
        self.question("question-1-2-2-2-2", 1, "How have you been sleeping?")
        shown = self.shown({"question-1-2-2": "0 - No"})
        self.assertNotIn("question-1-2-2", shown)
        self.assertIn("How have you been sleeping?", shown)

    def test_an_answer_stored_after_the_question_was_saved_still_matches(self):
        """The suffix can be longer on either side."""
        self.question("pain-2", 1, "Pain?")
        self.assertEqual(self.shown({"pain-2-2-2": "1 - Yes"}), {"Pain?": ["1 - Yes"]})

    def test_an_exact_match_is_never_displaced_by_a_guess(self):
        self.question("sleep", 1, "Sleep?")
        self.question("sleep-2", 2, "Sleep, second item?")
        shown = self.shown({"sleep": "0 - No", "sleep-2": "1 - Yes"})
        self.assertEqual(shown["Sleep?"], ["0 - No"])
        self.assertEqual(shown["Sleep, second item?"], ["1 - Yes"])

    def test_it_will_not_guess_between_two_questions_that_share_a_base(self):
        """Two questions both reduce to "mood". Showing the answer under either
        could be showing it under the wrong one, so it stays visibly unmatched."""
        self.question("mood-2-2", 1, "Mood, first?")
        self.question("mood-2-2-2", 2, "Mood, second?")
        shown = self.shown({"mood-2": "1 - Yes"})
        self.assertNotIn("Mood, first?", shown)
        self.assertNotIn("Mood, second?", shown)
        self.assertIn("mood-2", shown)

    def test_question_one_cannot_take_question_tens_answer(self):
        """"q1" is the start of "q10". The old fallback matched on that prefix,
        one question at a time, so question 1 could take question 10's answer
        before question 10 had looked for its own."""
        self.question("renamed-first", 1, "First question?")
        for order in range(2, 11):
            self.question(f"q{order}", order, f"Question {order}?")
        answers = {f"q{order}": "0 - No" for order in range(2, 10)}
        answers["q10"] = "1 - Yes"
        shown = self.shown(answers)
        self.assertEqual(shown["Question 10?"], ["1 - Yes"])
        self.assertNotIn("First question?", shown)

    def test_q1_does_not_match_q10_when_both_questions_were_renamed(self):
        """With no exact match to protect it, question 1 falls back to its
        order. "q10" starts with "q1", and must still go to question 10."""
        self.question("renamed-first", 1, "First?")
        for order in range(2, 10):
            self.question(f"q{order}", order, f"Question {order}?")
        self.question("renamed-tenth", 10, "Tenth?")
        shown = self.shown({"q10": "1 - Yes"})
        self.assertEqual(shown, {"Tenth?": ["1 - Yes"]})

    def test_a_zero_padded_old_record_still_finds_its_question(self):
        self.question("renamed", 1, "First?")
        self.assertEqual(self.shown({"q01": "1 - Yes"}), {"First?": ["1 - Yes"]})

    def test_nothing_stored_is_dropped(self):
        """An answer that matches no question is still shown, under its key,
        rather than silently disappearing from the clinician's view."""
        self.question("known", 1, "Known?")
        shown = self.shown({"known": "0 - No", "something-else": "1 - Yes"})
        self.assertEqual(shown["Known?"], ["0 - No"])
        self.assertEqual(shown["something-else"], ["1 - Yes"])
