"""The Return-to-Play Readiness Screener, and the four items that ran backwards.

The document says "Questions 9-22 use a 0-4 scale" where "4 = Most favorable".
The first four items of the pain domain are written the other way round: question
9 runs from "0 - None" to "4 - Severe and difficult to function with". Scored as
written, the athlete in the most pain scores the highest readiness.

The practice was asked which way to fix it and replied on 16 October 2026: "Can
these four items be reverse scored? Or is it better to change the responses?"
Reversed, for the reasons in the card's docstring.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, INSUFFICIENT_DATA, OK, score_assessment
from assessments.scoring.performance import RTP_DOMAINS, return_to_play
from assessments.scoring.validation import ERROR, achievable_range, validate_card

NA = "N/A - Not yet attempted / unable to assess"

# Question 9's own options, worst last. This is the shape of the problem.
PAIN = ["0 - None", "1 - Mild and easy to ignore", "2 - Noticeable but manageable",
        "3 - Significant and distracting", "4 - Severe and difficult to function with"]

# A mood item, worst first, which is the way round the document intends.
MOOD = ["0 - Nearly every day", "1 - Most days", "2 - Several days",
        "3 - A few days", "4 - Not at all"]

CONFIDENCE = [str(n) for n in range(11)]


def questions(pain=5, mood=5, fear=4, confidence=5, sport=5, globals_=2, intake=True):
    """The screener as stored: intake questions first, then five tagged domains."""
    built, order = [], 0

    def add(identifier, text, options, domain, response_type):
        nonlocal order
        order += 1
        built.append(AssessmentQuestion(
            identifier=identifier, order=order, text=text,
            response_type=response_type,
            config={"options": list(options)} if options else {},
            domain=domain,
        ))

    if intake:
        # Free text, carrying no numbers, so nothing here can reach a score.
        for name in ("Sport", "Position", "Injury or illness"):
            add(f"intake-{name.lower()[:6]}", name, [], "intake",
                AssessmentQuestion.ResponseType.FREE_TEXT)

    for key, count, options in (
        ("pain", pain, PAIN),
        ("mood", mood, MOOD),
        ("fear", fear, MOOD),
        ("confidence", confidence, CONFIDENCE),
        ("sport_readiness", sport, CONFIDENCE),
    ):
        for i in range(count):
            add(f"{key}-{i + 1}", f"{key} item {i + 1}", options, key,
                AssessmentQuestion.ResponseType.SINGLE_CHOICE)

    for i in range(globals_):
        add(f"global-{i + 1}", f"overall rating {i + 1}", CONFIDENCE, "global",
            AssessmentQuestion.ResponseType.SINGLE_CHOICE)

    return built


class ReturnToPlayTests(SimpleTestCase):
    def setUp(self):
        self.card = return_to_play(questions())

    def answers(self, pain=0, mood=4, fear=4, confidence=10, sport=10,
                predictability=None, **overrides):
        """A whole submission. Defaults are a healthy athlete.

        ``pain`` sets the first four pain items, which run from 0 (none) to 4
        (severe). The fifth asks how predictable the symptoms feel and runs the
        other way, so it moves opposite to the rest: by default it mirrors
        ``pain`` so that "no pain" also means "fully in control".
        """
        payload = {}
        for key, value, scale in (
            ("pain", pain, PAIN), ("mood", mood, MOOD), ("fear", fear, MOOD),
            ("confidence", confidence, CONFIDENCE),
            ("sport_readiness", sport, CONFIDENCE),
        ):
            count = next(c for k, _, c, _ in RTP_DOMAINS if k == key)
            for i in range(count):
                payload[f"{key}-{i + 1}"] = scale[value]

        payload["pain-5"] = PAIN[4 - pain if predictability is None else predictability]
        payload["global-1"] = CONFIDENCE[10]
        payload["global-2"] = CONFIDENCE[10]
        payload.update(overrides)
        return payload

    # ----------------------------------------------------------------- shape

    def test_card_is_sound(self):
        self.assertEqual([p for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_every_domain_is_reported_out_of_twenty(self):
        ranges = achievable_range(self.card)
        for key, _, _, _ in RTP_DOMAINS:
            self.assertEqual(ranges[key], (0, 20), key)

    def test_the_overall_score_runs_zero_to_one_hundred(self):
        self.assertEqual(achievable_range(self.card)["overall"], (0, 100))

    def test_intake_questions_never_reach_a_score(self):
        """Sport, position and the injury description are free text. Before the
        engine, a scorer that read numbers out of text would have added the year
        in "tore my ACL in 2024" to a clinical total."""
        identifiers = [r.identifier for r in self.card.questions]
        self.assertFalse([i for i in identifiers if i.startswith("intake-")])

    # ------------------------------------------------- the reversed four

    def test_an_athlete_in_severe_pain_does_not_read_as_ready(self):
        """The bug, stated as the submission that exposes it.

        Every pain item answered at its worst, everything else perfect.
        """
        result = score_assessment(self.card, self.answers(pain=4))
        self.assertEqual(result.score("pain").value, 0.0)
        self.assertLess(result.score("overall").value, 100)

    def test_no_pain_scores_the_pain_domain_full_marks(self):
        result = score_assessment(self.card, self.answers(pain=0))
        self.assertEqual(result.score("pain").value, 20.0)

    def test_the_first_four_pain_items_are_reversed_and_the_fifth_is_not(self):
        """Item 13 asks how predictable the symptoms feel, where a high answer
        really is the favourable one. Reversing it too would be the same bug
        pointing the other way."""
        reversed_flags = [r.reverse for r in self.card.questions if r.domain == "pain"]
        self.assertEqual(reversed_flags, [True, True, True, True, False])

    def test_nothing_outside_the_pain_domain_is_reversed(self):
        for rule in self.card.questions:
            if rule.domain != "pain":
                self.assertFalse(rule.reverse, rule.identifier)

    def test_worse_pain_always_lowers_the_score(self):
        previous = None
        for level in range(5):
            value = score_assessment(self.card, self.answers(pain=level)).score("pain").value
            if previous is not None:
                self.assertLess(value, previous, "pain level %d" % level)
            previous = value

    def test_the_worst_possible_submission_scores_zero(self):
        result = score_assessment(
            self.card, self.answers(pain=4, mood=0, fear=0, confidence=0, sport=0)
        )
        self.assertEqual(result.score("overall").value, 0)
        self.assertEqual(result.score("overall").band_label, "Significant Reported Barriers")

    def test_the_best_possible_submission_scores_one_hundred(self):
        result = score_assessment(self.card, self.answers())
        self.assertEqual(result.score("overall").value, 100)
        self.assertEqual(result.score("overall").band_label, "Higher Reported Readiness")

    # ------------------------------------------------------------- bands

    def test_each_band_reads_as_the_document_states(self):
        for pain, mood, fear, confidence, sport, expected in (
            (0, 4, 4, 10, 10, "Higher Reported Readiness"),
            (1, 3, 3, 8, 8, "Generally Favorable"),
            (2, 2, 2, 7, 7, "Mixed Readiness"),
            (3, 2, 2, 4, 4, "Reduced Readiness"),
            (4, 1, 1, 1, 1, "Significant Reported Barriers"),
        ):
            result = score_assessment(self.card, self.answers(
                pain=pain, mood=mood, fear=fear, confidence=confidence, sport=sport))
            self.assertEqual(result.score("overall").band_label, expected,
                             "%s -> %s" % (expected, result.score("overall").value))

    def test_no_reachable_overall_score_falls_outside_a_band(self):
        for pain in range(5):
            for confidence in range(11):
                result = score_assessment(
                    self.card, self.answers(pain=pain, confidence=confidence))
                self.assertIsNotNone(
                    result.score("overall").band_label,
                    "score %s returned no interpretation" % result.score("overall").value,
                )

    # --------------------------------------------------------- not applicable

    def test_a_skipped_item_shrinks_the_denominator_instead_of_scoring_zero(self):
        """"Responses marked N/A are not scored as zero. They should be excluded
        from the denominator when calculating the applicable domain score."

        Four confidence items at 10 and one not attempted is still full
        confidence, not eight out of ten.
        """
        result = score_assessment(self.card, self.answers(**{"confidence-5": NA}))
        self.assertEqual(result.score("confidence").value, 20.0)

    def test_counting_a_skipped_item_as_zero_would_have_cost_four_points(self):
        answered = score_assessment(
            self.card, self.answers(**{"confidence-5": CONFIDENCE[0]}))
        skipped = score_assessment(self.card, self.answers(**{"confidence-5": NA}))
        self.assertEqual(answered.score("confidence").value, 16.0)
        self.assertEqual(skipped.score("confidence").value, 20.0)

    def test_a_domain_answered_by_too_few_items_is_not_scored(self):
        payload = self.answers()
        for i in (1, 2, 3):
            payload[f"fear-{i}"] = NA
        result = score_assessment(self.card, payload)
        self.assertEqual(result.score("fear").status, INSUFFICIENT_DATA)
        self.assertIsNone(result.score("fear").value)

    def test_a_domain_that_cannot_be_scored_withholds_the_overall_score(self):
        """Four domains out of five is not a readiness score out of 100."""
        payload = self.answers()
        for i in (1, 2, 3):
            payload[f"fear-{i}"] = NA
        result = score_assessment(self.card, payload)
        self.assertEqual(result.score("overall").status, INSUFFICIENT_DATA)

    def test_half_a_domain_is_still_enough(self):
        payload = self.answers()
        payload["fear-1"] = NA
        payload["fear-2"] = NA
        result = score_assessment(self.card, payload)
        self.assertEqual(result.score("fear").status, OK)
        self.assertEqual(result.score("fear").value, 20.0)

    # -------------------------------------------------------------- flags

    def test_a_domain_below_fifteen_is_flagged_for_review(self):
        result = score_assessment(self.card, self.answers(mood=2))
        self.assertEqual(result.score("mood").value, 10.0)
        self.assertIn("rtp-mood-review", [f.id for f in result.flags])

    def test_a_domain_at_or_below_ten_is_a_significant_concern(self):
        result = score_assessment(self.card, self.answers(mood=2))
        self.assertIn("rtp-mood-concern", [f.id for f in result.flags])

    def test_a_healthy_domain_is_not_flagged(self):
        result = score_assessment(self.card, self.answers())
        self.assertEqual([f.id for f in result.flags], [])

    def test_the_pain_flag_fires_on_pain_the_old_scoring_called_favourable(self):
        """Before the reversal this submission scored 20/20 and flagged nothing."""
        result = score_assessment(self.card, self.answers(pain=4))
        self.assertIn("rtp-pain-concern", [f.id for f in result.flags])

    # ------------------------------------------------- the two overall ratings

    def test_the_athlete_and_clinician_ratings_are_reported_separately(self):
        ids = [s.id for s in self.card.scores]
        self.assertIn("athlete_rating", ids)
        self.assertIn("clinician_rating", ids)

    def test_a_disagreement_between_them_is_visible(self):
        """The finding a single number cannot show: the athlete says ready, the
        clinician does not."""
        result = score_assessment(self.card, self.answers(**{"global-2": CONFIDENCE[2]}))
        self.assertEqual(result.score("athlete_rating").value, 10)
        self.assertEqual(result.score("clinician_rating").value, 2)

    def test_neither_rating_reaches_the_readiness_score(self):
        """The document keeps them apart from it, so a confident athlete cannot
        lift their own readiness score by rating themselves highly."""
        high = score_assessment(self.card, self.answers())
        low = score_assessment(self.card, self.answers(
            **{"global-1": CONFIDENCE[0], "global-2": CONFIDENCE[0]}))
        self.assertEqual(high.score("overall").value, low.score("overall").value)

    # ------------------------------------------------------------ refusals

    def test_it_refuses_a_domain_with_the_wrong_number_of_items(self):
        with self.assertRaises(CardError):
            return_to_play(questions(fear=3))

    def test_the_refusal_names_the_domain(self):
        with self.assertRaises(CardError) as caught:
            return_to_play(questions(pain=4))
        self.assertIn("pain", str(caught.exception))

    def test_it_refuses_a_section_it_does_not_recognise(self):
        wrong = questions()
        wrong[-1].domain = "nutrition"
        with self.assertRaises(CardError) as caught:
            return_to_play(wrong)
        self.assertIn("nutrition", str(caught.exception))

    def test_it_refuses_a_confidence_domain_on_the_wrong_scale(self):
        wrong = questions()
        for question in wrong:
            if question.domain == "confidence":
                question.config = {"options": list(MOOD)}
        with self.assertRaises(CardError):
            return_to_play(wrong)

    def test_it_refuses_one_overall_rating_where_the_document_has_two(self):
        with self.assertRaises(CardError):
            return_to_play(questions(globals_=1))

    def test_the_notice_says_the_cut_offs_are_provisional(self):
        self.assertIn("not validated clinical cut scores", self.card.standing_notice)

    def test_the_notice_says_it_is_not_medical_clearance(self):
        self.assertIn("does not provide medical clearance", self.card.standing_notice)

    def test_the_notice_states_our_own_insufficient_data_rule(self):
        """It is not in the document, so it is said out loud rather than buried."""
        self.assertIn("fewer than half", self.card.standing_notice)
