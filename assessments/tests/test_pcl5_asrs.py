"""PCL-5 and ASRS, held to their published scoring.

Both are live on the editor's default four-point frequency scale rather than
their own, which is the fault these cards exist to make impossible:

* the PCL-5 total runs 0-60 instead of 0-80, so its published cut-off of 31 sits
  at a completely different place on the scale;
* the ASRS has no "Very Often" at all, and three of its six screening items only
  count from "Often" upwards, so the screener cannot reach its own threshold.

Neither is scored on a scale it does not recognise. Refusing is the point.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.instruments import (
    ASRS_DOCUMENT_THRESHOLD,
    ASRS_PART_A_THRESHOLDS,
    ASRS_POSITIVE_AT,
    PCL5_CLUSTERS,
    PCL5_CUTOFF,
    asrs,
    pcl5,
)
from assessments.scoring.validation import ERROR, achievable_range, validate_card

PCL5_SCALE = [
    "0 - Not at all", "1 - A little bit", "2 - Moderately",
    "3 - Quite a bit", "4 - Extremely",
]
ASRS_SCALE = [
    "0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often", "4 - Very Often",
]
# What both are live with: the editor's default, one option short.
DEFAULT_SCALE = ["0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often"]


def questions(count, options, prefix="q"):
    return [
        AssessmentQuestion(
            identifier=f"{prefix}{i}", order=i, text=f"item {i}",
            response_type=AssessmentQuestion.ResponseType.LIKERT,
            config={"options": list(options)}, domain="general",
        )
        for i in range(1, count + 1)
    ]


class Pcl5Tests(SimpleTestCase):
    def setUp(self):
        self.card = pcl5(questions(20, PCL5_SCALE))

    def answers(self, index=0, overrides=None):
        payload = {f"q{i}": PCL5_SCALE[index] for i in range(1, 21)}
        for item, value in (overrides or {}).items():
            payload[f"q{item}"] = PCL5_SCALE[value]
        return payload

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_it_reports_the_four_dsm5_clusters_and_a_total(self):
        self.assertEqual(len(self.card.scores), 5)

    def test_the_total_runs_zero_to_eighty(self):
        # Twenty items at four points. Live it is 0-60, which is the bug.
        self.assertEqual(achievable_range(self.card)["total"], (0, 80))

    def test_each_cluster_covers_its_published_items(self):
        expected = {key: last - first + 1 for key, _, first, last in PCL5_CLUSTERS}
        for key, count in expected.items():
            held = [r for r in self.card.questions if r.domain == key]
            self.assertEqual(len(held), count, key)

    def test_every_item_belongs_to_exactly_one_cluster(self):
        self.assertEqual(len(self.card.questions), 20)
        self.assertEqual({r.domain for r in self.card.questions}, {k for k, _, _, _ in PCL5_CLUSTERS})

    def test_a_score_below_the_cut_off_reads_as_below(self):
        result = score_assessment(self.card, self.answers(index=0))
        self.assertEqual(result.score("total").value, 0)
        self.assertEqual(result.score("total").band_label, "Below the provisional cut-off")

    def test_the_cut_off_boundary_is_the_published_one(self):
        # 30 is below, 31 is at. Ten items at 3 gives 30.
        below = score_assessment(self.card, self.answers(0, {i: 3 for i in range(1, 11)}))
        self.assertEqual(below.score("total").value, PCL5_CUTOFF - 1)
        self.assertEqual(below.score("total").band_label, "Below the provisional cut-off")

        at = score_assessment(self.card, self.answers(0, {**{i: 3 for i in range(1, 11)}, 11: 1}))
        self.assertEqual(at.score("total").value, PCL5_CUTOFF)
        self.assertEqual(at.score("total").band_label, "At or above the provisional cut-off")

    def test_the_flag_fires_only_at_the_cut_off(self):
        below = score_assessment(self.card, self.answers(0, {i: 3 for i in range(1, 11)}))
        self.assertEqual(below.flags, [])
        at = score_assessment(self.card, self.answers(0, {**{i: 3 for i in range(1, 11)}, 11: 1}))
        self.assertEqual([f.id for f in at.flags], ["pcl5-cutoff"])

    def test_no_cluster_claims_a_range(self):
        # The published guidance gives a cut-off for the total and none for clusters.
        for key, _, _, _ in PCL5_CLUSTERS:
            rule = next(s for s in self.card.scores if s.id == key)
            self.assertEqual(list(rule.bands), [])

    def test_the_notice_says_the_cut_off_is_provisional(self):
        self.assertIn("provisional", self.card.standing_notice.lower())

    def test_it_refuses_the_scale_the_live_assessment_carries(self):
        with self.assertRaises(CardError) as caught:
            pcl5(questions(20, DEFAULT_SCALE))
        self.assertIn("0-4", str(caught.exception))

    def test_the_refusal_says_the_options_need_correcting(self):
        with self.assertRaises(CardError) as caught:
            pcl5(questions(20, DEFAULT_SCALE))
        self.assertIn("answer options", str(caught.exception))

    def test_it_refuses_a_different_number_of_items(self):
        with self.assertRaises(CardError):
            pcl5(questions(17, PCL5_SCALE))


class AsrsTests(SimpleTestCase):
    def setUp(self):
        self.card = asrs(questions(18, ASRS_SCALE))

    def answers(self, overrides=None):
        payload = {f"q{i}": ASRS_SCALE[0] for i in range(1, 19)}
        for item, value in (overrides or {}).items():
            payload[f"q{item}"] = ASRS_SCALE[value]
        return payload

    def part_a(self, overrides=None):
        """The WHO item count, which the document's total is reported beside."""
        return score_assessment(self.card, self.answers(overrides)).score("part_a_screen")

    def total(self, overrides=None):
        """The practice document's rule: Part A summed, threshold 14 of 24."""
        return score_assessment(self.card, self.answers(overrides)).score("part_a")

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_part_a_holds_the_first_six_items(self):
        held = [r for r in self.card.questions if r.domain == "part_a"]
        self.assertEqual(len(held), 6)
        self.assertEqual([r.identifier for r in held], [f"q{i}" for i in range(1, 7)])

    def test_part_b_holds_the_remaining_twelve(self):
        self.assertEqual(len([r for r in self.card.questions if r.domain == "part_b"]), 12)

    def test_items_one_to_three_count_from_sometimes(self):
        self.assertEqual(self.part_a({1: 2, 2: 2, 3: 2}).value, 3)

    def test_items_four_to_six_do_not_count_at_sometimes(self):
        """The published rule, and the reason a single threshold will not do.

        The shaded boxes start one step later for items 4 to 6.
        """
        self.assertEqual(self.part_a({4: 2, 5: 2, 6: 2}).value, 0)

    def test_items_four_to_six_count_from_often(self):
        self.assertEqual(self.part_a({4: 3, 5: 3, 6: 3}).value, 3)

    def test_three_counted_items_is_not_a_positive_screen(self):
        self.assertFalse(self.part_a({1: 2, 2: 2, 3: 2}).positive)

    def test_four_counted_items_is_a_positive_screen(self):
        self.assertTrue(self.part_a({1: 2, 2: 2, 3: 2, 4: 3}).positive)

    def test_the_published_threshold_is_four(self):
        self.assertEqual(ASRS_POSITIVE_AT, 4)

    def test_the_screen_flag_fires_on_a_positive_screen_only(self):
        quiet = score_assessment(self.card, self.answers({1: 2, 2: 2, 3: 2})).flags
        self.assertNotIn("asrs-screen", [f.id for f in quiet])
        fired = score_assessment(self.card, self.answers({1: 2, 2: 2, 3: 2, 4: 3})).flags
        self.assertIn("asrs-screen", [f.id for f in fired])

    # -- the practice document's own rule ----------------------------- #

    def test_part_a_is_summed_out_of_twenty_four(self):
        self.assertEqual(achievable_range(self.card)["part_a"], (0, 24))

    def test_the_documents_threshold_is_fourteen(self):
        self.assertEqual(ASRS_DOCUMENT_THRESHOLD, 14)

    def test_below_fourteen_reads_as_below_the_threshold(self):
        # Six items at Sometimes is 12.
        result = self.total({i: 2 for i in range(1, 7)})
        self.assertEqual(result.value, 12)
        self.assertEqual(result.band_label, "Below the threshold")

    def test_fourteen_reads_as_at_or_above(self):
        # Three at Very Often and one at Rarely is 13; add one more to reach 14.
        result = self.total({1: 4, 2: 4, 3: 4, 4: 2})
        self.assertEqual(result.value, 14)
        self.assertEqual(result.band_label, "At or above the threshold")

    def test_the_total_flag_fires_at_fourteen_and_not_below(self):
        below = score_assessment(self.card, self.answers({1: 4, 2: 4, 3: 4, 4: 1})).flags
        self.assertNotIn("asrs-total", [f.id for f in below])
        at = score_assessment(self.card, self.answers({1: 4, 2: 4, 3: 4, 4: 2})).flags
        self.assertIn("asrs-total", [f.id for f in at])

    def test_the_two_rules_can_disagree_and_both_are_reported(self):
        """Why both exist.

        Three items at Very Often and three at Rarely totals 15, which is above
        the document's threshold, while only three items count, which is below
        the WHO screener's. Reporting either alone would hide that.
        """
        answers = self.answers({1: 4, 2: 4, 3: 4, 4: 1, 5: 1, 6: 1})
        result = score_assessment(self.card, answers)
        self.assertEqual(result.score("part_a").value, 15)
        self.assertEqual(result.score("part_a").band_label, "At or above the threshold")
        self.assertEqual(result.score("part_a_screen").value, 3)
        self.assertFalse(result.score("part_a_screen").positive)

    def test_part_b_is_scored_separately_as_the_document_says(self):
        rule = next(s for s in self.card.scores if s.id == "part_b")
        self.assertEqual(list(rule.bands), [])
        self.assertEqual(achievable_range(self.card)["part_b"], (0, 48))

    def test_answering_everything_very_often_is_a_positive_screen(self):
        result = self.part_a({i: 4 for i in range(1, 19)})
        self.assertEqual(result.value, 6)
        self.assertTrue(result.positive)

    def test_part_b_is_reported_without_a_range(self):
        # Whether a dimensional total belongs here is the practice's decision.
        rule = next(s for s in self.card.scores if s.id == "part_b")
        self.assertEqual(list(rule.bands), [])

    def test_it_refuses_the_scale_the_live_assessment_carries(self):
        """Without "Very Often" the screener cannot reach its own threshold."""
        with self.assertRaises(CardError):
            asrs(questions(18, DEFAULT_SCALE))

    def test_it_refuses_a_different_number_of_items(self):
        with self.assertRaises(CardError):
            asrs(questions(12, ASRS_SCALE))

    def test_every_part_a_item_has_its_published_threshold(self):
        self.assertEqual(ASRS_PART_A_THRESHOLDS, {1: 2, 2: 2, 3: 2, 4: 3, 5: 3, 6: 3})

    def test_each_part_a_item_counts_only_its_qualifying_answers(self):
        # An answer may arrive as the label or as the bare number, so the set
        # holds several spellings of each; what matters is which options are in.
        by_id = {r.identifier: r for r in self.card.questions}
        early, late = by_id["q1"].qualifying_values, by_id["q4"].qualifying_values

        for option in ("2 - Sometimes", "3 - Often", "4 - Very Often"):
            self.assertIn(option, early)
        self.assertNotIn("1 - Rarely", early)

        self.assertNotIn("2 - Sometimes", late)
        for option in ("3 - Often", "4 - Very Often"):
            self.assertIn(option, late)

    def test_an_answer_submitted_as_a_bare_number_still_counts(self):
        by_id = {r.identifier: r for r in self.card.questions}
        self.assertIn("2", by_id["q1"].qualifying_values)
        self.assertNotIn("2", by_id["q4"].qualifying_values)

    def test_part_b_items_are_not_counted_at_all(self):
        by_id = {r.identifier: r for r in self.card.questions}
        self.assertIsNone(by_id["q7"].qualifying_values)
