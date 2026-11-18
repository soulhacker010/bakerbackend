"""Scheduled emails sent on their day by the send_due_invites job (Nov 2026).

What broke on the live site, and must not again: monthly schedules refused (the
provider holds email 30 days at most), deleted schedules still sending, and every
email after the first carrying a link that had expired 48 hours after creation.
"""
from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework import status
from rest_framework.test import APITestCase

from assessments.email_invites import EmailInviteError, build_invite_url
from assessments.models import Assessment, AssessmentEmailRecord, RespondentInvite, RespondentInviteScheduleRun
from assessments.respondent_links import resolve_link_token
from assessments.scheduled_sending import send_due_runs, send_run
from clients.models import Client

SEND = "assessments.scheduled_sending.send_assessment_invite_email"


class ScheduledSendingTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="clinician@example.com",
                                                         password=get_random_string(32))
        self.client.force_authenticate(self.user)
        self.phq = Assessment.objects.create(title="PHQ-9", slug="phq-9", status=Assessment.Status.PUBLISHED,
                                             created_by=self.user)
        self.jordan = Client.objects.create(owner=self.user, first_name="Jordan", email="jordan@example.com",
                                            slug="jordan")

    def schedule(self, frequency="week", cycles=3, **email):
        response = self.client.post(reverse("assessments:respondent-link-schedule"), data={
            "assessments": ["phq-9"], "clientSlug": "jordan",
            "email": {"subject": "Check-in", "message": "Hi", **email},
            "schedule": {"startDate": (timezone.now().date() + timedelta(days=1)).isoformat(),
                         "frequency": frequency, "cycles": cycles}}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        return response.json()["scheduleId"]

    def runs(self):
        return list(RespondentInviteScheduleRun.objects.order_by("scheduled_at"))

    def make_due(self, run):
        RespondentInviteScheduleRun.objects.filter(pk=run.pk).update(scheduled_at=timezone.now() - timedelta(minutes=1))

    def test_a_monthly_schedule_is_accepted(self):
        self.schedule(frequency="month", cycles=3)
        self.assertEqual(len(self.runs()), 3)
        self.assertGreater(self.runs()[-1].scheduled_at - timezone.now(), timedelta(days=59))

    @patch(SEND, return_value="re_1")
    def test_only_due_emails_go_out(self, send):
        self.schedule()
        self.assertEqual(send_due_runs().sent, [])
        first = self.runs()[0]
        self.make_due(first)
        self.assertEqual(send_due_runs().sent, [first.pk])
        self.assertEqual(send.call_count, 1)
        self.assertEqual([r.status for r in self.runs()], ["sent", "scheduled", "scheduled"])

    @patch(SEND, return_value="re_1")
    def test_the_link_is_made_when_the_email_goes_out(self, send):
        self.schedule(replyTo="clinic@example.com")
        first = self.runs()[0]
        RespondentInviteScheduleRun.objects.filter(pk=first.pk).update(scheduled_at=timezone.now() - timedelta(days=10))
        send_due_runs()
        first.refresh_from_db()
        self.assertTrue(first.token)
        # Still valid now, 10 days after its send date was due: it was made at sending.
        resolve_link_token(first.token)
        invite = RespondentInvite.objects.get(token=first.token)
        self.assertGreater(invite.expires_at, timezone.now() + timedelta(hours=47))
        content = send.call_args[0][0]
        self.assertEqual((content.client_email, content.reply_to), ("jordan@example.com", "clinic@example.com"))
        self.assertEqual(content.invite_url, build_invite_url(first.token))

    @patch(SEND, return_value="re_9")
    def test_the_email_record_turns_to_sent(self, _send):
        self.schedule(cycles=1)
        self.make_due(self.runs()[0])
        send_due_runs()
        record = AssessmentEmailRecord.objects.get()
        self.assertEqual((record.status, record.provider_id), ("sent", "re_9"))
        self.assertTrue(record.token)
        self.assertLess(timezone.now() - record.send_at, timedelta(minutes=1))

    @patch(SEND, side_effect=EmailInviteError("provider down"))
    def test_a_failed_send_is_recorded_and_not_retried_forever(self, _send):
        self.schedule(cycles=1)
        self.make_due(self.runs()[0])
        summary = send_due_runs()
        self.assertEqual(len(summary.failed), 1)
        self.assertEqual(self.runs()[0].status, "failed")
        record = AssessmentEmailRecord.objects.get()
        self.assertEqual(record.status, "failed")
        self.assertIn("provider down", record.error)
        self.assertEqual(send_due_runs().failed, [])

    @patch(SEND, return_value="re_1")
    def test_an_assessment_unpublished_since_is_reported_not_sent(self, send):
        self.schedule(cycles=1)
        self.phq.status = Assessment.Status.DRAFT
        self.phq.save(update_fields=["status"])
        self.make_due(self.runs()[0])
        send_due_runs()
        send.assert_not_called()
        self.assertEqual(AssessmentEmailRecord.objects.get().status, "failed")

    @patch(SEND, return_value="re_1")
    def test_a_deleted_schedule_sends_nothing(self, send):
        reference = self.schedule()
        for run in self.runs():
            self.make_due(run)
        self.client.delete(reverse("assessments:respondent-link-schedule-detail", args=[reference]))
        self.assertEqual(send_due_runs().sent, [])
        send.assert_not_called()

    @patch(SEND, return_value="re_1")
    def test_an_email_is_never_sent_twice(self, send):
        self.schedule(cycles=1)
        run = self.runs()[0]
        self.make_due(run)
        self.assertIsNone(send_run(run))
        self.assertEqual(send_run(run), "Already being sent.")
        self.assertEqual(send_due_runs().sent, [])
        self.assertEqual(send.call_count, 1)

    @patch(SEND, return_value="re_1")
    def test_an_email_handed_over_the_old_way_is_left_to_the_provider(self, send):
        self.schedule(cycles=1)
        run = self.runs()[0]
        RespondentInviteScheduleRun.objects.filter(pk=run.pk).update(
            token="old-token", scheduled_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(send_due_runs().sent, [])
        send.assert_not_called()

    @patch(SEND, return_value="re_1")
    def test_the_command_reports_what_it_sent(self, _send):
        self.schedule(cycles=2)
        self.make_due(self.runs()[0])
        out = StringIO()
        call_command("send_due_invites", stdout=out)
        self.assertIn("sent 1, failed 0", out.getvalue())
