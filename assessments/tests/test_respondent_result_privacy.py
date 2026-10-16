"""What a respondent's browser is allowed to receive back.

The dashboard already declines to render clinician-only warnings to a respondent.
That was the whole protection, and it is not one: the warnings were still in the
response body, readable by anyone who opened the network tab, on a shared
computer, or in a cached page. On the perinatal screeners the text in question is
a clinical directive about suicide risk, addressed to somebody else.

These tests are about what is sent, not about what is drawn.
"""
from django.test import SimpleTestCase

from assessments.scoring.service import for_respondent

URGENT = (
    "Suicidal ideation was endorsed. The instrument directs an immediate safety "
    "assessment and a safety plan."
)


def response_data(**overrides):
    """The shape the response serializer returns after a submission."""
    data = {
        "id": 7,
        "assessment_slug": "expectant-mothers-mental-health-screener",
        "submitted_at": "2026-09-25T09:00:00Z",
        "highlights": [
            "Monitor with routine prenatal care.",
            URGENT,
        ],
        "score": {
            "version": 2,
            "total": 41,
            "band_label": "High",
            "interpretation": "Urgent referral to a psychiatrist.",
            "scores": [
                {"id": "total", "label": "Total", "status": "ok", "value": 41,
                 "max_possible": 75, "band_label": "High",
                 "interpretation": "Urgent referral to a psychiatrist."},
                {"id": "suicidal", "label": "Suicidal Ideation / History",
                 "status": "ok", "value": 5, "max_possible": 6,
                 "interpretation": "Screen for suicidal ideation. Refer urgently."},
            ],
            "flags": [
                {"id": "suicidal-any", "message": URGENT,
                 "severity": "urgent", "audience": "clinician"},
                {"id": "shared", "message": "Shared with everyone.",
                 "severity": "info", "audience": "both"},
                {"id": "yours", "message": "For the respondent.",
                 "severity": "info", "audience": "patient"},
            ],
        },
    }
    data.update(overrides)
    return data


class RespondentResultPrivacyTests(SimpleTestCase):
    def setUp(self):
        self.sent = for_respondent(response_data())

    def flag_ids(self):
        return [f["id"] for f in self.sent["score"]["flags"]]

    # -- the warnings ------------------------------------------------- #

    def test_a_clinician_only_warning_is_not_sent(self):
        self.assertNotIn("suicidal-any", self.flag_ids())

    def test_a_warning_for_the_respondent_is_sent(self):
        self.assertIn("yours", self.flag_ids())

    def test_a_warning_for_both_is_sent(self):
        self.assertIn("shared", self.flag_ids())

    def test_a_warning_with_no_stated_audience_is_treated_as_clinician_only(self):
        # Failing closed matters more here than failing helpfully.
        data = response_data()
        data["score"]["flags"] = [{"id": "untagged", "message": "?", "severity": "urgent"}]
        self.assertEqual(for_respondent(data)["score"]["flags"], [])

    # -- the text itself ---------------------------------------------- #

    def test_the_clinical_directive_appears_nowhere_in_what_is_sent(self):
        """The test that matters.

        Not "is the flag filtered" but "is the sentence gone", because it also
        used to travel in highlights.
        """
        self.assertNotIn(URGENT, str(self.sent))

    def test_highlights_are_not_sent_at_all(self):
        # A clinician's summary: every warning verbatim, plus section
        # interpretations written as instructions to a clinician.
        self.assertNotIn("highlights", self.sent)

    # -- the range descriptions ---------------------------------------- #

    def test_a_range_description_written_to_a_clinician_is_not_sent(self):
        """The second half of the same bug.

        "Urgent referral to a psychiatrist. Screen for suicidal ideation." is an
        instruction to a therapist about a patient. It was reaching the patient,
        alone, with a Finish button underneath, purely because it sits in the
        range description rather than in a warning.
        """
        self.assertNotIn("psychiatrist", str(self.sent))
        self.assertNotIn("Screen for suicidal ideation", str(self.sent))

    def test_no_section_carries_an_interpretation(self):
        for score in self.sent["score"]["scores"]:
            self.assertNotIn("interpretation", score)

    def test_the_headline_carries_no_interpretation_either(self):
        self.assertNotIn("interpretation", self.sent["score"])

    # -- what the respondent keeps ------------------------------------ #

    def test_the_respondent_still_receives_their_scores(self):
        self.assertEqual(len(self.sent["score"]["scores"]), 2)

    def test_the_respondent_still_receives_their_range(self):
        # The label is their result. What it means clinically is a conversation.
        self.assertEqual(self.sent["score"]["band_label"], "High")

    def test_the_respondent_still_receives_each_section_score(self):
        suicidal = next(s for s in self.sent["score"]["scores"] if s["id"] == "suicidal")
        self.assertEqual(suicidal["value"], 5)
        self.assertEqual(suicidal["max_possible"], 6)

    def test_the_respondent_still_receives_the_total(self):
        self.assertEqual(self.sent["score"]["total"], 41)

    def test_the_rest_of_the_record_is_untouched(self):
        self.assertEqual(self.sent["id"], 7)
        self.assertEqual(self.sent["assessment_slug"], "expectant-mothers-mental-health-screener")

    # -- shapes that must not crash ------------------------------------ #

    def test_a_response_that_was_never_scored_passes_through(self):
        self.assertIsNone(for_respondent(response_data(score=None))["score"])

    def test_a_result_with_no_warnings_passes_through(self):
        data = response_data()
        del data["score"]["flags"]
        self.assertNotIn("flags", for_respondent(data)["score"])

    def test_a_legacy_result_with_only_a_total_passes_through(self):
        data = response_data(score={"total": 30, "band": "level-2"})
        self.assertEqual(for_respondent(data)["score"]["total"], 30)

    def test_the_original_is_not_modified(self):
        # The clinician's copy is serialised from the same data.
        data = response_data()
        for_respondent(data)
        self.assertEqual(len(data["score"]["flags"]), 3)
        self.assertIn("highlights", data)
        self.assertIn("interpretation", data["score"]["scores"][0])


