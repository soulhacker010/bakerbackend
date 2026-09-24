"""The engine wired into real assessments and real submissions.

The behaviour being protected here is that switching an assessment onto a card is
deliberate and reversible, and that no configuration problem can ever stop a
respondent submitting.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from assessments.models import (
    Assessment,
    AssessmentQuestion,
    AssessmentResponse,
    AssessmentScoringConfig,
)
from assessments.scoring import ScoringCard, ScoreRule, Band, FlagRule, Transform
from assessments.scoring.loader import card_to_dict, question_rule
from assessments.serializers import AssessmentResponseSerializer

OPTIONS = ["None (0)", "Mild (1)", "Moderate (2)", "Severe (3)", "Very Severe (4)"]

LEGACY_BANDS = [
    {"id": "level-1", "label": "Level 1", "min": 0, "max": 24,
     "description": "Mild or no foot health issues"},
    {"id": "level-2", "label": "Level 2", "min": 25, "max": 50,
     "description": "Moderate; evaluation advised"},
    {"id": "level-3", "label": "Level 3", "min": 51, "max": 100,
     "description": "Significant; urgent evaluation recommended"},
]


class ScoringIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="clinician@example.com", password="pw-for-tests-only"
        )
        cls.assessment = Assessment.objects.create(
            title="Foot Health", slug="foot-health", status=Assessment.Status.PUBLISHED
        )
        for i in range(1, 16):
            AssessmentQuestion.objects.create(
                assessment=cls.assessment,
                identifier=f"f{i}",
                order=i,
                text=f"Question {i}",
                response_type=AssessmentQuestion.ResponseType.LIKERT,
                config={"options": list(OPTIONS)},
                domain="general",
            )
        cls.scoring = AssessmentScoringConfig.objects.create(
            assessment=cls.assessment,
            method=AssessmentScoringConfig.Method.SUM,
            configuration={"bands": LEGACY_BANDS},
        )

    def setUp(self):
        self.assessment.refresh_from_db()
        self.scoring.refresh_from_db()

    def answers(self, severe=4):
        """Four "very severe" answers and eleven "moderate": a raw total of 38."""
        payload = {f"f{i}": "Moderate (2)" for i in range(1, 16)}
        for i in range(1, severe + 1):
            payload[f"f{i}"] = "Very Severe (4)"
        return payload

    def score(self):
        serializer = AssessmentResponseSerializer()
        return serializer._calculate_score(self.assessment, self.answers())

    def store_card(self, card):
        self.scoring.configuration = {
            "bands": LEGACY_BANDS,
            "card": card_to_dict(card),
        }
        self.scoring.save(update_fields=["configuration"])
        self.assessment.refresh_from_db()

    # ----------------------------------------------------------------- #

    def test_without_a_card_nothing_changes(self):
        payload, highlights = self.score()
        self.assertEqual(payload["total"], 38)
        self.assertEqual(payload["band"], "level-2")
        self.assertNotIn("scores", payload)   # the legacy shape, untouched
        self.assertEqual(highlights, ["Moderate; evaluation advised"])

    def test_with_a_card_the_engine_takes_over(self):
        rules = [question_rule(q) for q in self.assessment.questions.all()]
        card = ScoringCard(questions=rules, scores=[ScoreRule(
            id="total", label="Foot Health Score", domain="general",
            transform=Transform(kind="linear", multiply=5, divide=3),
            bands=[Band(b["id"], b["label"], b["min"], b["max"], b["description"])
                   for b in LEGACY_BANDS],
        )])
        self.store_card(card)

        payload, highlights = self.score()
        # The conversion the instrument specifies, applied at last.
        self.assertEqual(payload["total"], 63.33)
        self.assertEqual(payload["band"], "level-3")
        self.assertIn("urgent", payload["interpretation"].lower())
        self.assertIn("urgent", highlights[0].lower())

    def test_the_legacy_keys_survive_so_the_dashboard_keeps_working(self):
        rules = [question_rule(q) for q in self.assessment.questions.all()]
        card = ScoringCard(questions=rules, scores=[ScoreRule(
            id="total", label="Total", domain="general",
            bands=[Band(b["id"], b["label"], b["min"], b["max"], b["description"])
                   for b in LEGACY_BANDS],
        )])
        self.store_card(card)

        payload, _ = self.score()
        for key in ("total", "band", "band_label", "interpretation"):
            self.assertIn(key, payload, key)
        # And the new shape sits alongside it.
        self.assertEqual(payload["version"], 2)
        self.assertEqual(len(payload["scores"]), 1)

    def test_subscales_and_flags_reach_the_stored_result(self):
        rules = [question_rule(q) for q in self.assessment.questions.all()]
        card = ScoringCard(
            questions=rules,
            scores=[
                ScoreRule(id="total", label="Total", domain="general",
                          bands=[Band("all", "All", 0, 60, "Everything")]),
            ],
            flags=[FlagRule(
                id="severe-pain", message="Severe pain reported on question 1.",
                severity="urgent", audience="both",
                questions=["f1"], operator=">=", value=4,
            )],
            standing_notice="Provisional.",
        )
        self.store_card(card)

        payload, highlights = self.score()
        self.assertEqual([f["id"] for f in payload["flags"]], ["severe-pain"])
        self.assertEqual(payload["flags"][0]["severity"], "urgent")
        self.assertEqual(payload["notice"], "Provisional.")
        self.assertIn("Severe pain reported on question 1.", highlights)

    def test_a_broken_card_falls_back_instead_of_rejecting_the_submission(self):
        """A configuration problem must never cost a respondent their answers."""
        self.scoring.configuration = {
            "bands": LEGACY_BANDS,
            # A score pointing at a question that does not exist.
            "card": {
                "questions": [{"identifier": "f1", "scale_max": 4}],
                "scores": [{"id": "total", "label": "Total", "questions": ["nope"]}],
            },
        }
        self.scoring.save(update_fields=["configuration"])
        self.assessment.refresh_from_db()

        with self.assertLogs("assessments.serializers", level="ERROR"):
            payload, highlights = self.score()

        # Scored the old way, exactly as before the card was added.
        self.assertEqual(payload["total"], 38)
        self.assertEqual(payload["band"], "level-2")

    def test_a_card_that_is_not_a_mapping_is_ignored(self):
        self.scoring.configuration = {"bands": LEGACY_BANDS, "card": "nonsense"}
        self.scoring.save(update_fields=["configuration"])
        self.assessment.refresh_from_db()
        payload, _ = self.score()
        self.assertEqual(payload["total"], 38)

    def test_an_empty_card_is_ignored(self):
        self.scoring.configuration = {"bands": LEGACY_BANDS, "card": {"questions": []}}
        self.scoring.save(update_fields=["configuration"])
        self.assessment.refresh_from_db()
        payload, _ = self.score()
        self.assertEqual(payload["total"], 38)

    def test_switching_back_restores_the_old_behaviour_exactly(self):
        rules = [question_rule(q) for q in self.assessment.questions.all()]
        card = ScoringCard(questions=rules, scores=[ScoreRule(
            id="total", label="Total", domain="general",
            transform=Transform(kind="linear", multiply=5, divide=3),
            bands=[Band(b["id"], b["label"], b["min"], b["max"], b["description"])
                   for b in LEGACY_BANDS],
        )])
        self.store_card(card)
        self.assertEqual(self.score()[0]["total"], 63.33)

        self.scoring.configuration = {"bands": LEGACY_BANDS}
        self.scoring.save(update_fields=["configuration"])
        self.assessment.refresh_from_db()
        self.assertEqual(self.score()[0]["total"], 38)


class StoredResponseTests(TestCase):
    """A full submission through the serializer, with a card in place."""

    @classmethod
    def setUpTestData(cls):
        cls.assessment = Assessment.objects.create(
            title="Two Domain", slug="two-domain", status=Assessment.Status.PUBLISHED
        )
        for domain in ("alpha", "beta"):
            for i in range(1, 4):
                AssessmentQuestion.objects.create(
                    assessment=cls.assessment,
                    identifier=f"{domain}{i}",
                    order=i,
                    text=f"{domain} {i}",
                    response_type=AssessmentQuestion.ResponseType.LIKERT,
                    config={"options": ["0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often"]},
                    domain=domain,
                )
        rules = [question_rule(q) for q in cls.assessment.questions.all()]
        card = ScoringCard(
            questions=rules,
            scores=[
                ScoreRule(id="alpha", label="Alpha", domain="alpha",
                          bands=[Band("a-low", "Low", 0, 4, "alpha low"),
                                 Band("a-high", "High", 5, 9, "alpha high")]),
                ScoreRule(id="beta", label="Beta", domain="beta",
                          bands=[Band("b-low", "Low", 0, 4, "beta low"),
                                 Band("b-high", "High", 5, 9, "beta high")]),
                ScoreRule(id="overall", label="Overall", scores=["alpha", "beta"],
                          bands=[Band("o-all", "All", 0, 18, "overall")]),
            ],
        )
        AssessmentScoringConfig.objects.create(
            assessment=cls.assessment,
            method=AssessmentScoringConfig.Method.SUM,
            configuration={"card": card_to_dict(card)},
        )

    def test_a_submission_stores_every_subscale(self):
        serializer = AssessmentResponseSerializer(data={
            "assessment_slug": "two-domain",
            "responses": [
                {"question_identifier": "alpha1", "value": "3 - Often"},
                {"question_identifier": "alpha2", "value": "3 - Often"},
                {"question_identifier": "alpha3", "value": "3 - Often"},
                {"question_identifier": "beta1", "value": "0 - Never"},
                {"question_identifier": "beta2", "value": "1 - Rarely"},
                {"question_identifier": "beta3", "value": "0 - Never"},
            ],
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()

        stored = AssessmentResponse.objects.get(pk=instance.pk)
        by_id = {s["id"]: s for s in stored.score["scores"]}
        self.assertEqual(by_id["alpha"]["value"], 9)
        self.assertEqual(by_id["alpha"]["band"], "a-high")
        self.assertEqual(by_id["beta"]["value"], 1)
        self.assertEqual(by_id["beta"]["band"], "b-low")
        self.assertEqual(by_id["overall"]["value"], 10)
        # The headline figure the dashboard reads.
        self.assertEqual(stored.score["total"], 10)
        self.assertIn("alpha high", stored.highlights)
        self.assertIn("beta low", stored.highlights)
