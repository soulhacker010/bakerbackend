"""The performance and leadership instruments.

Two of these reproduce a problem in their own document rather than papering over
it. Those tests exist so the problem stays visible until the client decides what
the figure should be.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.performance import (
    executive_self_assessment,
    mental_skills,
    sleep_and_recovery,
)
from assessments.scoring.validation import ERROR, WARNING, achievable_range, validate_card

ZERO_THREE = ["0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often"]
ONE_FIVE = [
    "Not at All Competent (1)", "Somewhat Competent (2)", "Moderately Competent (3)",
    "Very Competent (4)", "Highly Competent (5)",
]
YES_NO = ["No", "Yes"]


def questions(count, options, start=1):
    return [
        AssessmentQuestion(
            identifier=f"q{i}", order=i, text=f"item {i}",
            response_type=AssessmentQuestion.ResponseType.LIKERT,
            config={"options": list(options)}, domain="general",
        )
        for i in range(start, start + count)
    ]


class SleepAndRecoveryTests(SimpleTestCase):
    def setUp(self):
        self.card = sleep_and_recovery(questions(15, ZERO_THREE) + questions(7, YES_NO, start=16))

    def answers(self, scored_values, flags=None):
        payload = {f"q{i}": ZERO_THREE[v] for i, v in enumerate(scored_values, 1)}
        payload.update({f"q{i}": (flags or {}).get(i, "No") for i in range(16, 23)})
        return payload

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_only_the_first_fifteen_questions_are_scored(self):
        self.assertEqual(achievable_range(self.card)["overall"], (0, 45))
        overall = score_assessment(self.card, self.answers([3] * 15)).score("overall")
        self.assertEqual(overall.value, 45)
        self.assertEqual(overall.applicable, 15)

    def test_the_documented_section_ranges(self):
        ranges = achievable_range(self.card)
        self.assertEqual(ranges["quantity"], (0, 6))
        self.assertEqual(ranges["continuity"], (0, 9))
        self.assertEqual(ranges["restoration"], (0, 9))
        self.assertEqual(ranges["circadian"], (0, 6))
        self.assertEqual(ranges["performance"], (0, 15))

    def test_a_red_flag_answered_yes_never_moves_the_score(self):
        without = score_assessment(self.card, self.answers([1] * 15))
        with_flags = score_assessment(
            self.card, self.answers([1] * 15, flags={i: "Yes" for i in range(16, 23)})
        )
        self.assertEqual(without.score("overall").value, 15)
        self.assertEqual(with_flags.score("overall").value, 15)

    def test_a_single_yes_flags_while_the_score_sits_in_the_lowest_band(self):
        """The case the document warns about in as many words."""
        result = score_assessment(self.card, self.answers([0] * 15, flags={17: "Yes"}))
        self.assertEqual(result.score("overall").value, 0)
        self.assertEqual(result.score("overall").band_id, "low")
        # Each red flag raises its own alert, naming the item.
        self.assertEqual([f.id for f in result.flags], ["sleep-red-flag-17"])

    def test_two_red_flags_raise_two_alerts(self):
        result = score_assessment(self.card, self.answers([0] * 15, flags={16: "Yes", 22: "Yes"}))
        self.assertEqual(sorted(f.id for f in result.flags), ["sleep-red-flag-16", "sleep-red-flag-22"])

    def test_no_flag_when_every_red_flag_is_no(self):
        self.assertEqual(score_assessment(self.card, self.answers([3] * 15)).flags, [])

    def test_the_standing_notice_is_carried(self):
        result = score_assessment(self.card, self.answers([1] * 15))
        self.assertIn("not be represented as clinically validated", result.notice)

    def test_the_wrong_number_of_questions_is_refused(self):
        with self.assertRaises(ValueError):
            sleep_and_recovery(questions(15, ZERO_THREE))


class ExecutiveSelfAssessmentTests(SimpleTestCase):
    def setUp(self):
        self.card = executive_self_assessment(questions(24, ONE_FIVE))

    def answers(self, values):
        return {f"q{i}": ONE_FIVE[v - 1] for i, v in enumerate(values, 1)}

    def test_the_scale_starts_at_one_so_the_lowest_total_is_twenty_four(self):
        self.assertEqual(achievable_range(self.card)["total"], (24, 120))

    def test_each_dimension_runs_three_to_fifteen(self):
        ranges = achievable_range(self.card)
        self.assertEqual(ranges["goal_setting"], (3, 15))
        self.assertEqual(ranges["self_monitoring"], (3, 15))

    def test_everything_at_five_reaches_one_hundred_and_twenty(self):
        result = score_assessment(self.card, self.answers([5] * 24))
        self.assertEqual(result.score("total").value, 120)
        self.assertEqual(result.score("total").band_id, "excellent")

    def test_everything_at_one_reads_as_poor(self):
        """The floor of the scale, and the practice's answer to what it means.

        The source document defined "0-23 (Poor)", which no submission could
        reach: twenty-four items that never score below 1 put the floor at 24,
        so the worst possible result read as Needs Improvement and Poor was
        dead text. Asked about it, the practice replied "Change to 0 - 24
        instead of 0 -23".
        """
        result = score_assessment(self.card, self.answers([1] * 24))
        self.assertEqual(result.score("total").value, 24)
        self.assertEqual(result.score("total").band_id, "poor")

    def test_twenty_five_is_the_first_needs_improvement_score(self):
        """Poor had to take 24 from Needs Improvement, not share it.

        Two bands both containing 24 is the fault that made a score of exactly
        100 read a level low on the ABA assessment: the first listed silently
        wins and nothing reports the clash.
        """
        result = score_assessment(self.card, self.answers([1] * 23 + [2]))
        self.assertEqual(result.score("total").value, 25)
        self.assertEqual(result.score("total").band_id, "needs-improvement")

    def test_no_band_is_now_unreachable_and_none_overlap(self):
        problems = validate_card(self.card)
        self.assertEqual([p for p in problems if p.severity == ERROR], [])
        self.assertEqual(
            [p.message for p in problems if "can never be reached" in p.message], []
        )

    def test_the_wrong_answer_scale_is_refused(self):
        with self.assertRaises(CardError):
            executive_self_assessment(questions(24, ZERO_THREE))


class MentalSkillsTests(SimpleTestCase):
    def setUp(self):
        self.card = mental_skills(questions(40, ONE_FIVE))

    def answers(self, values):
        return {f"q{i}": ONE_FIVE[v - 1] for i, v in enumerate(values, 1)}

    def test_a_domain_score_is_the_average_of_its_five_items(self):
        values = [4] * 5 + [1] * 35
        result = score_assessment(self.card, self.answers(values))
        self.assertEqual(result.score("domain1").value, 4.0)
        self.assertEqual(result.score("domain2").value, 1.0)

    def test_the_overall_index_is_the_average_of_the_eight_domain_averages(self):
        # Seven domains at 5.0 and one at 1.0 -> (5*7 + 1) / 8 = 4.5
        values = [1] * 5 + [5] * 35
        result = score_assessment(self.card, self.answers(values))
        self.assertEqual(result.score("domain1").value, 1.0)
        self.assertEqual(result.score("overall").value, 4.5)

    def test_the_index_runs_one_to_five_not_forty_to_two_hundred(self):
        self.assertEqual(achievable_range(self.card)["overall"], (1, 5))

    def test_a_domain_average_lands_on_fifths(self):
        values = [5, 5, 5, 5, 4] + [1] * 35     # 24 / 5
        result = score_assessment(self.card, self.answers(values))
        self.assertEqual(result.score("domain1").value, 4.8)

    def test_the_card_has_no_gaps_left(self):
        """The document's bands left 3.9 to 4.0 uncovered; the practice closed it."""
        problems = [p for p in validate_card(self.card) if p.severity == ERROR]
        self.assertEqual(problems, [], [p.message for p in problems])

    def test_a_score_between_the_documents_bands_goes_in_the_lower_one(self):
        """ "Lower band. Anything up until the minimum threshold of the next level
        stays below." - the practice, 16 October 2026.

        Six domains at 4.0 and two at 3.8 give 3.95.
        """
        values = [4] * 30 + [4, 4, 4, 4, 3] + [4, 4, 4, 4, 3]
        overall = score_assessment(self.card, self.answers(values)).score("overall")
        self.assertEqual(overall.value, 3.95)
        self.assertEqual(overall.band_id, "developing")

    def test_the_highest_index_below_four_is_still_developing(self):
        # Seven domains at 4.0 and one at 3.8 give 3.975.
        values = [4] * 35 + [4, 4, 4, 4, 3]
        overall = score_assessment(self.card, self.answers(values)).score("overall")
        self.assertLess(overall.value, 4.0)
        self.assertEqual(overall.band_id, "developing")

    def test_four_is_a_strength(self):
        overall = score_assessment(self.card, self.answers([4] * 40)).score("overall")
        self.assertEqual(overall.band_id, "strength")

    def test_the_wrong_number_of_questions_is_refused(self):
        with self.assertRaises(CardError):
            mental_skills(questions(39, ONE_FIVE))


