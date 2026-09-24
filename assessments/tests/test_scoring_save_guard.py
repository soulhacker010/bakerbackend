"""Saving an assessment with a scoring card that cannot produce a usable result.

Every card below is refused. The messages matter as much as the refusal: whoever
is writing the card needs to be told what is wrong with it, not just that
something is.
"""
from django.test import TestCase

from assessments.models import Assessment, AssessmentQuestion
from assessments.serializers import AssessmentSerializer

OPTIONS = ["0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often"]


def question_payload(identifier, order, domain="general"):
    return {
        "identifier": identifier,
        "order": order,
        "text": f"Question {order}",
        "response_type": AssessmentQuestion.ResponseType.LIKERT,
        "required": True,
        "config": {"options": list(OPTIONS)},
        "domain": domain,
    }


def card_question(identifier, domain="general"):
    return {
        "identifier": identifier,
        "domain": domain,
        "weight": 1.0,
        "reverse": False,
        "scale_min": 0,
        "scale_max": 3,
        "scored": True,
    }


class SaveGuardTests(TestCase):
    QUESTION_COUNT = 10   # 10 questions on 0-3, so totals run 0-30

    def payload(self, bands=None, card_overrides=None, with_card=True):
        questions = [question_payload(f"q{i}", i) for i in range(1, self.QUESTION_COUNT + 1)]
        data = {
            "title": "Guarded Assessment",
            "status": Assessment.Status.DRAFT,
            "questions": questions,
        }
        if not with_card:
            data["scoring"] = {"method": "sum", "configuration": {"bands": bands or []}}
            return data

        card = {
            "questions": [card_question(f"q{i}") for i in range(1, self.QUESTION_COUNT + 1)],
            "scores": [{
                "id": "total",
                "label": "Total",
                "method": "sum",
                "domain": "general",
                "bands": bands if bands is not None else [
                    {"id": "low", "label": "Low", "min": 0, "max": 15},
                    {"id": "high", "label": "High", "min": 16, "max": 30},
                ],
            }],
        }
        if card_overrides:
            card.update(card_overrides)
        data["scoring"] = {"method": "sum", "configuration": {"card": card}}
        return data

    def errors_for(self, data):
        serializer = AssessmentSerializer(data=data)
        self.assertFalse(serializer.is_valid(), "expected this card to be refused")
        return " ".join(str(m) for m in serializer.errors.get("scoring", []))

    # ------------------------------------------------------------------ #

    def test_a_good_card_saves(self):
        serializer = AssessmentSerializer(data=self.payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        assessment = serializer.save()
        self.assertEqual(assessment.questions.count(), self.QUESTION_COUNT)

    def test_an_assessment_without_a_card_is_unaffected(self):
        serializer = AssessmentSerializer(data=self.payload(with_card=False, bands=[
            {"id": "anything", "label": "Anything", "min": 0, "max": 5},
        ]))
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_a_gap_between_bands_is_refused(self):
        message = self.errors_for(self.payload(bands=[
            {"id": "low", "label": "Low", "min": 0, "max": 10},
            {"id": "high", "label": "High", "min": 18, "max": 30},
        ]))
        self.assertIn("nothing covers 10 to 18", message)

    def test_bands_that_stop_short_of_the_top_are_refused(self):
        message = self.errors_for(self.payload(bands=[
            {"id": "low", "label": "Low", "min": 0, "max": 12},
        ]))
        self.assertIn("scores can reach 30", message)
        self.assertIn("18 points return no interpretation", message)

    def test_overlapping_bands_are_refused(self):
        message = self.errors_for(self.payload(bands=[
            {"id": "low", "label": "Low", "min": 0, "max": 15},
            {"id": "high", "label": "High", "min": 15, "max": 30},
        ]))
        self.assertIn("overlap at 15", message)

    def test_a_malformed_card_is_refused_with_the_reason(self):
        message = self.errors_for(self.payload(card_overrides={
            "scores": [{"id": "total", "label": "Total", "domain": "general",
                        "questions": ["q1"]}],   # two sources at once
        }))
        self.assertIn("malformed", message.lower())

    def test_a_card_naming_a_question_the_assessment_lacks_is_refused(self):
        card_questions = [card_question(f"q{i}") for i in range(1, self.QUESTION_COUNT + 1)]
        card_questions.append(card_question("ghost"))
        message = self.errors_for(self.payload(card_overrides={"questions": card_questions}))
        self.assertIn("does not have", message)
        self.assertIn("ghost", message)

    def test_a_question_left_off_the_card_is_refused(self):
        """Silently unscored questions are the failure this whole build exists for."""
        card_questions = [card_question(f"q{i}") for i in range(1, self.QUESTION_COUNT)]
        message = self.errors_for(self.payload(card_overrides={"questions": card_questions}))
        self.assertIn("never count towards a score", message)
        self.assertIn("q10", message)

    def test_a_question_may_be_excluded_deliberately(self):
        card_questions = [card_question(f"q{i}") for i in range(1, self.QUESTION_COUNT + 1)]
        card_questions[-1]["scored"] = False          # explicit, so allowed
        data = self.payload(card_overrides={"questions": card_questions}, bands=[
            {"id": "low", "label": "Low", "min": 0, "max": 13},
            {"id": "high", "label": "High", "min": 14, "max": 27},
        ])
        serializer = AssessmentSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_unreachable_bands_are_only_a_warning_and_still_save(self):
        serializer = AssessmentSerializer(data=self.payload(bands=[
            {"id": "all", "label": "All", "min": 0, "max": 40},   # top is 30
        ]))
        self.assertTrue(serializer.is_valid(), serializer.errors)


class UpdateGuardTests(TestCase):
    """The guard applies when editing an existing assessment too."""

    def setUp(self):
        self.assessment = Assessment.objects.create(title="Existing", slug="existing")
        for i in range(1, 6):
            AssessmentQuestion.objects.create(
                assessment=self.assessment,
                identifier=f"q{i}", order=i, text=f"Q{i}",
                response_type=AssessmentQuestion.ResponseType.LIKERT,
                config={"options": list(OPTIONS)}, domain="general",
            )

    def card(self, bands):
        return {"method": "sum", "configuration": {"card": {
            "questions": [card_question(f"q{i}") for i in range(1, 6)],
            "scores": [{"id": "total", "label": "Total", "method": "sum",
                        "domain": "general", "bands": bands}],
        }}}

    def test_editing_in_a_broken_card_is_refused(self):
        serializer = AssessmentSerializer(
            self.assessment,
            data={"scoring": self.card([{"id": "low", "label": "Low", "min": 0, "max": 3}])},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("12 points return no interpretation",
                      " ".join(str(m) for m in serializer.errors["scoring"]))

    def test_editing_in_a_sound_card_succeeds(self):
        serializer = AssessmentSerializer(
            self.assessment,
            data={"scoring": self.card([
                {"id": "low", "label": "Low", "min": 0, "max": 7},
                {"id": "high", "label": "High", "min": 8, "max": 15},
            ])},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.assessment.refresh_from_db()
        self.assertIn("card", self.assessment.scoring.configuration)
