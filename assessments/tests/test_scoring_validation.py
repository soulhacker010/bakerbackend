"""Card validation, checked against the assessments that are live right now.

Several of the cards below are faithful reproductions of what is in the database
today, bands and all. Each one currently returns a score with no interpretation
attached for part of its range, and every one of them must be refused.
"""
from django.test import SimpleTestCase

from assessments.scoring import (
    Band,
    CardError,
    QuestionRule,
    ScoreRule,
    ScoringCard,
    Transform,
)
from assessments.scoring.validation import (
    ERROR,
    WARNING,
    achievable_range,
    assert_valid,
    validate_card,
)


def band_card(questions, bands, **score_kwargs):
    return ScoringCard(
        questions=questions,
        scores=[ScoreRule(id="total", label="Total", domain="d", bands=bands, **score_kwargs)],
    )


def items(count, scale_max, scale_min=0.0):
    return [
        QuestionRule(identifier=f"q{i}", domain="d", scale_min=scale_min, scale_max=scale_max)
        for i in range(1, count + 1)
    ]


class LiveExecutiveFunctioningTests(SimpleTestCase):
    """30 items on 0-3, so scores run 0-90. The live bands stop at 36."""

    def card(self):
        return band_card(items(30, 3), [
            Band("band-1", "Minimal Concerns", 0, 10, ""),
            Band("band-2", "Significant Impairment (WM, CF, PO)", 18, 24, ""),
            Band("band-3", "Significant Impairment (IC, ER)", 25, 36, ""),
        ])

    def test_range_is_zero_to_ninety(self):
        self.assertEqual(achievable_range(self.card())["total"], (0, 90))

    def test_the_gap_between_eleven_and_seventeen_is_reported(self):
        messages = [p.message for p in validate_card(self.card()) if p.severity == ERROR]
        self.assertTrue(
            any("nothing covers 10 to 18" in m for m in messages),
            messages,
        )

    def test_the_fifty_four_points_above_the_top_band_are_reported(self):
        messages = [p.message for p in validate_card(self.card()) if p.severity == ERROR]
        self.assertTrue(
            any("54 points return no interpretation" in m for m in messages),
            messages,
        )

    def test_this_card_cannot_be_saved(self):
        with self.assertRaises(CardError):
            assert_valid(self.card())


class LiveSeverityScaleTests(SimpleTestCase):
    """30 items on 0-4, so scores run 0-120. The live bands stop at 24.

    The assessment's own note says scores are summed per domain with a maximum of
    24, but the stored configuration sums all 30 questions into one total, so
    nearly every real submission lands above every band.
    """

    def card(self):
        return band_card(items(30, 4), [
            Band("band-1", "Minimal Concerns", 0, 5, ""),
            Band("band-2", "Moderate Disruption", 6, 16, ""),
            Band("band-3", "Significant Impairment", 17, 24, ""),
        ])

    def test_ninety_six_points_are_uncovered(self):
        problems = [p for p in validate_card(self.card()) if p.severity == ERROR]
        self.assertTrue(any("96 points return no interpretation" in p.message for p in problems))

    def test_no_gaps_are_reported_between_adjacent_whole_number_bands(self):
        # 5 then 6, and 16 then 17, sit flush on a whole-number scale.
        problems = validate_card(self.card())
        self.assertFalse(any("nothing covers" in p.message for p in problems))


class LiveAbaParentTrainingTests(SimpleTestCase):
    """50 items on 1-5, so scores run 50-250, and two bands overlap at 100."""

    def card(self):
        return band_card(items(50, 5, scale_min=1), [
            Band("band-1", "Level 1", 0, 100, ""),
            Band("band-2", "Level 2", 100, 149, ""),
            Band("band-3", "Level 3", 150, 199, ""),
            Band("band-4", "Level 4", 200, 250, ""),
        ])

    def test_minimum_is_fifty_not_zero(self):
        self.assertEqual(achievable_range(self.card())["total"], (50, 250))

    def test_the_overlap_at_one_hundred_is_an_error(self):
        problems = [p for p in validate_card(self.card()) if p.severity == ERROR]
        self.assertTrue(any("overlap at 100" in p.message for p in problems))

    def test_an_unreachable_bottom_band_is_only_a_warning(self):
        problems = [p for p in validate_card(self.card()) if p.severity == WARNING]
        self.assertTrue(any("can never be reached" in p.message for p in problems))


class FootHealthTransformTests(SimpleTestCase):
    """The conversion is what makes the 0-100 bands correct."""

    BANDS = [
        Band("mild", "Mild or none", 0, 24, ""),
        Band("moderate", "Moderate", 25, 50, ""),
        Band("significant", "Significant", 51, 100, ""),
    ]

    def test_with_the_conversion_the_bands_fit_exactly(self):
        card = band_card(
            items(15, 4), self.BANDS,
            transform=Transform(kind="linear", multiply=5, divide=3),
        )
        self.assertEqual(achievable_range(card)["total"], (0, 100))
        self.assertEqual(validate_card(card), [])

    def test_without_the_conversion_forty_points_are_unreachable(self):
        # This is the live state: the raw sum stops at 60 while the bands run to 100.
        card = band_card(items(15, 4), self.BANDS)
        self.assertEqual(achievable_range(card)["total"], (0, 60))
        problems = validate_card(card)
        self.assertTrue(any("can never be reached" in p.message for p in problems))


