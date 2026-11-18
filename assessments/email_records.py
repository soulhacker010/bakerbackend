"""The practice's own record of every assessment invitation it emails.

Asked for in November 2026: "when assessments are emailed to a client, the
system does not keep a record of what was sent or when it was sent". The email
provider deletes its copies after a few weeks, so this is the record that lasts.
A failed send is recorded too, so a clinician can see it did not go out.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from django.utils import timezone

from clients.models import Client

from .email_invites import cancel_scheduled_email
from .models import Assessment, AssessmentEmailRecord, RespondentInviteSchedule


def recipient_label(client: Client, rater: str) -> str:
    """Blank for the client; "Informant - <name>" for someone on their record."""
    if rater in ("informant1", "informant2"):
        name = (getattr(client, f"{rater}_name", "") or "").strip()
        return f"Informant - {name}" if name else "Informant"
    return ""


def record_email(
    *,
    owner,
    client: Client,
    recipient_email: str,
    assessment_slugs: Iterable[str],
    subject: str,
    send_at: datetime,
    kind: str = AssessmentEmailRecord.Kind.NOW,
    status: str = AssessmentEmailRecord.Status.SENT,
    rater: str = "",
    token: str = "",
    provider_id: str = "",
    error: str = "",
    schedule: Optional[RespondentInviteSchedule] = None,
) -> AssessmentEmailRecord:
    slugs = list(dict.fromkeys(slug for slug in assessment_slugs if slug))
    titles = dict(Assessment.objects.filter(slug__in=slugs).values_list("slug", "title"))
    return AssessmentEmailRecord.objects.create(
        owner=owner,
        client=client,
        client_name=str(client),
        recipient_email=recipient_email,
        recipient_label=recipient_label(client, rater),
        assessments=[{"slug": slug, "title": titles.get(slug, slug)} for slug in slugs],
        subject=subject[:255],
        kind=kind,
        status=status,
        send_at=send_at,
        error=error,
        token=token,
        provider_id=provider_id,
        schedule=schedule,
    )


def cancel_queued_emails(schedule: RespondentInviteSchedule) -> int:
    """Call back a schedule's emails that have not gone out yet. Returns how many."""
    cancelled = 0
    pending = schedule.email_records.filter(status=AssessmentEmailRecord.Status.SCHEDULED, send_at__gt=timezone.now())
    for record in pending:
        reason = cancel_scheduled_email(record.provider_id)
        if not reason:
            record.status = AssessmentEmailRecord.Status.CANCELLED
            record.save(update_fields=["status"])
            cancelled += 1
        else:
            record.error = f"Could not be cancelled with the email provider, so it may still be sent: {reason}"
            record.save(update_fields=["error"])
    return cancelled
