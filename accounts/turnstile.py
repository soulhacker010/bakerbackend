import logging
from typing import Any

import requests
from django.conf import settings

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
MISCONFIGURATION_CODES = {"missing-input-secret", "invalid-input-secret"}

logger = logging.getLogger(__name__)


class TurnstileValidationError(Exception):
    """Raised when the user must re-complete the Turnstile challenge."""


class TurnstileServiceError(Exception):
    """Raised when the backend cannot complete Turnstile verification."""


def validate_turnstile_token(response_token: str | None, remote_ip: str | None = None) -> None:
    """Validate a Cloudflare Turnstile token.

    When TURNSTILE_ENABLED is False the function becomes a no-op so that the
    calling code does not need to branch on its own.
    """

    if not getattr(settings, "TURNSTILE_ENABLED", False):
        return

    secret = getattr(settings, "TURNSTILE_SECRET", "").strip()
    if not secret:
        logger.error("TURNSTILE_ENABLED is True but TURNSTILE_SECRET is missing.")
        raise TurnstileServiceError("Turnstile verification is temporarily unavailable. Please try again later.")

    if not response_token:
        raise TurnstileValidationError("Turnstile verification is required.")

    payload: dict[str, Any] = {
        "secret": secret,
        "response": response_token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        resp = requests.post(TURNSTILE_VERIFY_URL, data=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:  # pragma: no cover - network failure
        logger.warning("Turnstile verification request failed: %s", exc)
        raise TurnstileServiceError("Unable to verify Turnstile token. Please try again.") from exc

    if data.get("success"):
        return

    error_codes: list[str] = data.get("error-codes") or []
    if any(code in MISCONFIGURATION_CODES for code in error_codes):
        logger.error("Turnstile secret rejected: codes=%s", error_codes)
        raise TurnstileServiceError("Turnstile verification is temporarily unavailable. Please try again later.")

    if "timeout-or-duplicate" in error_codes:
        raise TurnstileValidationError("Turnstile verification timed out. Please refresh and try again.")

    raise TurnstileValidationError("Turnstile verification failed. Please try again.")
