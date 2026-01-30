from __future__ import annotations

from dataclasses import dataclass

import resend
from django.conf import settings


@dataclass(frozen=True)
class SignupVerificationEmail:
    recipient: str
    recipient_name: str
    code: str


class SignupVerificationEmailError(RuntimeError):
    """Raised when a signup verification email cannot be sent."""


def _require_settings() -> None:
    if not settings.RESEND_API_KEY:
        raise SignupVerificationEmailError("Resend API key is not configured.")
    if not settings.RESEND_FROM_EMAIL:
        raise SignupVerificationEmailError("Resend from email address is not configured.")


def _build_subject(name: str) -> str:
    formatted_name = name.strip() or "Clinician"
    return f"Welcome to Baker Street, {formatted_name}! Verify your email".strip()


def _mask_code_in_text(code: str) -> tuple[str, str]:
    spaced = " ".join(code)
    return spaced, code


def send_signup_verification_email(payload: SignupVerificationEmail) -> None:
    """Dispatch the signup verification code email via Resend."""

    _require_settings()

    resend.api_key = settings.RESEND_API_KEY

    spaced_code, plain_code = _mask_code_in_text(payload.code)
    subject = _build_subject(payload.recipient_name)

    text_body = (
        f"Welcome to Baker Street Health, {payload.recipient_name}!\n\n"
        "To complete your registration and verify your email address, "
        f"please enter the following 6-digit code:\n\n"
        f"{spaced_code}\n\n"
        "This code expires in approximately "
        f"{settings.TWO_FACTOR_CODE_TTL_MINUTES} minutes.\n\n"
        "Once verified, your account will be reviewed by an administrator before you can sign in."
    )

    html_body = (
        "<div style=\"font-family:Inter,Helvetica,Arial,sans-serif;font-size:15px;color:#0f172a;line-height:1.6;\">"
        f"<p style=\"margin:0 0 18px;font-size:18px;font-weight:600;color:#0f766e;\">Welcome to Baker Street Health, {payload.recipient_name}!</p>"
        "<p style=\"margin:0 0 18px\">To complete your registration and verify your email address, "
        "please enter the following 6-digit code:</p>"
        "<p style=\"margin:0 0 18px;font-size:32px;font-weight:700;letter-spacing:8px;text-align:center;color:#0f766e;\">"
        f"{plain_code}</p>"
        f"<p style=\"margin:0 0 18px\">This code expires in approximately {settings.TWO_FACTOR_CODE_TTL_MINUTES} minutes.</p>"
        "<p style=\"margin:0;font-size:14px;color:#64748b\">Once verified, your account will be reviewed by an administrator before you can sign in.</p>"
        "<p style=\"margin:24px 0 0;font-size:13px;color:#64748b\">If you didn't request this, you can safely ignore this email.</p>"
        "</div>"
    )

    try:
        resend.Emails.send(
            {
                "from": settings.RESEND_FROM_EMAIL,
                "to": payload.recipient,
                "subject": subject,
                "text": text_body,
                "html": html_body,
            }
        )
    except Exception as exc:  # pragma: no cover - network or API failure
        raise SignupVerificationEmailError("Unable to send verification code email.") from exc
