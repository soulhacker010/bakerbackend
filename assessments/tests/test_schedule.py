from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from clients.models import Client
from assessments.email_invites import EmailInviteError
from assessments.models import Assessment
from assessments.respondent_links import RespondentLinkError


class RespondentLinkScheduleViewTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(
            email="clinician@example.com",
            password="test-pass-123",
            first_name="Taylor",
        )
        self.client.force_authenticate(self.user)

        self.assessment = Assessment.objects.create(
            title="Mood Index",
            slug="mood-index",
            status=Assessment.Status.PUBLISHED,
            created_by=self.user,
        )

        self.client_record = Client.objects.create(
            owner=self.user,
            first_name="Jordan",
            email="jordan@example.com",
            slug="jordan-d",
        )

        self.url = reverse("assessments:respondent-link-schedule")

    def _valid_payload(self, **overrides):
        start_date = (timezone.now().date() + timedelta(days=1)).isoformat()
        payload = {
            "assessments": [self.assessment.slug],
            "clientSlug": self.client_record.slug,
            "shareResults": True,
            "email": {
                "subject": "Upcoming check-in",
                "message": "Please complete your assessment.",
                "includeConsent": True,
            },
            "schedule": {
                "startDate": start_date,
                "frequency": "week",
                "cycles": 3,
            },
        }
        payload.update(overrides)
        return payload

    @patch("assessments.views.send_assessment_invite_email")
    @patch("assessments.views.issue_link_token", autospec=True)
    def test_creates_runs_and_returns_schedule_details(self, mock_issue_token, mock_send_email):
        mock_issue_token.return_value = "token-123"

        response = self.client.post(self.url, data=self._valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()

        self.assertIn("scheduleId", body)
        self.assertEqual(len(body.get("runs", [])), 3)

        self.assertEqual(mock_issue_token.call_count, 3)
        self.assertEqual(mock_send_email.call_count, 3)

    def test_requires_client_slug(self):
        payload = self._valid_payload(clientSlug=None)

        response = self.client.post(self.url, data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("client slug", response.json().get("detail", ""))

    def test_validates_schedule_start_date_format(self):
        payload = self._valid_payload()
        payload["schedule"]["startDate"] = "20-01-2025"

        response = self.client.post(self.url, data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("format", response.json().get("detail", ""))

    @patch("assessments.views.send_assessment_invite_email")
    @patch("assessments.views.issue_link_token", side_effect=RespondentLinkError("failed"))
    def test_handles_token_generation_errors(self, mock_issue_token, mock_send_email):
        response = self.client.post(self.url, data=self._valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("failed", response.json().get("detail", ""))
        mock_send_email.assert_not_called()

    @patch("assessments.views.send_assessment_invite_email", side_effect=EmailInviteError("email failure"))
    def test_handles_email_failures(self, mock_send_email):
        response = self.client.post(self.url, data=self._valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn("email failure", response.json().get("detail", ""))

    def test_requires_authenticated_user(self):
        self.client.logout()

        response = self.client.post(self.url, data=self._valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
