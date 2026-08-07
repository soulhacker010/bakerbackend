"""End-to-end tests for the flows the product exists to serve.

These are deliberately "happy path": a clinician invites a client, the client
opens the link without logging in, answers the questions, and the clinician sees
the result. If any of these break, the product is broken.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils.crypto import get_random_string
from rest_framework import status
from rest_framework.test import APITestCase

from assessments.models import Assessment, AssessmentQuestion, AssessmentResponse
from clients.models import Client


@override_settings(TURNSTILE_ENABLED=False)
class RespondentEndToEndTests(APITestCase):
    """A clinician sends an assessment; a respondent completes it."""

    def setUp(self):
        super().setUp()
        self.password = get_random_string(length=32)
        self.clinician = get_user_model().objects.create_user(
            email="clinician@example.com",
            password=self.password,
            first_name="Taylor",
            last_name="Reed",
            is_approved=True,
        )

        self.assessment = Assessment.objects.create(
            title="Mood Index",
            slug="mood-index",
            status=Assessment.Status.PUBLISHED,
            created_by=self.clinician,
        )
        AssessmentQuestion.objects.create(
            assessment=self.assessment,
            identifier="sleep",
            order=1,
            text="How well did you sleep?",
            response_type=AssessmentQuestion.ResponseType.NUMERIC,
            required=True,
        )
        AssessmentQuestion.objects.create(
            assessment=self.assessment,
            identifier="mood",
            order=2,
            text="How was your mood?",
            response_type=AssessmentQuestion.ResponseType.NUMERIC,
            required=True,
        )

        self.client_record = Client.objects.create(
            owner=self.clinician,
            first_name="Jordan",
            last_name="Doe",
            email="jordan@example.com",
            slug="jordan-doe",
        )

    def _login(self) -> str:
        response = self.client.post(
            reverse("accounts:login"),
            data={"email": self.clinician.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()["access"]

    def _issue_token(self) -> str:
        access = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = self.client.post(
            reverse("assessments:respondent-link-issue"),
            data={
                "assessments": [self.assessment.slug],
                "mode": "linked",
                "clientSlug": self.client_record.slug,
                "shareResults": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.client.credentials()
        return response.json()["token"]

    def test_clinician_can_log_in_and_issue_a_respondent_link(self):
        token = self._issue_token()
        self.assertTrue(token)

    def test_respondent_can_resolve_the_link_without_logging_in(self):
        token = self._issue_token()

        response = self.client.post(
            reverse("assessments:respondent-link-resolve"),
            data={"token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["mode"], "linked")
        self.assertFalse(body["pendingClient"])
        self.assertEqual([item["slug"] for item in body["assessments"]], [self.assessment.slug])
        self.assertEqual(body["client"]["slug"], self.client_record.slug)

    def test_respondent_can_load_the_invited_assessment(self):
        token = self._issue_token()

        response = self.client.post(
            reverse("assessments:respondent-link-assessment"),
            data={"token": token, "assessment": self.assessment.slug},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["slug"], self.assessment.slug)
        self.assertEqual(len(body["questions"]), 2)

    def test_respondent_can_submit_answers_and_clinician_sees_the_result(self):
        token = self._issue_token()

        submission = self.client.post(
            reverse("assessments:respondent-link-assessment-response"),
            data={
                "token": token,
                "response": {
                    "assessment_slug": self.assessment.slug,
                    "client_slug": self.client_record.slug,
                    "responses": [
                        {"question_identifier": "sleep", "value": 3},
                        {"question_identifier": "mood", "value": 4},
                    ],
                },
            },
            format="json",
        )

        self.assertEqual(submission.status_code, status.HTTP_201_CREATED)

        stored = AssessmentResponse.objects.get()
        self.assertEqual(stored.client_id, self.client_record.id)
        self.assertEqual(stored.assessment_id, self.assessment.id)
        self.assertIsNone(stored.submitted_by_id)
        self.assertEqual(stored.responses, {"sleep": 3, "mood": 4})

        access = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        listing = self.client.get(
            reverse("assessments:assessment-response-list"),
            data={"client": self.client_record.slug},
        )

        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        rows = listing.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["assessment_slug"], self.assessment.slug)
        self.assertEqual(rows[0]["client"]["slug"], self.client_record.slug)

    def test_clinician_can_administer_an_assessment_directly(self):
        """The in-session flow: the clinician records answers themselves."""
        access = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.post(
            reverse("assessments:assessment-response-list"),
            data={
                "assessment_slug": self.assessment.slug,
                "client_slug": self.client_record.slug,
                "responses": [
                    {"question_identifier": "sleep", "value": 2},
                    {"question_identifier": "mood", "value": 5},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        stored = AssessmentResponse.objects.get()
        self.assertEqual(stored.client_id, self.client_record.id)
        self.assertEqual(stored.submitted_by_id, self.clinician.id)
