"""Question identifiers must survive a save.

Four live submissions reference question identifiers that no longer exist. The
cause is visible in the identifiers themselves: one live question is called
``q01-self-abcs-2-2-2-2-2-2-2-2``. A "-2" was appended on every save, because a
payload without the database id looked like a brand new question whose chosen
identifier was already taken.

An identifier is the only thing tying a stored answer to the question it answers.
Renaming one silently orphans every response recorded under the old name.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.crypto import get_random_string

from assessments.models import Assessment, AssessmentQuestion
from assessments.serializers import AssessmentSerializer

SCALE = ["0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often"]


class QuestionIdentifierTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="clinician@example.com", password=get_random_string(length=32),
            is_approved=True,
        )
        self.assessment = Assessment.objects.create(
            title="Mood Index", slug="mood-index",
            status=Assessment.Status.PUBLISHED, created_by=self.user,
        )
        for index, identifier in enumerate(["sleep", "mood"], start=1):
            AssessmentQuestion.objects.create(
                assessment=self.assessment, identifier=identifier, order=index,
                text=f"Question {index}",
                response_type=AssessmentQuestion.ResponseType.LIKERT,
                config={"options": list(SCALE)},
            )

    def save(self, questions):
        serializer = AssessmentSerializer(self.assessment, data={"questions": questions}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        return list(
            self.assessment.questions.order_by("order").values_list("identifier", flat=True)
        )

    def without_ids(self):
        """What the editor sends: identifier and text, no database id."""
        return [
            {"identifier": q.identifier, "order": q.order, "text": q.text,
             "response_type": q.response_type, "config": q.config}
            for q in self.assessment.questions.order_by("order")
        ]

    def test_saving_without_ids_keeps_the_identifiers(self):
        self.assertEqual(self.save(self.without_ids()), ["sleep", "mood"])

    def test_saving_eight_times_keeps_the_identifiers(self):
        """The live failure, reproduced.

        Before the fix this returned sleep-2-2-2-2-2-2-2-2.
        """
        for _ in range(8):
            self.save(self.without_ids())
        self.assertEqual(
            list(self.assessment.questions.order_by("order").values_list("identifier", flat=True)),
            ["sleep", "mood"],
        )

    def test_no_identifier_ever_gains_a_numeric_suffix(self):
        for _ in range(8):
            self.save(self.without_ids())
        for identifier in self.assessment.questions.values_list("identifier", flat=True):
            self.assertNotIn("-2", identifier)

    def test_an_answer_recorded_today_still_matches_after_a_save(self):
        """Why it matters, stated as the thing that actually breaks."""
        recorded = set(self.assessment.questions.values_list("identifier", flat=True))
        self.save(self.without_ids())
        after = set(self.assessment.questions.values_list("identifier", flat=True))
        self.assertEqual(recorded, after)

    def test_saving_with_ids_still_keeps_the_identifiers(self):
        payload = [
            {"id": q.id, "identifier": q.identifier, "order": q.order, "text": q.text,
             "response_type": q.response_type, "config": q.config}
            for q in self.assessment.questions.order_by("order")
        ]
        self.assertEqual(self.save(payload), ["sleep", "mood"])

    def test_editing_a_question_does_not_rename_it(self):
        payload = self.without_ids()
        payload[0]["text"] = "How well did you sleep last night?"
        self.assertEqual(self.save(payload), ["sleep", "mood"])
        self.assertEqual(
            self.assessment.questions.get(identifier="sleep").text,
            "How well did you sleep last night?",
        )

    def test_a_genuinely_new_question_still_gets_a_free_identifier(self):
        # The uniqueness rule still has to work; it just must not fire on a
        # question that already owns the name.
        payload = self.without_ids()
        payload.append({"identifier": "sleep", "order": 3, "text": "A different question",
                        "response_type": "likert", "config": {"options": list(SCALE)}})
        identifiers = self.save(payload)
        self.assertEqual(identifiers[:2], ["sleep", "mood"])
        self.assertEqual(len(identifiers), 3)
        self.assertNotIn(identifiers[2], ("sleep", "mood"))

    def test_two_new_questions_claiming_the_same_name_are_kept_apart(self):
        payload = self.without_ids()
        for order in (3, 4):
            payload.append({"identifier": "energy", "order": order, "text": f"New {order}",
                            "response_type": "likert", "config": {"options": list(SCALE)}})
        identifiers = self.save(payload)
        self.assertEqual(len(set(identifiers)), len(identifiers))

    def test_a_removed_question_is_still_removed(self):
        payload = self.without_ids()[:1]
        self.assertEqual(self.save(payload), ["sleep"])

    def test_a_question_with_no_identifier_gets_one_from_its_text(self):
        payload = self.without_ids()
        payload.append({"order": 3, "text": "Appetite this week",
                        "response_type": "likert", "config": {"options": list(SCALE)}})
        identifiers = self.save(payload)
        self.assertEqual(identifiers[2], "appetite-this-week")
