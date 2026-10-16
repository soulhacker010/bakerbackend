"""PC-PTSD-5 and the WHO-5, added for the Middlesex screening.

Both come from the client's October 2026 update, which specifies every item, the
answer scale and the interpretation bands. The figures asserted here are that
document's and the published instruments', not ours.

Two of the four screeners in that update are deliberately absent. The Brief
Resilience Scale was struck out by the practice, whose note reads "We can't post
it"; the Oldenburg Burnout Inventory is waiting on written permission.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, INSUFFICIENT_DATA, OK, score_assessment
from assessments.scoring.instruments import pc_ptsd_5, who5
from assessments.scoring.loader import card_from_dict, card_to_dict
from assessments.scoring.validation import ERROR, achievable_range, validate_card

YES_NO = ["0. NO", "1. YES"]

WHO5_SCALE = [
    "0. At no time",
    "1. Some of the time",
    "2. Less than half the time",
    "3. More than half the time",
    "4. Most of the time",
    "5. All of the time",
]


def build(count, options):
    return [
        AssessmentQuestion(
            identifier=f"q{i}", order=i, text=f"item {i}",
            response_type=AssessmentQuestion.ResponseType.SINGLE_CHOICE,
            config={"options": list(options)}, domain="general",
        )
        for i in range(1, count + 1)
    ]


# --------------------------------------------------------------------------- #
# PC-PTSD-5
# --------------------------------------------------------------------------- #

class PcPtsd5Tests(SimpleTestCase):
    def setUp(self):
        self.card = pc_ptsd_5(build(6, YES_NO))

    def answers(self, exposed=True, endorsed=0):
        """The gate, then ``endorsed`` of the five symptom items answered yes."""
        payload = {"q1": YES_NO[1] if exposed else YES_NO[0]}
        for i in range(2, 7):
            payload[f"q{i}"] = YES_NO[1] if i - 1 <= endorsed else YES_NO[0]
        return payload

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_the_total_runs_zero_to_five(self):
        self.assertEqual(achievable_range(self.card)["total"], (0, 5))

    def test_the_gate_question_is_not_part_of_the_total(self):
        """Six questions are asked and five are counted.

        Counting the exposure question would make the maximum six and push every
        exposed respondent one point closer to a positive screen.
        """
        self.assertEqual(len(self.card.questions), 6)
        self.assertEqual(len(self.card.questions_for(self.card.scores[0])), 5)

    def test_three_endorsed_is_a_positive_screen(self):
        result = score_assessment(self.card, self.answers(endorsed=3))
        self.assertEqual(result.score("total").value, 3)
        self.assertEqual(result.score("total").band_label, "Positive screen")

    def test_two_endorsed_is_not(self):
        result = score_assessment(self.card, self.answers(endorsed=2))
        self.assertEqual(result.score("total").value, 2)
        self.assertEqual(result.score("total").band_label, "Negative screen")

    def test_all_five_endorsed_reaches_the_top_of_the_scale(self):
        result = score_assessment(self.card, self.answers(endorsed=5))
        self.assertEqual(result.score("total").value, 5)
        self.assertEqual(result.score("total").band_label, "Positive screen")

    def test_no_trauma_exposure_ends_the_screen_at_zero(self):
        """The documented behaviour: "If the respondent answers 'no' to trauma
        exposure, the screen ends with a score of 0." """
        result = score_assessment(self.card, self.answers(exposed=False, endorsed=5))
        total = result.score("total")
        self.assertEqual(total.status, OK)
        self.assertEqual(total.value, 0)
        self.assertEqual(total.band_label, "Negative screen")

    def test_without_the_gate_those_same_answers_would_read_as_positive(self):
        """Why the gate is worth having.

        The platform has no skip logic, so a respondent reporting no trauma
        exposure is still shown the five symptom items. Answered without the
        gate, this submission is a five out of five.
        """
        ungated = score_assessment(
            pc_ptsd_5(build(6, YES_NO)), self.answers(exposed=True, endorsed=5)
        )
        self.assertEqual(ungated.score("total").value, 5)

    def test_no_exposure_is_reported_rather_than_left_implicit(self):
        result = score_assessment(self.card, self.answers(exposed=False))
        self.assertIn("pc-ptsd-5-no-exposure", [f.id for f in result.flags])

    def test_an_unanswered_gate_is_not_guessed_either_way(self):
        payload = self.answers(endorsed=4)
        payload.pop("q1")
        total = score_assessment(self.card, payload).score("total")
        self.assertEqual(total.status, INSUFFICIENT_DATA)
        self.assertIsNone(total.value)

    def test_the_stricter_cut_point_is_noted_only_where_it_disagrees(self):
        at_three = score_assessment(self.card, self.answers(endorsed=3))
        at_four = score_assessment(self.card, self.answers(endorsed=4))
        self.assertIn("pc-ptsd-5-stricter-cut-point", [f.id for f in at_three.flags])
        self.assertNotIn("pc-ptsd-5-stricter-cut-point", [f.id for f in at_four.flags])

    def test_the_notice_states_the_screen_is_not_a_diagnosis(self):
        self.assertIn("does not establish PTSD", self.card.standing_notice)

    def test_the_notice_credits_the_source_the_licence_requires(self):
        self.assertIn("National Center for PTSD", self.card.standing_notice)

    def test_it_refuses_a_different_number_of_questions(self):
        with self.assertRaises(CardError):
            pc_ptsd_5(build(5, YES_NO))

    def test_it_refuses_a_scale_that_is_not_yes_no(self):
        with self.assertRaises(CardError):
            pc_ptsd_5(build(6, ["0 - Never", "1 - Sometimes", "2 - Often"]))

    def test_the_gate_survives_being_stored_and_read_back(self):
        """Cards live in the database as JSON, so a gate that does not serialise
        would work in these tests and nowhere else."""
        restored = card_from_dict(card_to_dict(self.card))
        result = score_assessment(restored, self.answers(exposed=False, endorsed=5))
        self.assertEqual(result.score("total").value, 0)


