from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Tuple

from django.conf import settings
from django.utils import timezone

from .models import PasswordResetToken, User


def _hash_token(token: str, salt: str) -> str:
    payload = f"{salt}:{token}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def issue_password_reset_token(user: User) -> Tuple[PasswordResetToken | None, str | None, bool]:
    """Create a password reset token for the user and return the raw value.

    Returns a tuple of (token, raw_token, created). When an unexpired token was
    requested too recently, the existing token is returned with ``raw_token`` set
    to ``None`` and ``created`` to ``False`` so callers can throttle emails.
    """

    now = timezone.now()
    cooldown_seconds = getattr(settings, "PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS", 5 * 60)
    cutoff = now - timedelta(seconds=cooldown_seconds)

    recent_token = (
        PasswordResetToken.objects.filter(user=user, used_at__isnull=True, created_at__gte=cutoff)
        .order_by("-created_at")
        .first()
    )

    if recent_token and not recent_token.is_expired():
        return recent_token, None, False

    # Clean up any expired unused tokens before issuing a new one.
    PasswordResetToken.objects.filter(user=user, used_at__isnull=True, expires_at__lt=now).delete()

    raw_token = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    token_hash = _hash_token(raw_token, salt)

    expires_minutes = getattr(settings, "PASSWORD_RESET_TOKEN_TTL_MINUTES", 60 * 24)
    token = PasswordResetToken.objects.create(
        user=user,
        token_hash=token_hash,
        token_salt=salt,
        expires_at=now + timedelta(minutes=expires_minutes),
    )

    return token, raw_token, True


def verify_password_reset_token(token: PasswordResetToken, raw_token: str) -> bool:
    if token.used_at is not None or token.is_expired():
        return False

    expected = _hash_token(raw_token, token.token_salt)
    return secrets.compare_digest(expected, token.token_hash)


def invalidate_password_reset_tokens(user: User, exclude_id: int | None = None) -> None:
    queryset = PasswordResetToken.objects.filter(user=user, used_at__isnull=True)
    if exclude_id is not None:
        queryset = queryset.exclude(pk=exclude_id)
    queryset.update(used_at=timezone.now())
