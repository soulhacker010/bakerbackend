from __future__ import annotations

from dataclasses import dataclass

import resend
from django.conf import settings


@dataclass(frozen=True)
class FeedbackEmail:
    author_email: str
    author_name: str
    feedback_type: str
    message: str


class FeedbackEmailError(RuntimeError):
    """Raised when a feedback email cannot be dispatched."""


_FEEDBACK_TYPE_LABELS = {
    "general": "General feedback",
    "error": "Error report",
    "feature": "Feature request",
    "other": "Feedback",
}


def _require_settings() -> None:
    if not settings.RESEND_API_KEY:
        raise FeedbackEmailError("Resend API key is not configured.")
    if not settings.RESEND_FROM_EMAIL:
        raise FeedbackEmailError("Resend from email address is not configured.")
    if not settings.FEEDBACK_TO_EMAIL:
        raise FeedbackEmailError("Feedback recipient email address is not configured.")


def _normalise_subject(feedback_type: str, author_name: str) -> str:
    label = _FEEDBACK_TYPE_LABELS.get(feedback_type, "Feedback")
    cleaned_author = author_name.strip() or "Clinician"
    return f"{label} from {cleaned_author}"


def _build_text_body(payload: FeedbackEmail) -> str:
    lines = [
        f"Type: {_FEEDBACK_TYPE_LABELS.get(payload.feedback_type, payload.feedback_type.title())}",
        f"From: {payload.author_name} <{payload.author_email}>",
        "",
        payload.message.strip(),
    ]
    return "\n".join(lines)


def _build_html_body(payload: FeedbackEmail) -> str:
    message_html = payload.message.strip().replace("\n", "<br />")
    feedback_label = _FEEDBACK_TYPE_LABELS.get(payload.feedback_type, payload.feedback_type.title())
    return (
        "<div style=\"font-family:Inter,Helvetica,Arial,sans-serif;font-size:14px;color:#0f172a;line-height:1.6;\">"
        f"<p><strong>Type:</strong> {feedback_label}</p>"
        f"<p><strong>From:</strong> {payload.author_name} &lt;{payload.author_email}&gt;</p>"
        f"<p style=\"margin-top:18px;white-space:pre-wrap;\">{message_html}</p>"
        "</div>"
    )


def send_feedback_email(payload: FeedbackEmail) -> None:
    """Send a feedback email to the configured recipient via Resend."""

    _require_settings()

    resend.api_key = settings.RESEND_API_KEY

    subject = _normalise_subject(payload.feedback_type, payload.author_name)
    text_body = _build_text_body(payload)
    html_body = _build_html_body(payload)

    try:
        resend.Emails.send(
            {
                "from": settings.RESEND_FROM_EMAIL,
                "to": settings.FEEDBACK_TO_EMAIL,
                "subject": subject,
                "text": text_body,
                "html": html_body,
                "reply_to": payload.author_email,
            }
        )
    except Exception as exc:  # pragma: no cover - network or API failure
        raise FeedbackEmailError("Unable to send feedback email.") from exc
