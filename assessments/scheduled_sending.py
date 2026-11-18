"""Sending scheduled assessment emails on the day they are due.

Schedules used to hand every email to the provider at creation, to be held and
sent later. That broke three ways, all seen on the live site in November 2026:
the provider holds email for 30 days at most, so a monthly schedule was refused;
deleting a schedule could not call its emails back with a send-only key; and the
link in each email was made at creation and expires after 48 hours, so every
email after the first arrived with a dead link.

Now nothing is handed over early. A job on the server (``manage.py
send_due_invites``, every 15 minutes) sends each email when its time comes, with
a link made at that moment. Deleting a schedule deletes its unsent emails.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from django.utils import timezone

from .email_invites import (
    EmailInviteError,
    InviteContent,
    _normalise_subject,
    build_invite_url,
    send_assessment_invite_email,
)
from .models import AssessmentEmailRecord, RespondentInviteScheduleRun
from .respondent_links import RespondentLinkError, issue_link_token

logger = logging.getLogger(__name__)

SCHEDULED = "scheduled"
SENDING = "sending"
SENT = "sent"
FAILED = "failed"


@dataclass
class SendSummary:
    sent: List[int] = field(default_factory=list)
    failed: List[int] = field(default_factory=list)


def due_runs(now=None):
    """Runs whose time has come and that are ours to send.

    A run with a token was handed to the provider in advance (the old way) and
    the provider sends it, so it is left alone here.
    """
    now = now or timezone.now()
    return (
        RespondentInviteScheduleRun.objects.filter(status=SCHEDULED, token="", scheduled_at__lte=now)
        .select_related("schedule", "schedule__client", "schedule__owner")
        .order_by("scheduled_at", "id")
    )


def _claim(run: RespondentInviteScheduleRun) -> bool:
    """Mark a run as being sent, unless another job got there first."""
    return RespondentInviteScheduleRun.objects.filter(pk=run.pk, status=SCHEDULED, token="").update(status=SENDING) == 1


def send_run(run: RespondentInviteScheduleRun) -> Optional[str]:
    """Send one due run. Returns None when sent, otherwise why it was not."""
    if not _claim(run):
        return "Already being sent."
    schedule = run.schedule
    client = schedule.client
    record = AssessmentEmailRecord.objects.filter(run=run).first()

    def fail(reason: str) -> str:
        RespondentInviteScheduleRun.objects.filter(pk=run.pk).update(status=FAILED)
        if record:
            record.status = AssessmentEmailRecord.Status.FAILED
            record.error = reason[:2000]
            record.save(update_fields=["status", "error"])
        logger.warning("Scheduled invite %s not sent: %s", run.pk, reason)
        return reason

    if not client.email:
        return fail("The client has no email address on file.")
    try:
        token = issue_link_token(
            owner_id=schedule.owner_id,
            assessments=schedule.assessments,
            mode="linked",
            client_slug=client.slug,
            share_results=schedule.share_results,
        )
    except RespondentLinkError as exc:
        # e.g. an assessment in the schedule has since been unpublished.
        return fail(str(exc))
    try:
        provider_id = send_assessment_invite_email(
            InviteContent(
                subject=schedule.subject,
                message=schedule.message,
                include_consent=schedule.include_consent,
                invite_url=build_invite_url(token),
                client_email=client.email,
                reply_to=schedule.reply_to or None,
            )
        )
    except EmailInviteError as exc:
        return fail(str(exc))

    now = timezone.now()
    RespondentInviteScheduleRun.objects.filter(pk=run.pk).update(status=SENT, sent_at=now, token=token)
    if record:
        record.status = AssessmentEmailRecord.Status.SENT
        record.send_at = now
        record.token = token
        record.provider_id = provider_id or ""
        record.recipient_email = client.email
        record.subject = _normalise_subject(schedule.subject)
        record.save(update_fields=["status", "send_at", "token", "provider_id", "recipient_email", "subject"])
    return None


def send_due_runs(now=None) -> SendSummary:
    summary = SendSummary()
    for run in due_runs(now):
        reason = send_run(run)
        if reason is None:
            summary.sent.append(run.pk)
        elif reason != "Already being sent.":
            summary.failed.append(run.pk)
    return summary
