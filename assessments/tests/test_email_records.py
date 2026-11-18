"""The practice's record of emailed assessments (Nov 2026).

"When assessments are emailed to a client, the system does not keep a record of
what was sent or when it was sent." Every email is now written down - sent now,
scheduled, or failed - and a deleted schedule calls back what is still queued.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework import status
from rest_framework.test import APITestCase

from assessments.email_invites import EmailInviteError
from assessments.models import Assessment, AssessmentEmailRecord, RespondentInvite
from clients.models import Client


class EmailRecordTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="clinician@example.com",
                                                         password=get_random_string(32))
        self.client.force_authenticate(self.user)
        self.phq = Assessment.objects.create(title="PHQ-9", slug="phq-9", status=Assessment.Status.PUBLISHED,
                                             created_by=self.user)
        self.gad = Assessment.objects.create(title="GAD-7", slug="gad-7", status=Assessment.Status.PUBLISHED,
                                             created_by=self.user)
        self.jordan = Client.objects.create(owner=self.user, first_name="Jordan", last_name="Lee",
                                            email="jordan@example.com", slug="jordan-lee",
                                            informant1_name="Pat Lee", informant1_email="pat@example.com")

    def email_now(self, **extra):
        return self.client.post(reverse("assessments:respondent-link-email"), data={
            "assessments": ["phq-9", "gad-7"], "clientSlug": "jordan-lee",
            "email": {"subject": "Your check-in", "message": "Hi"}, **extra}, format="json")

    def history(self, **params):
        response = self.client.get(reverse("assessments:email-records"), params)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return response.json()["records"]

    @patch("assessments.views.send_assessment_invite_email", return_value="re_1")
    def test_an_email_sent_now_is_recorded_with_what_and_when(self, _send):
        self.assertEqual(self.email_now().status_code, status.HTTP_201_CREATED)
        [record] = self.history(client="jordan-lee")
        self.assertEqual(record["recipient_email"], "jordan@example.com")
        self.assertEqual([a["title"] for a in record["assessments"]], ["PHQ-9", "GAD-7"])
        self.assertEqual(record["subject"], "Your check-in")
        self.assertEqual((record["kind"], record["status"]), ("now", "sent"))
        self.assertIsNotNone(record["send_at"])
        self.assertEqual(record["completed"], [])

    @patch("assessments.views.send_assessment_invite_email", return_value="re_1")
    def test_progress_follows_the_link(self, _send):
        token = self.email_now().json()["token"]
        RespondentInvite.objects.filter(token=token).update(completed_assessments=["phq-9"])
        self.assertEqual(self.history()[0]["completed"], ["phq-9"])

    @patch("assessments.views.send_assessment_invite_email", return_value="re_1")
    def test_an_email_to_an_informant_says_so(self, _send):
        self.email_now(rater="informant1")
        [record] = self.history()
        self.assertEqual((record["recipient_email"], record["recipient_label"]), ("pat@example.com", "Informant - Pat Lee"))

    @patch("assessments.views.send_assessment_invite_email", side_effect=EmailInviteError("provider down"))
    def test_a_failed_send_is_recorded_as_failed(self, _send):
        self.assertEqual(self.email_now().status_code, status.HTTP_502_BAD_GATEWAY)
        [record] = self.history()
        self.assertEqual(record["status"], "failed")
        self.assertIn("provider down", record["error"])

    @patch("assessments.views.send_assessment_invite_email", return_value="re_1")
    def test_a_clinician_sees_only_their_own_emails(self, _send):
        self.email_now()
        other = get_user_model().objects.create_user(email="other@example.com", password=get_random_string(32))
        self.client.force_authenticate(other)
        self.assertEqual(self.history(), [])
        response = self.client.get(reverse("assessments:email-records"), {"client": "jordan-lee"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("assessments.views.send_assessment_invite_email", return_value="re_1")
    def test_deleting_a_client_deletes_their_email_history(self, _send):
        self.email_now()
        self.assertEqual(self.client.delete(reverse("clients:client-detail", args=["jordan-lee"])).status_code,
                         status.HTTP_204_NO_CONTENT)
        self.assertFalse(AssessmentEmailRecord.objects.exists())

    def schedule(self, cycles=2):
        return self.client.post(reverse("assessments:respondent-link-schedule"), data={
            "assessments": ["phq-9"], "clientSlug": "jordan-lee",
            "email": {"subject": "Weekly check-in", "message": "Hi"},
            "schedule": {"startDate": (timezone.now().date() + timedelta(days=1)).isoformat(),
                         "frequency": "week", "cycles": cycles}}, format="json")

    @patch("assessments.views.send_assessment_invite_email", side_effect=["re_a", "re_b"])
    def test_scheduled_emails_are_recorded_for_when_they_go_out(self, _send):
        self.assertEqual(self.schedule().status_code, status.HTTP_201_CREATED)
        records = self.history()
        self.assertEqual([r["status"] for r in records], ["scheduled", "scheduled"])
        self.assertEqual({r["kind"] for r in records}, {"scheduled"})
        # Once its time has passed, a scheduled email reads as sent.
        AssessmentEmailRecord.objects.filter(provider_id="re_a").update(send_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(sorted(r["status"] for r in self.history()), ["scheduled", "sent"])

    @patch("assessments.email_records.cancel_scheduled_email", return_value="")
    @patch("assessments.views.send_assessment_invite_email", side_effect=["re_a", "re_b"])
    def test_deleting_a_schedule_cancels_what_is_still_queued(self, _send, cancel):
        reference = self.schedule().json()["scheduleId"]
        response = self.client.delete(reverse("assessments:respondent-link-schedule-detail", args=[reference]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(sorted(call.args[0] for call in cancel.call_args_list), ["re_a", "re_b"])
        self.assertEqual([r["status"] for r in self.history()], ["cancelled", "cancelled"])

    @patch("assessments.email_records.cancel_scheduled_email", return_value="")
    @patch("assessments.views.send_assessment_invite_email", side_effect=["re_a", EmailInviteError("too far ahead")])
    def test_a_schedule_that_fails_part_way_calls_back_the_ones_already_queued(self, _send, cancel):
        self.assertEqual(self.schedule().status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual([call.args[0] for call in cancel.call_args_list], ["re_a"])
        self.assertEqual(sorted(r["status"] for r in self.history()), ["cancelled", "failed"])


class ProviderCallTests(APITestCase):
    """The two calls to the email provider: the id comes back, and cancelling uses it."""

    def content(self):
        from assessments.email_invites import InviteContent
        return InviteContent(subject="", message="", include_consent=True, invite_url="https://x/r?token=t",
                             client_email="jordan@example.com")

    @patch("assessments.email_invites._require_settings")
    @patch("assessments.email_invites.resend.Emails.send", return_value={"id": "re_42"})
    def test_sending_returns_the_provider_id(self, _send, _settings):
        from assessments.email_invites import send_assessment_invite_email
        self.assertEqual(send_assessment_invite_email(self.content()), "re_42")

    @patch("assessments.email_invites._require_settings")
    @patch("assessments.email_invites.resend.Emails.cancel", create=True)
    def test_cancelling_names_the_email(self, cancel, _settings):
        from assessments.email_invites import cancel_scheduled_email
        self.assertEqual(cancel_scheduled_email("re_42"), "")
        cancel.assert_called_once_with(email_id="re_42")
        self.assertIn("No email id", cancel_scheduled_email(""))

    @patch("assessments.email_invites._require_settings")
    @patch("assessments.email_invites.resend.Emails.cancel", create=True, side_effect=Exception("key lacks permission"))
    def test_a_refused_cancel_keeps_the_reason(self, _cancel, _settings):
        from assessments.email_invites import cancel_scheduled_email
        self.assertIn("key lacks permission", cancel_scheduled_email("re_42"))