# --------------------------------------------------------------------------- #
# WHO-5
# --------------------------------------------------------------------------- #

class Who5Tests(SimpleTestCase):
    def setUp(self):
        self.card = who5(build(5, WHO5_SCALE))

    def answers(self, each=0):
        return {f"q{i}": WHO5_SCALE[each] for i in range(1, 6)}

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_the_raw_score_runs_zero_to_twenty_five(self):
        self.assertEqual(achievable_range(self.card)["raw"], (0, 25))

    def test_the_percentage_runs_zero_to_one_hundred(self):
        self.assertEqual(achievable_range(self.card)["percentage"], (0, 100))

    def test_the_percentage_is_the_raw_score_times_four(self):
        for each in range(6):
            result = score_assessment(self.card, self.answers(each=each))
            self.assertEqual(
                result.score("percentage").value, result.score("raw").value * 4
            )

    def test_the_worst_possible_answer_is_very_low_well_being(self):
        result = score_assessment(self.card, self.answers(each=0))
        self.assertEqual(result.score("raw").value, 0)
        self.assertEqual(result.score("raw").band_label, "Very low well-being")

    def test_the_best_possible_answer_is_normal_to_high(self):
        result = score_assessment(self.card, self.answers(each=5))
        self.assertEqual(result.score("raw").value, 25)
        self.assertEqual(result.score("percentage").value, 100)
        self.assertEqual(result.score("raw").band_label, "Normal to high well-being")

    def test_a_high_score_is_the_good_one(self):
        """The opposite direction to every other screener on the platform, and the
        reason this must not be reported in the same words as a symptom scale."""
        low = score_assessment(self.card, self.answers(each=1))
        high = score_assessment(self.card, self.answers(each=4))
        self.assertLess(low.score("raw").value, high.score("raw").value)
        self.assertEqual(low.score("raw").band_label, "Very low well-being")
        self.assertEqual(high.score("raw").band_label, "Normal to high well-being")

    def test_the_cut_off_sits_between_twelve_and_thirteen(self):
        """Raw 12 is a percentage of 48 and below the cut-off; raw 13 is 52 and
        above it. The document gives the same cut-off in both forms."""
        twelve = score_assessment(self.card, {
            "q1": WHO5_SCALE[3], "q2": WHO5_SCALE[3], "q3": WHO5_SCALE[3],
            "q4": WHO5_SCALE[3], "q5": WHO5_SCALE[0],
        })
        self.assertEqual(twelve.score("raw").value, 12)
        self.assertEqual(twelve.score("percentage").value, 48)
        self.assertEqual(twelve.score("raw").band_label, "Low well-being")

        thirteen = score_assessment(self.card, {
            "q1": WHO5_SCALE[3], "q2": WHO5_SCALE[3], "q3": WHO5_SCALE[3],
            "q4": WHO5_SCALE[3], "q5": WHO5_SCALE[1],
        })
        self.assertEqual(thirteen.score("raw").value, 13)
        self.assertEqual(thirteen.score("percentage").value, 52)
        self.assertEqual(thirteen.score("raw").band_label, "Normal to high well-being")

    def test_below_the_cut_off_is_flagged_for_the_clinician(self):
        result = score_assessment(self.card, self.answers(each=2))
        self.assertEqual(result.score("raw").value, 10)
        self.assertIn("who5-below-cut-off", [f.id for f in result.flags])

    def test_above_the_cut_off_is_not_flagged(self):
        result = score_assessment(self.card, self.answers(each=3))
        self.assertEqual(result.score("raw").value, 15)
        self.assertNotIn("who5-below-cut-off", [f.id for f in result.flags])

    def test_every_reachable_percentage_lands_in_a_band(self):
        """The percentage moves in fours, so its bands sit four apart. Nothing
        reachable may fall between them."""
        for each in range(6):
            result = score_assessment(self.card, self.answers(each=each))
            self.assertIsNotNone(
                result.score("percentage").band_label,
                "a percentage of %s returned no interpretation"
                % result.score("percentage").value,
            )

    def test_the_raw_score_is_the_headline(self):
        self.assertEqual(self.card.primary().id, "raw")

    def test_the_notice_carries_the_attribution_the_licence_requires(self):
        self.assertIn("CC BY-NC-SA 3.0 IGO", self.card.standing_notice)
        self.assertIn("do not imply endorsement", self.card.standing_notice)

    def test_the_notice_says_which_direction_is_good(self):
        self.assertIn("A high score is the good one", self.card.standing_notice)

    def test_it_refuses_a_different_number_of_questions(self):
        with self.assertRaises(CardError):
            who5(build(6, WHO5_SCALE))

    def test_it_refuses_the_editor_default_scale(self):
        """The failure that put PCL-5 and ASRS on the wrong buttons. A WHO-5 on
        nought to three tops out at 15, so its own cut-off of 13 would sit near
        the ceiling instead of the middle."""
        with self.assertRaises(CardError):
            who5(build(5, ["0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often"]))

    def test_it_survives_being_stored_and_read_back(self):
        restored = card_from_dict(card_to_dict(self.card))
        result = score_assessment(restored, self.answers(each=2))
        self.assertEqual(result.score("raw").value, 10)
        self.assertEqual(result.score("percentage").value, 40)
