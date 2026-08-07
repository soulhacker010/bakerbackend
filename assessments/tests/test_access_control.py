"""Access-control regression tests for assessment responses and respondent links.

Each test here would fail if the protection it covers were removed.
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework import status
from rest_framework.test import APITestCase

from assessments.models import (
    Assessment,
    AssessmentQuestion,
    AssessmentResponse,
    RespondentInvite,
)
from assessments.respondent_links import issue_link_token
from clients.models import Client


def _make_clinician(email: str):
    return get_user_model().objects.create_user(
        email=email,
        password=get_random_string(length=32),
        first_name="Test",
        last_name="Clinician",
        is_approved=True,
    )


def _make_assessment(owner, *, slug: str = "mood-index", title: str = "Mood Index") -> Assessment:
    assessment = Assessment.objects.create(
        title=title,
        slug=slug,
        status=Assessment.Status.PUBLISHED,
        created_by=owner,
    )
    AssessmentQuestion.objects.create(
        assessment=assessment,
        identifier="sleep",
        order=1,
        text="How well did you sleep?",
        response_type=AssessmentQuestion.ResponseType.NUMERIC,
        required=True,
    )
    return assessment


ANSWERS = [{"question_identifier": "sleep", "value": 3}]


@override_settings(TURNSTILE_ENABLED=False)
class SameSlugAcrossCliniciansTests(APITestCase):
    """Client slugs are unique per clinician, so two clinicians can share one.

    Slugs are generated from the client's name, so two practitioners each with a
    "John Doe" both end up with ``john-doe``. Nothing may leak or break because
    of that collision.
    """

    def setUp(self):
        super().setUp()
        self.clinician_a = _make_clinician("a@example.com")
        self.clinician_b = _make_clinician("b@example.com")

        self.assessment = _make_assessment(self.clinician_a)

        self.client_a = Client.objects.create(
            owner=self.clinician_a,
            first_name="John",
            last_name="Doe",
            email="john.a@example.com",
            slug="john-doe",
        )
        self.client_b = Client.objects.create(
            owner=self.clinician_b,
            first_name="John",
            last_name="Doe",
            email="john.b@example.com",
            slug="john-doe",
        )

    def test_clinician_can_record_a_response_for_their_own_client(self):
        """Clinician A administering to A's own John Doe must simply work."""
        self.client.force_authenticate(self.clinician_a)

        response = self.client.post(
            reverse("assessments:assessment-response-list"),
            data={
                "assessment_slug": self.assessment.slug,
                "client_slug": "john-doe",
                "responses": ANSWERS,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        stored = AssessmentResponse.objects.get()
        self.assertEqual(stored.client_id, self.client_a.id)

    def test_respondent_submission_is_recorded_against_the_invited_client(self):
        """A's respondent must land on A's John Doe, never B's."""
        token = issue_link_token(
            owner_id=self.clinician_a.id,
            assessments=[self.assessment.slug],
            mode="linked",
            client_slug=self.client_a.slug,
            share_results=False,
        )

        response = self.client.post(
            reverse("assessments:respondent-link-assessment-response"),
            data={
                "token": token,
                "response": {
                    "assessment_slug": self.assessment.slug,
                    "client_slug": "john-doe",
                    "responses": ANSWERS,
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        stored = AssessmentResponse.objects.get()
        self.assertEqual(stored.client_id, self.client_a.id)

    def test_clinician_cannot_record_a_response_against_another_clinicians_client(self):
        """Clinician B's client must be unreachable to clinician A."""
        Client.objects.filter(pk=self.client_a.pk).delete()

        self.client.force_authenticate(self.clinician_a)
        response = self.client.post(
            reverse("assessments:assessment-response-list"),
            data={
                "assessment_slug": self.assessment.slug,
                "client_slug": "john-doe",
                "responses": ANSWERS,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AssessmentResponse.objects.filter(client=self.client_b).exists())

    def test_respondent_cannot_write_onto_another_clinicians_client(self):
        """If the invited client is gone, the answers must not fall through to B's."""
        token = issue_link_token(
            owner_id=self.clinician_a.id,
            assessments=[self.assessment.slug],
            mode="linked",
            client_slug=self.client_a.slug,
            share_results=False,
        )
        Client.objects.filter(pk=self.client_a.pk).delete()

        response = self.client.post(
            reverse("assessments:respondent-link-assessment-response"),
            data={
                "token": token,
                "response": {
                    "assessment_slug": self.assessment.slug,
                    "client_slug": "john-doe",
                    "responses": ANSWERS,
                },
            },
            format="json",
        )

        self.assertIn(
            response.status_code,
            {status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN},
        )
        self.assertFalse(AssessmentResponse.objects.filter(client=self.client_b).exists())


@override_settings(TURNSTILE_ENABLED=False)
class CrossClinicianResponseVisibilityTests(APITestCase):
    """Clinician A cannot list or retrieve clinician B's assessment responses."""

    def setUp(self):
        super().setUp()
        self.clinician_a = _make_clinician("a@example.com")
        self.clinician_b = _make_clinician("b@example.com")

        self.assessment = _make_assessment(self.clinician_b)
        self.client_b = Client.objects.create(
            owner=self.clinician_b,
            first_name="Bianca",
            last_name="Bell",
            email="bianca@example.com",
            slug="bianca-bell",
        )
        self.response_b = AssessmentResponse.objects.create(
            assessment=self.assessment,
            client=self.client_b,
            submitted_by=self.clinician_b,
            responses={"sleep": 3},
        )

    def test_list_excludes_another_clinicians_responses(self):
        self.client.force_authenticate(self.clinician_a)

        response = self.client.get(reverse("assessments:assessment-response-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), [])

    def test_retrieve_of_another_clinicians_response_is_not_found(self):
        self.client.force_authenticate(self.clinician_a)

        response = self.client.get(
            reverse("assessments:assessment-response-detail", args=[self.response_b.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_filtering_by_another_clinicians_client_returns_nothing(self):
        self.client.force_authenticate(self.clinician_a)

        response = self.client.get(
            reverse("assessments:assessment-response-list"),
            data={"client": self.client_b.slug},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), [])


@override_settings(TURNSTILE_ENABLED=False)
class RespondentLinkGuardTests(APITestCase):
    """The public respondent link must stay inside the bounds of its invitation."""

    def setUp(self):
        super().setUp()
        self.clinician = _make_clinician("clinician@example.com")

        self.invited_assessment = _make_assessment(self.clinician)
        self.other_assessment = _make_assessment(
            self.clinician, slug="anxiety-index", title="Anxiety Index"
        )

        self.invited_client = Client.objects.create(
            owner=self.clinician,
            first_name="Jordan",
            last_name="Doe",
            email="jordan@example.com",
            slug="jordan-doe",
        )
        self.other_client = Client.objects.create(
            owner=self.clinician,
            first_name="Riley",
            last_name="Stone",
            email="riley@example.com",
            slug="riley-stone",
        )

        self.token = issue_link_token(
            owner_id=self.clinician.id,
            assessments=[self.invited_assessment.slug],
            mode="linked",
            client_slug=self.invited_client.slug,
            share_results=False,
        )

    def _submit(self, *, token=None, assessment_slug=None, client_slug=None):
        return self.client.post(
            reverse("assessments:respondent-link-assessment-response"),
            data={
                "token": token or self.token,
                "response": {
                    "assessment_slug": assessment_slug or self.invited_assessment.slug,
                    "client_slug": client_slug or self.invited_client.slug,
                    "responses": ANSWERS,
                },
            },
            format="json",
        )

    def test_token_cannot_submit_for_a_different_client(self):
        response = self._submit(client_slug=self.other_client.slug)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(AssessmentResponse.objects.exists())

    def test_token_cannot_submit_an_assessment_outside_the_invitation(self):
        response = self._submit(assessment_slug=self.other_assessment.slug)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(AssessmentResponse.objects.exists())

    def test_token_cannot_load_an_assessment_outside_the_invitation(self):
        response = self.client.post(
            reverse("assessments:respondent-link-assessment"),
            data={"token": self.token, "assessment": self.other_assessment.slug},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_link_cannot_be_reused_once_it_reaches_max_uses(self):
        first = self._submit()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self._submit()

        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AssessmentResponse.objects.count(), 1)

    def test_expired_link_is_rejected(self):
        RespondentInvite.objects.filter(token=self.token).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        response = self._submit()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AssessmentResponse.objects.exists())

    def test_tampered_token_is_rejected(self):
        tampered = self.token[:-1] + ("A" if self.token[-1] != "A" else "B")

        response = self._submit(token=tampered)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AssessmentResponse.objects.exists())

    def test_unknown_token_is_rejected(self):
        response = self._submit(token="not-a-real-token")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AssessmentResponse.objects.exists())
