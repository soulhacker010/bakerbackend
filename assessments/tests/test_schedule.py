from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from clients.models import Client
from assessments.models import Assessment, RespondentInviteScheduleRun


class RespondentLinkScheduleViewTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(
            email="clinician@example.com",
            password=get_random_string(length=32),
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
    def test_creates_runs_and_returns_schedule_details(self, mock_send_email):
        response = self.client.post(self.url, data=self._valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()

        self.assertIn("scheduleId", body)
        self.assertEqual(len(body.get("runs", [])), 3)
        # Nothing goes out when the schedule is made; each email is sent on its day.
        mock_send_email.assert_not_called()
        self.assertEqual(RespondentInviteScheduleRun.objects.filter(token="", status="scheduled").count(), 3)

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

    def test_refuses_an_unpublished_assessment_up_front(self):
        self.assessment.status = Assessment.Status.DRAFT
        self.assessment.save(update_fields=["status"])

        response = self.client.post(self.url, data=self._valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(RespondentInviteScheduleRun.objects.exists())

    def test_requires_authenticated_user(self):
        self.client.logout()

        response = self.client.post(self.url, data=self._valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
