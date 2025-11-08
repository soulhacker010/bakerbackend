"""Helpers for emailing respondent assessment invites via Resend."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from typing import Optional
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

import resend

DEFAULT_CONSENT_TEXT = (
    "By completing these assessments you consent to Baker Street securely processing and storing your responses in line "
    "with HIPAA & GDPR obligations."
)


@dataclass(frozen=True)
class InviteContent:
    subject: str
    message: str
    include_consent: bool
    invite_url: str
    client_email: str
    reply_to: Optional[str] = None
    send_at: Optional[datetime] = None


class EmailInviteError(RuntimeError):
    """Raised when an invite email cannot be sent."""


def _require_settings() -> None:
    if not settings.RESEND_API_KEY:
        raise EmailInviteError("Resend API key is not configured.")
    if not settings.RESEND_FROM_EMAIL:
        raise EmailInviteError("Resend from email address is not configured.")


def _normalise_subject(subject: str) -> str:
    cleaned = (subject or "").strip()
    return cleaned or "Your Baker Street assessment invitation"


def _build_text_body(message: str, invite_url: str, include_consent: bool) -> str:
    lines = []
    body = (message or "").strip()
    if body:
        lines.append(body)
    if invite_url:
        if lines:
            lines.append("")
        lines.append(f"Follow the secure link to begin: {invite_url}")
    if include_consent:
        if lines:
            lines.append("")
        lines.append(DEFAULT_CONSENT_TEXT)
    return "\n".join(lines)


def _build_html_body(message: str, invite_url: str, include_consent: bool) -> str:
    paragraphs = []
    body = (message or "").strip().replace("\n", "<br />")
    if body:
        paragraphs.append(f"<p>{body}</p>")
    if invite_url:
        paragraphs.append(
            f'<p><a href="{invite_url}" style="color:#0f766e;font-weight:600;">Start your assessment</a></p>'
        )
    if include_consent:
        paragraphs.append(f"<p style=\"font-size:12px;color:#475569;\">{DEFAULT_CONSENT_TEXT}</p>")
    return "".join(paragraphs)


def send_assessment_invite_email(content: InviteContent) -> None:
    """Dispatch an assessment invite email using Resend."""

    _require_settings()

    # Configure API key on demand to avoid global state during tests
    resend.api_key = settings.RESEND_API_KEY

    subject = _normalise_subject(content.subject)
    invite_url = content.invite_url

    text_body = _build_text_body(content.message, invite_url, content.include_consent)
    html_body = _build_html_body(content.message, invite_url, content.include_consent)

    payload = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": content.client_email,
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }

    reply_to = content.reply_to or settings.RESEND_REPLY_TO
    if reply_to:
        payload["reply_to"] = reply_to

    if content.send_at:
        scheduled_at = content.send_at
        if timezone.is_naive(scheduled_at):
            scheduled_at = timezone.make_aware(scheduled_at, timezone.get_current_timezone())
        scheduled_at_utc = scheduled_at.astimezone(dt_timezone.utc)
        payload["scheduled_at"] = scheduled_at_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    try:
        resend.Emails.send(payload)
    except Exception as exc:  # pragma: no cover - network failure or API error
        raise EmailInviteError("Unable to send assessment invite email.") from exc


def build_invite_url(token: str) -> str:
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/respondent?token={quote(token)}"
