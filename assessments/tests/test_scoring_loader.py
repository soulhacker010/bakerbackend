"""Reading a card off an assessment, and proving the move changes nothing.

The important test here is ``LegacyEquivalenceTests``: for the same answers, a
derived card must produce the same total the live engine produces today. Without
that, migrating the eight live assessments would silently move people between
bands.
"""
import itertools

from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, ScoringCard, score_assessment
from assessments.scoring.loader import (
    card_from_dict,
    card_to_dict,
    legacy_card,
    option_map,
    parse_option_value,
    question_rule,
)
from assessments.serializers import AssessmentResponseSerializer

# Both option layouts found in the live database.
NUMBER_FIRST = ["0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often"]
NUMBER_LAST = ["None (0)", "Mild (1)", "Moderate (2)", "Severe (3)", "Very Severe (4)"]


def question(identifier, options, domain="general"):
    """An unsaved question, which is all the loader reads."""
    return AssessmentQuestion(
        identifier=identifier,
        domain=domain,
        config={"options": list(options)},
        response_type=AssessmentQuestion.ResponseType.LIKERT,
        order=1,
        text=identifier,
    )


class OptionParsingTests(SimpleTestCase):
    def test_number_first_layout(self):
        self.assertEqual(parse_option_value("0 - Never"), 0)
        self.assertEqual(parse_option_value("3 - Often"), 3)

    def test_number_last_layout(self):
        self.assertEqual(parse_option_value("Very Severe (4)"), 4)
        self.assertEqual(parse_option_value("None (0)"), 0)

    def test_option_with_no_number_has_no_value(self):
        # The CAGE "alcohol or drugs?" item is a classification, not a score.
        self.assertIsNone(parse_option_value("Alcohol"))

    def test_an_option_with_two_numbers_is_refused_rather_than_guessed(self):
        # "6-7 hours - 1 point" would score as 6 under a first-number rule.
        with self.assertRaises(CardError):
            parse_option_value("6-7 hours - 1 point")

    def test_answers_resolve_from_their_text(self):
        mapping = option_map(NUMBER_LAST)
        self.assertEqual(mapping["Moderate (2)"], 2)
        self.assertEqual(mapping["moderate (2)"], 2)
        self.assertEqual(mapping["2"], 2)


class QuestionRuleTests(SimpleTestCase):
    def test_scale_is_read_from_the_options(self):
        rule = question_rule(question("q1", NUMBER_LAST))
        self.assertEqual(rule.scale_min, 0)
        self.assertEqual(rule.scale_max, 4)
        self.assertTrue(rule.scored)

    def test_a_question_whose_options_carry_no_numbers_is_not_scored(self):
        rule = question_rule(question("q5", ["Alcohol", "Drugs"]))
        self.assertFalse(rule.scored)

    def test_answers_arriving_as_option_text_are_understood(self):
        rule = question_rule(question("q1", NUMBER_LAST))
        self.assertEqual(rule.value_of("Moderate (2)"), 2)
        self.assertEqual(rule.value_of("Very Severe (4)"), 4)

    def test_free_text_is_not_mined_for_a_number(self):
        rule = question_rule(question("q1", NUMBER_LAST))
        self.assertIsNone(rule.value_of("about 3 times a week"))


class LegacyEquivalenceTests(SimpleTestCase):
    """The derived card must agree with the live engine, answer for answer."""

    CONFIG = {
        "bands": [
            {"id": "level-1", "label": "Level 1", "min": 0, "max": 15, "description": "a"},
            {"id": "level-2", "label": "Level 2", "min": 16, "max": 30, "description": "b"},
            {"id": "level-3", "label": "Level 3", "min": 31, "max": 45, "description": "c"},
            {"id": "level-4", "label": "Level 4", "min": 46, "max": 60, "description": "d"},
        ]
    }

    def old_engine(self, responses):
        serializer = AssessmentResponseSerializer()
        payload, _ = serializer._calculate_sum_score(self.CONFIG, responses)
        return payload

    def test_every_combination_of_answers_scores_the_same_both_ways(self):
        questions = [question(f"q{i}", NUMBER_FIRST) for i in range(1, 6)]
        card = legacy_card(questions, self.CONFIG)

        checked = 0
        for combo in itertools.product(NUMBER_FIRST, repeat=5):
            answers = {f"q{i}": combo[i - 1] for i in range(1, 6)}
            old = self.old_engine(answers)
            new = score_assessment(card, answers).score("total")
            self.assertEqual(new.value, old["total"], answers)
            self.assertEqual(new.band_id, old.get("band"), answers)
            checked += 1
        self.assertEqual(checked, 4 ** 5)

    def test_the_number_last_layout_also_agrees(self):
        questions = [question(f"q{i}", NUMBER_LAST) for i in range(1, 5)]
        card = legacy_card(questions, self.CONFIG)
        for combo in itertools.product(NUMBER_LAST, repeat=4):
            answers = {f"q{i}": combo[i - 1] for i in range(1, 5)}
            old = self.old_engine(answers)
            new = score_assessment(card, answers).score("total")
            self.assertEqual(new.value, old["total"], answers)

    def test_a_score_outside_every_band_is_bandless_in_both(self):
        questions = [question(f"q{i}", NUMBER_FIRST) for i in range(1, 30)]
        card = legacy_card(questions, self.CONFIG)
        answers = {f"q{i}": "3 - Often" for i in range(1, 30)}   # 87, past the top band
        old = self.old_engine(answers)
        new = score_assessment(card, answers).score("total")
        self.assertEqual(new.value, 87)
        self.assertEqual(new.value, old["total"])
        self.assertIsNone(new.band_id)
        self.assertIsNone(old.get("band"))


