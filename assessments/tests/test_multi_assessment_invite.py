"""One invitation, several assessments - the way the practice sends them.

Their October 2026 update: "When sending out multiple assessments to clients,
they only receive a link to one assessment. They need to receive and have
access to all."

The link always carried every assessment. What it could not do was remember
which ones were done. A respondent who finished the first, closed the tab and
came back through the email was given the first one again; redoing it spent a
use meant for another assessment, and the last one was then refused as
"already used".
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils.crypto import get_random_string
from rest_framework import status

from bakerapi.test_utils import ThrottledAPITestCase

from assessments.models import Assessment, AssessmentQuestion, AssessmentResponse, RespondentInvite
from clients.models import Client

SLUGS = ("mood-index", "sleep-index", "stress-index")


@override_settings(TURNSTILE_ENABLED=False)
class MultiAssessmentInviteTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.password = get_random_string(length=32)
        self.clinician = get_user_model().objects.create_user(
            email="clinician@example.com", password=self.password,
            first_name="Taylor", last_name="Reed", is_approved=True,
        )
        for slug in SLUGS:
            assessment = Assessment.objects.create(
                title=slug.replace("-", " ").title(), slug=slug,
                status=Assessment.Status.PUBLISHED, created_by=self.clinician,
            )
            AssessmentQuestion.objects.create(
                assessment=assessment, identifier="q1", order=1, text="How are you?",
                response_type=AssessmentQuestion.ResponseType.NUMERIC, required=True,
            )
        self.client_record = Client.objects.create(
            owner=self.clinician, first_name="Jordan", last_name="Doe",
            email="jordan@example.com", slug="jordan-doe",
        )
        self.token = self._issue()

    def _issue(self) -> str:
        login = self.client.post(
            reverse("accounts:login"),
            data={"email": self.clinician.email, "password": self.password},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
        response = self.client.post(
            reverse("assessments:respondent-link-issue"),
            data={"assessments": list(SLUGS), "mode": "linked",
                  "clientSlug": self.client_record.slug},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.client.credentials()
        return response.json()["token"]

    def resolve(self):
        return self.client.post(
            reverse("assessments:respondent-link-resolve"),
            data={"token": self.token}, format="json",
        )

    def submit(self, slug):
        return self.client.post(
            reverse("assessments:respondent-link-assessment-response"),
            data={"token": self.token, "response": {
                "assessment_slug": slug, "client_slug": self.client_record.slug,
                "responses": [{"question_identifier": "q1", "value": 2}],
            }},
            format="json",
        )

    # ----------------------------------------------------------------- tests

    def test_one_link_reaches_every_assessment_in_turn(self):
        for slug in SLUGS:
            self.assertEqual(self.submit(slug).status_code, status.HTTP_201_CREATED, slug)
        self.assertEqual(AssessmentResponse.objects.count(), 3)

    def test_the_link_reports_what_has_already_been_done(self):
        self.submit("mood-index")
        body = self.resolve().json()
        self.assertEqual(body["completedAssessments"], ["mood-index"])

    def test_coming_back_after_closing_the_tab_reaches_the_rest(self):
        """The case that failed. Finish one, leave, come back via the email."""
        self.submit("mood-index")

        reopened = self.resolve()
        self.assertEqual(reopened.status_code, status.HTTP_200_OK)
        self.assertEqual(reopened.json()["completedAssessments"], ["mood-index"])

        self.assertEqual(self.submit("sleep-index").status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.submit("stress-index").status_code, status.HTTP_201_CREATED)

    def test_redoing_one_cannot_spend_the_last_ones_turn(self):
        """Before: the repeat was accepted, used up a turn, and the third
        assessment was then refused with "already been used"."""
        self.submit("mood-index")
        repeat = self.submit("mood-index")
        self.assertEqual(repeat.status_code, status.HTTP_409_CONFLICT)

        self.assertEqual(self.submit("sleep-index").status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.submit("stress-index").status_code, status.HTTP_201_CREATED)
        self.assertEqual(AssessmentResponse.objects.count(), 3)

    def test_a_refused_repeat_stores_nothing(self):
        self.submit("mood-index")
        self.submit("mood-index")
        self.assertEqual(AssessmentResponse.objects.filter(assessment__slug="mood-index").count(), 1)

    def test_the_refusal_says_what_happened_in_plain_words(self):
        self.submit("mood-index")
        self.assertIn("already completed", self.submit("mood-index").json()["detail"])

    def test_a_finished_invitation_thanks_rather_than_blames(self):
        """Read by someone who has just done everything asked of them."""
        for slug in SLUGS:
            self.submit(slug)
        detail = self.resolve().json()["detail"]
        self.assertIn("completed every assessment", detail)
        self.assertNotIn("already been used", detail)

    def test_the_invitation_records_each_assessment_once(self):
        self.submit("mood-index")
        self.submit("mood-index")
        self.submit("sleep-index")
        invite = RespondentInvite.objects.get(token=self.token)
        self.assertEqual(invite.completed_assessments, ["mood-index", "sleep-index"])
        self.assertEqual(invite.uses, 2)
