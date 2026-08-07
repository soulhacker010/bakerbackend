"""Audit trail tests.

The no-PHI test is the one that protects the compliance record: the trail must
record who touched which record, and nothing about the patient themselves.
"""
from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils.crypto import get_random_string
from rest_framework import status

from bakerapi.test_utils import ThrottledAPITestCase

from assessments.models import Assessment, AssessmentQuestion, AssessmentResponse
from assessments.respondent_links import issue_link_token
from audit.models import AuditLog
from clients.models import Client, ClientGroup

# Distinctive values, so the no-PHI assertion cannot pass by coincidence.
PHI = {
    "first_name": "Zebediah",
    "last_name": "Quartermaine",
    "email": "zebediah.quartermaine@example.org",
    "dob": "1974-03-19",
    "informant1_name": "Persephone Quartermaine",
    "informant1_email": "persephone.quartermaine@example.org",
}


def _make_clinician(email: str = "clinician@example.com"):
    return get_user_model().objects.create_user(
        email=email,
        password=get_random_string(length=32),
        first_name="Test",
        last_name="Clinician",
        is_approved=True,
    )


@override_settings(TURNSTILE_ENABLED=False)
class ClientAuditTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.clinician = _make_clinician()
        self.client.force_authenticate(self.clinician)
        self.record = Client.objects.create(
            owner=self.clinician,
            first_name=PHI["first_name"],
            last_name=PHI["last_name"],
            email=PHI["email"],
            slug="zebediah-quartermaine",
        )
        AuditLog.objects.all().delete()

    def test_viewing_a_client_writes_one_view_entry(self):
        response = self.client.get(reverse("clients:client-detail", args=[self.record.slug]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditLog.Action.VIEW)
        self.assertEqual(entry.resource_type, AuditLog.ResourceType.CLIENT)
        self.assertEqual(entry.resource_id, str(self.record.pk))
        self.assertEqual(entry.user_id, self.clinician.id)
        self.assertEqual(entry.user_email, self.clinician.email)

    def test_creating_a_client_writes_one_create_entry(self):
        response = self.client.post(
            reverse("clients:client-list"),
            data={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditLog.Action.CREATE)
        self.assertEqual(entry.resource_id, str(response.json()["id"]))

    def test_updating_a_client_writes_one_update_entry(self):
        response = self.client.patch(
            reverse("clients:client-detail", args=[self.record.slug]),
            data={"first_name": "Zeb"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditLog.Action.UPDATE)
        self.assertEqual(entry.resource_id, str(self.record.pk))

    def test_deleting_a_client_writes_one_delete_entry(self):
        pk = self.record.pk

        response = self.client.delete(reverse("clients:client-detail", args=[self.record.slug]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditLog.Action.DELETE)
        self.assertEqual(entry.resource_id, str(pk))

    def test_listing_clients_is_not_audited(self):
        self.client.get(reverse("clients:client-list"))

        self.assertEqual(AuditLog.objects.count(), 0)

    def test_a_refused_request_writes_no_entry(self):
        other = _make_clinician("other@example.com")
        self.client.force_authenticate(other)

        response = self.client.get(reverse("clients:client-detail", args=[self.record.slug]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_bulk_import_writes_one_entry_without_identifying_anyone(self):
        response = self.client.post(
            reverse("clients:client-import-clients"),
            data={
                "rows": [
                    {"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"},
                    {"first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com"},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditLog.Action.CREATE)
        self.assertEqual(entry.resource_type, AuditLog.ResourceType.CLIENT)
        self.assertEqual(entry.resource_id, "")

        blob = " ".join(str(value) for value in entry.__dict__.values())
        for term in ("Ada", "Lovelace", "Grace", "Hopper", "ada@example.com", "grace@example.com"):
            self.assertNotIn(term, blob)

    def test_request_still_succeeds_when_the_audit_write_fails(self):
        with patch("audit.services.AuditLog.objects.create", side_effect=RuntimeError("boom")):
            with self.assertLogs("audit.services", level="ERROR") as logs:
                response = self.client.get(
                    reverse("clients:client-detail", args=[self.record.slug])
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["slug"], self.record.slug)
        self.assertEqual(AuditLog.objects.count(), 0)
        self.assertTrue(any("audit log entry" in message for message in logs.output))


@override_settings(TURNSTILE_ENABLED=False)
class ClientGroupAuditTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.clinician = _make_clinician()
        self.client.force_authenticate(self.clinician)
        self.group = ClientGroup.objects.create(
            owner=self.clinician, name="Tuesday cohort", slug="tuesday-cohort"
        )
        AuditLog.objects.all().delete()

    def test_group_lifecycle_is_audited(self):
        self.client.get(reverse("clients:client-group-detail", args=[self.group.slug]))
        self.client.patch(
            reverse("clients:client-group-detail", args=[self.group.slug]),
            data={"name": "Wednesday cohort"},
            format="json",
        )
        self.client.delete(reverse("clients:client-group-detail", args=[self.group.slug]))

        actions = list(AuditLog.objects.order_by("id").values_list("action", flat=True))
        self.assertEqual(
            actions,
            [AuditLog.Action.VIEW, AuditLog.Action.UPDATE, AuditLog.Action.DELETE],
        )
        self.assertEqual(
            set(AuditLog.objects.values_list("resource_type", flat=True)),
            {AuditLog.ResourceType.CLIENT_GROUP},
        )

    def test_creating_a_group_is_audited(self):
        response = self.client.post(
            reverse("clients:client-group-list"),
            data={"name": "Thursday cohort"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditLog.Action.CREATE)
        self.assertEqual(entry.resource_type, AuditLog.ResourceType.CLIENT_GROUP)


@override_settings(TURNSTILE_ENABLED=False)
class AssessmentResponseAuditTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.clinician = _make_clinician()
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
        self.record = Client.objects.create(
            owner=self.clinician,
            first_name=PHI["first_name"],
            last_name=PHI["last_name"],
            email=PHI["email"],
            dob=PHI["dob"],
            informant1_name=PHI["informant1_name"],
            informant1_email=PHI["informant1_email"],
            slug="zebediah-quartermaine",
        )
        self.response_record = AssessmentResponse.objects.create(
            assessment=self.assessment,
            client=self.record,
            submitted_by=self.clinician,
            responses={"sleep": 3},
        )
        AuditLog.objects.all().delete()

    def test_viewing_a_response_is_audited(self):
        self.client.force_authenticate(self.clinician)

        response = self.client.get(
            reverse("assessments:assessment-response-detail", args=[self.response_record.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditLog.Action.VIEW)
        self.assertEqual(entry.resource_type, AuditLog.ResourceType.ASSESSMENT_RESPONSE)
        self.assertEqual(entry.resource_id, str(self.response_record.pk))

    def test_deleting_a_response_is_audited(self):
        self.client.force_authenticate(self.clinician)
        pk = self.response_record.pk

        response = self.client.delete(
            reverse("assessments:assessment-response-detail", args=[pk])
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditLog.Action.DELETE)
        self.assertEqual(entry.resource_id, str(pk))

    def test_respondent_submission_is_audited_with_no_user(self):
        token = issue_link_token(
            owner_id=self.clinician.id,
            assessments=[self.assessment.slug],
            mode="linked",
            client_slug=self.record.slug,
            share_results=False,
        )

        response = self.client.post(
            reverse("assessments:respondent-link-assessment-response"),
            data={
                "token": token,
                "response": {
                    "assessment_slug": self.assessment.slug,
                    "client_slug": self.record.slug,
                    "responses": [{"question_identifier": "sleep", "value": 3}],
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditLog.Action.SUBMIT)
        self.assertEqual(entry.resource_type, AuditLog.ResourceType.ASSESSMENT_RESPONSE)
        self.assertIsNone(entry.user_id)
        self.assertEqual(entry.user_email, "")
        self.assertEqual(entry.resource_id, str(response.json()["id"]))


@override_settings(TURNSTILE_ENABLED=False)
class AuditLogContainsNoPatientDataTests(ThrottledAPITestCase):
    """The trail records identifiers. It must never record the patient."""

    def setUp(self):
        super().setUp()
        self.clinician = _make_clinician()
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
            response_type=AssessmentQuestion.ResponseType.FREE_TEXT,
            required=True,
        )

    def _exercise_every_audited_path(self):
        self.client.force_authenticate(self.clinician)

        created = self.client.post(
            reverse("clients:client-list"),
            data={
                "first_name": PHI["first_name"],
                "last_name": PHI["last_name"],
                "email": PHI["email"],
                "dob": PHI["dob"],
                "gender": "diverse",
                "informant1_name": PHI["informant1_name"],
                "informant1_email": PHI["informant1_email"],
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        slug = created.json()["slug"]
        record = Client.objects.get(pk=created.json()["id"])

        self.client.get(reverse("clients:client-detail", args=[slug]))
        self.client.patch(
            reverse("clients:client-detail", args=[slug]),
            data={"last_name": PHI["last_name"]},
            format="json",
        )

        token = issue_link_token(
            owner_id=self.clinician.id,
            assessments=[self.assessment.slug],
            mode="linked",
            client_slug=record.slug,
            share_results=False,
        )
        self.client.force_authenticate(None)
        submitted = self.client.post(
            reverse("assessments:respondent-link-assessment-response"),
            data={
                "token": token,
                "response": {
                    "assessment_slug": self.assessment.slug,
                    "client_slug": record.slug,
                    "responses": [
                        {"question_identifier": "sleep", "value": "Badly, I kept waking at 3am"}
                    ],
                },
            },
            format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.clinician)
        self.client.get(
            reverse("assessments:assessment-response-detail", args=[submitted.json()["id"]])
        )
        self.client.delete(
            reverse("assessments:assessment-response-detail", args=[submitted.json()["id"]])
        )
        self.client.delete(reverse("clients:client-detail", args=[slug]))

        return slug

    def test_no_audit_entry_contains_patient_data(self):
        slug = self._exercise_every_audited_path()

        self.assertGreaterEqual(AuditLog.objects.count(), 6)

        forbidden = [
            PHI["first_name"],
            PHI["last_name"],
            PHI["email"],
            PHI["dob"],
            PHI["informant1_name"],
            PHI["informant1_email"],
            "diverse",
            "Badly, I kept waking at 3am",
            slug,
        ]

        for entry in AuditLog.objects.all():
            blob = " ".join(str(value) for value in entry.__dict__.values())
            for term in forbidden:
                with self.subTest(entry=entry.pk, term=term):
                    self.assertNotIn(term.lower(), blob.lower())

    def test_every_entry_records_an_action_a_resource_and_a_time(self):
        self._exercise_every_audited_path()

        for entry in AuditLog.objects.all():
            with self.subTest(entry=entry.pk):
                self.assertIn(entry.action, AuditLog.Action.values)
                self.assertIn(entry.resource_type, AuditLog.ResourceType.values)
                self.assertIsNotNone(entry.created_at)

    def test_resource_id_is_always_numeric_or_blank(self):
        """A slug would leak the patient's name, so identifiers stay numeric."""
        self._exercise_every_audited_path()

        for entry in AuditLog.objects.all():
            with self.subTest(entry=entry.pk):
                self.assertTrue(entry.resource_id == "" or entry.resource_id.isdigit())


class AuditLogWriteProtectionTests(ThrottledAPITestCase):
    """No API route may create, edit or delete an audit entry."""

    def test_no_audit_routes_are_exposed(self):
        from django.urls import NoReverseMatch, reverse as django_reverse

        for name in ("audit:auditlog-list", "audit:audit-log-list", "audit:list"):
            with self.subTest(name=name):
                with self.assertRaises(NoReverseMatch):
                    django_reverse(name)

    def test_entries_are_only_written_through_the_service(self):
        clinician = _make_clinician()
        self.client.force_authenticate(clinician)

        for path in ("/api/audit/", "/api/audit-logs/", "/api/auditlog/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(
                    self.client.post(path, data={}, format="json").status_code,
                    status.HTTP_404_NOT_FOUND,
                )