class FootHealthCorrectionTests(SimpleTestCase):
    """What the conversion changes, recorded so the difference is deliberate.

    The instrument converts its 0-60 total onto 0-100 by (sum x 5) / 3. The live
    engine never did, so a raw 38 is read against 0-100 bands and reported two
    severities lower than the document intends.
    """

    BANDS = [
        {"id": "level-1", "label": "Level 1", "min": 0, "max": 24,
         "description": "Mild or no foot health issues"},
        {"id": "level-2", "label": "Level 2", "min": 25, "max": 50,
         "description": "Moderate; evaluation advised"},
        {"id": "level-3", "label": "Level 3", "min": 51, "max": 100,
         "description": "Significant; urgent evaluation recommended"},
    ]

    def test_without_the_conversion_a_raw_thirty_eight_reads_as_moderate(self):
        questions = [question(f"f{i}", NUMBER_LAST) for i in range(1, 16)]
        card = legacy_card(questions, {"bands": self.BANDS})
        answers = {f"f{i}": "Moderate (2)" for i in range(1, 16)}
        answers["f1"] = "Very Severe (4)"
        answers["f2"] = "Very Severe (4)"
        answers["f3"] = "Very Severe (4)"
        answers["f4"] = "Very Severe (4)"
        total = score_assessment(card, answers).score("total")
        self.assertEqual(total.value, 38)
        self.assertEqual(total.band_id, "level-2")

    def test_with_the_conversion_the_same_answers_read_as_urgent(self):
        from assessments.scoring import Band, ScoreRule, Transform
        rules = [question_rule(question(f"f{i}", NUMBER_LAST)) for i in range(1, 16)]
        card = ScoringCard(questions=rules, scores=[ScoreRule(
            id="total", label="Foot Health Score", domain="general",
            transform=Transform(kind="linear", multiply=5, divide=3),
            bands=[Band(b["id"], b["label"], b["min"], b["max"], b["description"])
                   for b in self.BANDS],
        )])
        answers = {f"f{i}": "Moderate (2)" for i in range(1, 16)}
        for i in range(1, 5):
            answers[f"f{i}"] = "Very Severe (4)"
        total = score_assessment(card, answers).score("total")
        self.assertEqual(total.value, 63.33)
        self.assertEqual(total.band_id, "level-3")
        self.assertIn("urgent", total.interpretation.lower())


class RoundTripTests(SimpleTestCase):
    def test_a_card_survives_being_stored_and_read_back(self):
        questions = [question(f"q{i}", NUMBER_LAST) for i in range(1, 6)]
        original = legacy_card(questions, {"bands": [
            {"id": "low", "label": "Low", "min": 0, "max": 10},
            {"id": "high", "label": "High", "min": 11, "max": 20},
        ]})
        restored = card_from_dict(card_to_dict(original))

        answers = {f"q{i}": "Moderate (2)" for i in range(1, 6)}
        before = score_assessment(original, answers).score("total")
        after = score_assessment(restored, answers).score("total")
        self.assertEqual(after.value, before.value)
        self.assertEqual(after.band_id, before.band_id)

    def test_weights_reversals_and_flags_survive_the_round_trip(self):
        from assessments.scoring import Band, FlagRule, QuestionRule, ScoreRule
        original = ScoringCard(
            questions=[
                QuestionRule(identifier="q1", domain="d", scale_max=3, weight=1.5),
                QuestionRule(identifier="q2", domain="d", scale_max=3, reverse=True),
            ],
            scores=[ScoreRule(id="total", label="Total", domain="d", granularity=0.5,
                              bands=[Band("all", "All", 0, 7.5, "")])],
            flags=[FlagRule(id="f1", message="check", questions=["q1"],
                            operator=">=", value=1)],
            standing_notice="Provisional.",
        )
        restored = card_from_dict(card_to_dict(original))
        self.assertEqual(restored.questions[0].weight, 1.5)
        self.assertTrue(restored.questions[1].reverse)
        self.assertEqual(restored.scores[0].granularity, 0.5)
        self.assertEqual(restored.flags[0].id, "f1")
        self.assertEqual(restored.standing_notice, "Provisional.")

        answers = {"q1": 1, "q2": 0}
        self.assertEqual(
            score_assessment(restored, answers).score("total").value,
            score_assessment(original, answers).score("total").value,
        )
