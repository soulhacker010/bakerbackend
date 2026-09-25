"""The ABA trainer observation form, which was reporting one number for ten areas.

The total was never wrong. It was simply the only thing reported, so a trainer
could see that a parent was around the middle without seeing that they were
perfect on one skill area and had not started on another.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.aba import (
    ITEMS_PER_AREA,
    SKILL_AREAS,
    aba_caregiver_skills,
    aba_trainer_observation,
)
from assessments.scoring.validation import ERROR, achievable_range, validate_card

SCALE = [
    "Not at All Competent (1)",
    "Somewhat Competent (2)",
    "Moderately Competent (3)",
    "Very Competent(4)",
    "Highly Competent (5)",
]


def questions(count=50, options=None, tags=None):
    """Fifty questions, interleaved across the ten areas as the live form is."""
    labels = tags if tags is not None else [label for _, label in SKILL_AREAS]
    return [
        AssessmentQuestion(
            identifier=f"a{i}", order=i, text=f"item {i}",
            response_type=AssessmentQuestion.ResponseType.LIKERT,
            config={"options": list(options or SCALE)},
            domain=labels[(i - 1) % len(labels)],
        )
        for i in range(1, count + 1)
    ]


class AbaTrainerObservationTests(SimpleTestCase):
    def setUp(self):
        self.card = aba_trainer_observation(questions())

    def answers(self, default=2, by_area=None):
        """Every item at ``default``, with whole areas overridden by name."""
        payload = {}
        for rule in self.card.questions:
            index = SKILL_AREAS and next(
                (i for i, (_, label) in enumerate(SKILL_AREAS) if label == rule.domain), None
            )
            choice = (by_area or {}).get(rule.domain, default)
            payload[rule.identifier] = SCALE[choice]
            assert index is not None
        return payload

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_it_reports_ten_areas_and_a_total(self):
        self.assertEqual(len(self.card.scores), 11)

    def test_each_area_runs_five_to_twenty_five(self):
        ranges = achievable_range(self.card)
        for key, _ in SKILL_AREAS:
            self.assertEqual(ranges[key], (5, 25))

    def test_the_total_runs_fifty_to_two_hundred_and_fifty(self):
        # The scale starts at 1, not 0, so fifty items cannot total less than 50.
        self.assertEqual(achievable_range(self.card)["total"], (50, 250))

    def test_the_total_ranges_are_unchanged_and_reach_the_maximum(self):
        total = next(s for s in self.card.scores if s.id == "total")
        self.assertEqual(max(b.maximum for b in total.bands), 250)

    def test_the_total_still_reads_the_way_it_always_did(self):
        result = score_assessment(self.card, self.answers(default=2))
        self.assertEqual(result.score("total").value, 150)
        self.assertEqual(result.score("total").band_label, "Moderate Competency")

    def test_an_area_the_parent_has_not_started_is_now_visible(self):
        """The whole point.

        Two parents can both total 150 and need completely different sessions.
        """
        mixed = self.answers(default=2, by_area={
            "Understanding ABA Principles": 4,
            "Managing Challenging Behaviors": 0,
        })
        result = score_assessment(self.card, mixed)
        self.assertEqual(result.score("total").value, 150)
        self.assertEqual(result.score("understanding_aba").value, 25)
        self.assertEqual(result.score("challenging_behaviors").value, 5)

    def test_a_flat_profile_and_a_mixed_one_no_longer_look_the_same(self):
        flat = score_assessment(self.card, self.answers(default=2))
        mixed = score_assessment(self.card, self.answers(default=2, by_area={
            "Understanding ABA Principles": 4,
            "Managing Challenging Behaviors": 0,
        }))
        self.assertEqual(flat.score("total").value, mixed.score("total").value)
        self.assertNotEqual(
            [s.value for s in flat.scores], [s.value for s in mixed.scores]
        )

    def test_areas_carry_no_invented_ranges(self):
        # None were supplied, so none are claimed.
        for key, _ in SKILL_AREAS:
            rule = next(s for s in self.card.scores if s.id == key)
            self.assertEqual(list(rule.bands), [])

    def test_the_notice_says_the_ranges_belong_to_the_total(self):
        self.assertIn("total", self.card.standing_notice.lower())

    def test_the_lowest_possible_result_is_limited_competency(self):
        result = score_assessment(self.card, self.answers(default=0))
        self.assertEqual(result.score("total").value, 50)
        self.assertEqual(result.score("total").band_label, "Limited Competency")

    def test_the_highest_possible_result_is_strong_competency(self):
        result = score_assessment(self.card, self.answers(default=4))
        self.assertEqual(result.score("total").value, 250)
        self.assertEqual(result.score("total").band_label, "Strong Competency")

    def test_sections_are_read_from_the_tag_not_from_position(self):
        """The live form interleaves its questions.

        Grouping by position would put five consecutive items into one area and
        score every section against the wrong five answers.
        """
        rules = {r.identifier: r.domain for r in self.card.questions}
        self.assertNotEqual(rules["a1"], rules["a2"])
        self.assertEqual(rules["a1"], rules["a11"])

    def test_it_refuses_a_different_number_of_questions(self):
        with self.assertRaises(CardError):
            aba_trainer_observation(questions(count=40))

    def test_it_refuses_a_scale_that_is_not_one_to_five(self):
        with self.assertRaises(CardError):
            aba_trainer_observation(questions(options=["0 - No", "1 - Yes"]))

    def test_it_refuses_a_skill_area_it_does_not_recognise(self):
        wrong = questions()
        wrong[0].domain = "Toilet Training"
        with self.assertRaises(CardError):
            aba_trainer_observation(wrong)

    def test_it_refuses_areas_that_are_not_evenly_filled(self):
        uneven = questions()
        uneven[0].domain = uneven[1].domain
        with self.assertRaises(CardError):
            aba_trainer_observation(uneven)

    def test_the_refusal_names_the_area_that_is_wrong(self):
        wrong = questions()
        wrong[0].domain = "Toilet Training"
        with self.assertRaises(CardError) as caught:
            aba_trainer_observation(wrong)
        self.assertIn("Toilet Training", str(caught.exception))

    def test_every_area_holds_five_items(self):
        for key, label in SKILL_AREAS:
            held = [r for r in self.card.questions if r.domain == label]
            self.assertEqual(len(held), ITEMS_PER_AREA)


COMPETENCY = [
    "Not at All Competent (1)", "Somewhat Competent (2)", "Moderately Competent (3)",
    "Very Competent (4)", "Highly Competent (5)",
]
# What the live assessment carries instead: the editor's default.
DEFAULT_SCALE = ["0 - Never", "1 - Rarely", "2 - Sometimes", "3 - Often"]


def caregiver_questions(options=None, self_report=30, observation=20):
    """Thirty parent-report items followed by twenty observation items."""
    built = []
    order = 0
    for domain, count in (("self-report", self_report), ("clinician-observation", observation)):
        for _ in range(count):
            order += 1
            built.append(
                AssessmentQuestion(
                    identifier=f"c{order}", order=order, text=f"item {order}",
                    response_type=AssessmentQuestion.ResponseType.LIKERT,
                    config={"options": list(options or COMPETENCY)}, domain=domain,
                )
            )
    return built


class AbaCaregiverSkillsTests(SimpleTestCase):
    def setUp(self):
        self.card = aba_caregiver_skills(caregiver_questions())

    def answers(self, index=0, observation_index=None):
        payload = {}
        for rule in self.card.questions:
            if rule.domain == "clinician-observation" and observation_index is not None:
                payload[rule.identifier] = COMPETENCY[observation_index]
            else:
                payload[rule.identifier] = COMPETENCY[index]
        return payload

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_it_reports_both_halves_and_a_total(self):
        self.assertEqual([s.id for s in self.card.scores],
                         ["self_report", "clinician_observation", "total"])

    def test_the_halves_run_the_ranges_the_document_implies(self):
        ranges = achievable_range(self.card)
        self.assertEqual(ranges["self_report"], (30, 150))
        self.assertEqual(ranges["clinician_observation"], (20, 100))

    def test_the_total_runs_fifty_to_two_hundred_and_fifty(self):
        self.assertEqual(achievable_range(self.card)["total"], (50, 250))

    def test_the_top_band_is_now_reachable(self):
        """The bug. On the live four-point scale the total stops at 150, so
        "Strong Competency" at 200-250 could never be reported."""
        result = score_assessment(self.card, self.answers(index=4))
        self.assertEqual(result.score("total").value, 250)
        self.assertEqual(result.score("total").band_label, "Strong Competency")

    def test_the_bottom_band_still_reads_as_limited(self):
        result = score_assessment(self.card, self.answers(index=0))
        self.assertEqual(result.score("total").value, 50)
        self.assertEqual(result.score("total").band_label, "Limited Competency")

    def test_a_gap_between_the_parent_and_the_clinician_is_visible(self):
        """Why both halves are reported.

        A parent rating themselves highly while the clinician observes little is
        the finding, and a single total averages it away.
        """
        result = score_assessment(self.card, self.answers(index=4, observation_index=0))
        self.assertEqual(result.score("self_report").value, 150)
        self.assertEqual(result.score("clinician_observation").value, 20)

    def test_two_people_with_the_same_total_can_look_different(self):
        flat = score_assessment(self.card, self.answers(index=2))
        split = score_assessment(self.card, self.answers(index=4, observation_index=0))
        self.assertNotEqual(flat.score("self_report").value, split.score("self_report").value)

    def test_it_refuses_the_scale_the_live_assessment_carries(self):
        with self.assertRaises(CardError) as caught:
            aba_caregiver_skills(caregiver_questions(DEFAULT_SCALE))
        self.assertIn("1-5", str(caught.exception))

    def test_it_refuses_a_different_number_of_items(self):
        with self.assertRaises(CardError):
            aba_caregiver_skills(caregiver_questions(self_report=25))

    def test_it_refuses_a_split_that_is_not_thirty_and_twenty(self):
        with self.assertRaises(CardError):
            aba_caregiver_skills(caregiver_questions(self_report=25, observation=25))

    def test_the_notice_explains_why_both_halves_are_shown(self):
        self.assertIn("separately", self.card.standing_notice.lower())
