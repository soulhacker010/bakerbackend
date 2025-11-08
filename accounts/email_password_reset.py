from __future__ import annotations

from dataclasses import dataclass

import resend
from django.conf import settings


@dataclass(frozen=True)
class PasswordResetEmail:
    recipient: str
    recipient_name: str
    reset_url: str
    expires_minutes: int


class PasswordResetEmailError(RuntimeError):
    """Raised when a password reset email cannot be sent."""


def _require_settings() -> None:
    if not settings.RESEND_API_KEY:
        raise PasswordResetEmailError("Resend API key is not configured.")
    if not settings.RESEND_FROM_EMAIL:
        raise PasswordResetEmailError("Resend from email address is not configured.")


def _build_subject(name: str) -> str:
    formatted_name = name.strip() or "Clinician"
    return f"Reset your Baker Street password, {formatted_name}".strip()


def send_password_reset_email(payload: PasswordResetEmail) -> None:
    """Dispatch the password reset email via Resend."""

    _require_settings()

    resend.api_key = settings.RESEND_API_KEY

    subject = _build_subject(payload.recipient_name)
    expires_text = "24 hours" if payload.expires_minutes >= 1440 else f"{payload.expires_minutes} minutes"

    text_body = (
        "We received a request to reset the password for your Baker Street account.\n\n"
        f"To choose a new password, open this secure link: {payload.reset_url}\n\n"
        f"This link expires in {expires_text}. If you did not request a reset, you can safely ignore this email."
    )

    html_body = (
        '<div style="font-family:Inter,Helvetica,Arial,sans-serif;font-size:15px;color:#0f172a;line-height:1.6;">'
        '<p style="margin:0 0 18px;">We received a request to reset the password for your Baker Street account.</p>'
        '<p style="margin:0 0 18px;">'
        '<a href="{reset_url}" '
        'style="display:inline-block;padding:12px 24px;border-radius:999px;background-color:#0f766e;color:#ffffff;'
        'text-decoration:none;font-weight:600;">Reset password</a>'
        '</p>'
        '<p style="margin:0 0 18px;">This link expires in {expires_text}. If you did not request a reset, you can safely ignore this email.</p>'
        '<p style="margin:24px 0 0;font-size:13px;color:#64748b">For security, this link can only be used once.</p>'
        '</div>'
    ).format(reset_url=payload.reset_url, expires_text=expires_text)

    try:
        resend.Emails.send(
            {
                "from": settings.RESEND_FROM_EMAIL,
                "to": payload.recipient,
                "subject": subject,
                "text": text_body,
                "html": html_body,
                **({"reply_to": settings.RESEND_REPLY_TO} if settings.RESEND_REPLY_TO else {}),
            }
        )
    except Exception as exc:  # pragma: no cover - network or API failure
        raise PasswordResetEmailError("Unable to send password reset email.") from exc
