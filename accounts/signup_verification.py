from __future__ import annotations

import hashlib
import secrets
import string
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from .models import SignupVerificationChallenge

_DIGITS = string.digits


def _generate_code() -> str:
    length = max(4, min(settings.TWO_FACTOR_CODE_LENGTH, 10))
    return "".join(secrets.choice(_DIGITS) for _ in range(length))


def _hash_code(code: str, salt: str) -> str:
    payload = f"{salt}:{code}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def create_signup_verification_challenge(
    email: str,
    first_name: str,
    last_name: str,
    profession: str,
    password: str,
) -> tuple[SignupVerificationChallenge, str]:
    """Create a new signup verification challenge, replacing any existing ones for this email."""

    # Delete any existing challenges for this email
    SignupVerificationChallenge.objects.filter(email=email).delete()

    now = timezone.now()
    code = _generate_code()
    salt = secrets.token_hex(16)

    challenge = SignupVerificationChallenge.objects.create(
        email=email,
        first_name=first_name,
        last_name=last_name,
        profession=profession,
        password_hash=make_password(password),
        code_hash=_hash_code(code, salt),
        code_salt=salt,
        expires_at=now + timedelta(minutes=settings.TWO_FACTOR_CODE_TTL_MINUTES),
        last_sent_at=now,
    )
    return challenge, code


def regenerate_signup_verification_code(challenge: SignupVerificationChallenge) -> str:
    """Refresh the verification code for an existing signup challenge."""

    now = timezone.now()
    code = _generate_code()
    salt = secrets.token_hex(16)

    challenge.code_hash = _hash_code(code, salt)
    challenge.code_salt = salt
    challenge.expires_at = now + timedelta(minutes=settings.TWO_FACTOR_CODE_TTL_MINUTES)
    challenge.last_sent_at = now
    challenge.save(update_fields=["code_hash", "code_salt", "expires_at", "last_sent_at", "updated_at"])

    return code


def verify_signup_code(challenge: SignupVerificationChallenge, code: str) -> bool:
    expected = _hash_code(code, challenge.code_salt)
    return secrets.compare_digest(expected, challenge.code_hash)
