from __future__ import annotations

from dataclasses import dataclass

import resend
from django.conf import settings


@dataclass(frozen=True)
class TwoFactorEmail:
    recipient: str
    recipient_name: str
    code: str


class TwoFactorEmailError(RuntimeError):
    """Raised when a two-factor email cannot be sent."""


def _require_settings() -> None:
    if not settings.RESEND_API_KEY:
        raise TwoFactorEmailError("Resend API key is not configured.")
    if not settings.RESEND_FROM_EMAIL:
        raise TwoFactorEmailError("Resend from email address is not configured.")


def _build_subject(name: str) -> str:
    formatted_name = name.strip() or "Clinician"
    return f"Your Baker Street verification code, {formatted_name}".strip()


def _mask_code_in_text(code: str) -> tuple[str, str]:
    spaced = " ".join(code)
    return spaced, code


def send_two_factor_email(payload: TwoFactorEmail) -> None:
    """Dispatch the verification code email via Resend."""

    _require_settings()

    resend.api_key = settings.RESEND_API_KEY

    spaced_code, plain_code = _mask_code_in_text(payload.code)
    subject = _build_subject(payload.recipient_name)

    text_body = (
        "We received a request to sign in to your Baker Street account.\n\n"
        f"Your verification code is: {spaced_code}\n\n"
        "This code expires in approximately "
        f"{settings.TWO_FACTOR_CODE_TTL_MINUTES} minutes."
    )

    html_body = (
        "<div style=\"font-family:Inter,Helvetica,Arial,sans-serif;font-size:15px;color:#0f172a;line-height:1.6;\">"
        "<p style=\"margin:0 0 18px\">We received a request to sign in to your Baker Street account.</p>"
        "<p style=\"margin:0 0 18px;font-size:26px;font-weight:600;letter-spacing:6px;text-align:center;color:#0f766e;\">"
        f"{plain_code}</p>"
        f"<p style=\"margin:0\">This code expires in approximately {settings.TWO_FACTOR_CODE_TTL_MINUTES} minutes.</p>"
        "<p style=\"margin:24px 0 0;font-size:13px;color:#64748b\">If you didn't request this, you can ignore this email.</p>"
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
        raise TwoFactorEmailError("Unable to send verification code email.") from exc