class PostpartumHalfPointTests(SimpleTestCase):
    """Weighted items land on half points, so whole-number bands leave holes."""

    def card(self):
        heavy = {"q2", "q4", "q6"}
        questions = [
            QuestionRule(
                identifier=f"q{i}", domain="d", scale_max=3,
                weight=1.5 if f"q{i}" in heavy else 1.0,
            )
            for i in range(1, 11)
        ]
        return ScoringCard(questions=questions, scores=[ScoreRule(
            id="total", label="Depression", domain="d", granularity=0.5,
            bands=[
                Band("minimal", "Minimal", 0, 8, ""),
                Band("mild", "Mild", 9, 17, ""),
                Band("moderate", "Moderate", 18, 26, ""),
                Band("severe", "Severe", 27, 34.5, ""),
            ],
        )])

    def test_range_reaches_the_documented_thirty_four_point_five(self):
        self.assertEqual(achievable_range(self.card())["total"], (0, 34.5))

    def test_a_score_of_eight_point_five_matches_no_band(self):
        # 1.5 from a weighted item plus 7 from unweighted ones is reachable, and
        # the bands jump straight from 8 to 9.
        problems = [p for p in validate_card(self.card()) if p.severity == ERROR]
        self.assertTrue(
            any("nothing covers 8 to 9" in p.message for p in problems),
            [p.message for p in problems],
        )


class UncoveredBottomTests(SimpleTestCase):
    """Bands that start above the lowest reachable score strand the bottom.

    Easy to write by accident on a 1-5 scale, where the floor is the item count
    rather than zero, and easy to miss because only the least affected
    respondents land there.
    """

    def card(self):
        # 10 items on 1-5, so scores run 10-50. Bands begin at 20.
        return band_card(items(10, 5, scale_min=1), [
            Band("mid", "Moderate", 20, 35, ""),
            Band("high", "High", 36, 50, ""),
        ])

    def test_range_starts_at_ten(self):
        self.assertEqual(achievable_range(self.card())["total"], (10, 50))

    def test_the_uncovered_bottom_is_an_error(self):
        problems = [p for p in validate_card(self.card()) if p.severity == ERROR]
        self.assertTrue(
            any("down to 10" in p.message and "starts at 20" in p.message
                for p in problems),
            [p.message for p in problems],
        )

    def test_this_card_cannot_be_saved(self):
        with self.assertRaises(CardError):
            assert_valid(self.card())


class HealthyCardTests(SimpleTestCase):
    def test_a_card_whose_bands_cover_the_range_passes_cleanly(self):
        card = band_card(items(20, 3), [
            Band("level-1", "Level 1", 0, 15, ""),
            Band("level-2", "Level 2", 16, 30, ""),
            Band("level-3", "Level 3", 31, 45, ""),
            Band("level-4", "Level 4", 46, 60, ""),
        ])
        self.assertEqual(validate_card(card), [])
        assert_valid(card)  # must not raise

    def test_a_score_with_no_bands_is_left_alone(self):
        card = ScoringCard(
            questions=items(5, 3),
            scores=[ScoreRule(id="total", label="Raw", domain="d")],
        )
        self.assertEqual(validate_card(card), [])

    def test_warnings_alone_do_not_block_saving(self):
        card = band_card(items(10, 3), [
            Band("all", "All", 0, 40, ""),   # reaches past the maximum of 30
        ])
        self.assertTrue(validate_card(card))
        assert_valid(card)  # warning only, so it saves


class DerivedScoreRangeTests(SimpleTestCase):
    def test_a_total_built_from_domains_adds_their_ranges(self):
        questions = [
            QuestionRule(identifier=f"a{i}", domain="a", scale_max=3) for i in range(1, 9)
        ] + [
            QuestionRule(identifier=f"b{i}", domain="b", scale_max=3) for i in range(1, 9)
        ]
        card = ScoringCard(questions=questions, scores=[
            ScoreRule(id="a", label="A", domain="a"),
            ScoreRule(id="b", label="B", domain="b"),
            ScoreRule(id="total", label="Total", scores=["a", "b"],
                      bands=[Band("all", "All", 0, 48, "")]),
        ])
        ranges = achievable_range(card)
        self.assertEqual(ranges["a"], (0, 24))
        self.assertEqual(ranges["total"], (0, 48))
        self.assertEqual(validate_card(card), [])

    def test_normalised_domains_report_the_scale_they_are_mapped_onto(self):
        questions = [
            QuestionRule(identifier=f"q{i}", domain="d", scale_max=4, allow_na=True)
            for i in range(1, 6)
        ]
        card = ScoringCard(questions=questions, scores=[
            ScoreRule(id="d", label="D", domain="d",
                      transform=Transform(kind="normalize", to=20)),
        ])
        self.assertEqual(achievable_range(card)["d"], (0, 20))