class CrisisSupportTests(SimpleTestCase):
    """The other half of stripping the clinician's directives out.

    Removing "urgent referral to a psychiatrist" was right - it is addressed to
    somebody else - but on its own it leaves a person holding a number and no
    route anywhere. The practice supplied its own routing on 16 October 2026 and
    it now rides with every respondent-facing result.
    """

    def setUp(self):
        self.sent = for_respondent(response_data())

    def joined(self):
        return " ".join(self.sent["crisis_support"]["lines"])

    def test_the_result_carries_crisis_contacts(self):
        self.assertIn("crisis_support", self.sent)
        self.assertTrue(self.sent["crisis_support"]["lines"])

    def test_the_daytime_number_reaches_the_practice(self):
        self.assertIn("833-937-2724", self.joined())

    def test_emergencies_route_to_911(self):
        self.assertIn("911", self.joined())

    def test_distress_routes_to_the_988_lifeline(self):
        self.assertIn("988", self.joined())

    def test_the_lifeline_is_described_as_always_open(self):
        """A screener finished at 2am is the case this exists for."""
        self.assertIn("24/7", self.joined())

    def test_it_is_addressed_to_the_person_reading_it(self):
        """Not to the clinician. The practice's note to us was written in the
        third person - "they should call 911" - and that is not what a person
        alone with their own result should be reading."""
        self.assertNotIn("they should", self.joined().lower())
        self.assertIn("you", self.joined().lower())

    def test_it_is_sent_whatever_the_score_was(self):
        """Deliberately not conditioned on a threshold. The person who needs it
        is not reliably the one the bands catch."""
        for data in (response_data(score={"version": 2, "total": 0}),
                     response_data(score=None),
                     response_data()):
            self.assertIn("988", " ".join(
                for_respondent(data)["crisis_support"]["lines"]
            ))

    def test_it_survives_the_removals_rather_than_being_stripped_with_them(self):
        self.assertNotIn("highlights", self.sent)
        self.assertIn("crisis_support", self.sent)

    def test_editing_what_was_sent_cannot_change_the_next_respondents_copy(self):
        self.sent["crisis_support"]["lines"].append("made up")
        self.assertNotIn("made up", for_respondent(response_data())["crisis_support"]["lines"])