def free_text(identifier, order):
    return AssessmentQuestion(identifier=identifier, order=order, text="notes",
                              response_type=AssessmentQuestion.ResponseType.FREE_TEXT,
                              config={}, domain="notes", required=False)


class AuditFollowUpTests(SimpleTestCase):
    """Items from the 20 Oct 2026 audit against the practice's documents."""

    def test_executive_self_assessment_uses_the_organizational_report(self):
        from assessments.scoring.card import ORGANISATIONAL
        self.assertEqual(executive_self_assessment(questions(24, ONE_FIVE)).report_style, ORGANISATIONAL)

    def test_executive_self_assessment_carries_justification_fields_unscored(self):
        qs = questions(24, ONE_FIVE) + [free_text("goal_setting-justification", 25),
                                        free_text("goal_setting-improvement", 26)]
        card = executive_self_assessment(qs)
        self.assertEqual({r.identifier for r in card.questions if not r.scored},
                         {"goal_setting-justification", "goal_setting-improvement"})
        answers = {f"q{i}": ONE_FIVE[4] for i in range(1, 25)}
        answers["goal_setting-justification"] = "Set quarterly OKRs."
        self.assertEqual(score_assessment(card, answers).score("total").value, 120)

    def test_mental_skills_flags_two_or_more_domains_below_three(self):
        card = mental_skills(questions(40, ONE_FIVE) + [free_text("open-question", 41)])
        one_low = [2] * 5 + [4] * 35
        two_low = [2] * 10 + [4] * 30
        ans = lambda v: {f"q{i}": ONE_FIVE[x - 1] for i, x in enumerate(v, 1)}
        self.assertEqual(score_assessment(card, ans(one_low)).flags, [])
        self.assertEqual([f.id for f in score_assessment(card, ans(two_low)).flags], ["multiple-domains-below-3"])


class MentalSkillsObserverTests(SimpleTestCase):
    def setUp(self):
        from assessments.scoring.performance import mental_skills_observer
        self.card = mental_skills_observer(questions(8, ONE_FIVE) + [free_text("observation-context", 9)])

    def test_card_is_sound_and_uses_the_screeners_domain_ids(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])
        self.assertEqual([s.id for s in self.card.scores], [f"domain{i}" for i in range(1, 9)] + ["overall"])

    def test_each_item_is_its_domains_score(self):
        values = [5, 1, 3, 4, 2, 5, 4, 3]
        result = score_assessment(self.card, {f"q{i}": ONE_FIVE[v - 1] for i, v in enumerate(values, 1)})
        self.assertEqual([result.score(f"domain{i}").value for i in range(1, 9)], values)
        self.assertEqual(result.score("overall").value, 3.38)
        self.assertEqual(result.score("domain2").band_id, "growth")
