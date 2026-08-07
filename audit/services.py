"""Writing audit trail entries.

An audit write must never break a clinical request, but it must never fail
silently either, so every failure is logged with a stack trace.
"""
from __future__ import annotations

import logging
from ipaddress import ip_address

from bakerapi.middleware import _client_ip

from .models import AuditLog

logger = logging.getLogger(__name__)


def _resolve_ip(request) -> str | None:
    """Return the caller's IP, or None when the header cannot be trusted.

    ``X-Forwarded-For`` is attacker-controlled, so a value that is not a valid
    address is discarded rather than handed to the database.
    """
    raw = _client_ip(request) if request is not None else None
    if not raw:
        return None
    try:
        ip_address(raw)
    except ValueError:
        return None
    return raw


def _resolve_user(request, user):
    if user is not None:
        return user
    candidate = getattr(request, "user", None)
    if candidate is not None and getattr(candidate, "is_authenticated", False):
        return candidate
    return None


def record_audit(
    request,
    *,
    action: str,
    resource_type: str,
    resource_id: str = "",
    user=None,
) -> AuditLog | None:
    """Record one access to a protected record.

    ``resource_id`` must be an identifier such as a primary key. Never pass a
    name, email, slug derived from a name, or any part of a request body.
    """
    try:
        actor = _resolve_user(request, user)
        user_agent = ""
        if request is not None:
            user_agent = request.META.get("HTTP_USER_AGENT") or ""

        return AuditLog.objects.create(
            user=actor,
            user_email=(getattr(actor, "email", "") or "")[:254],
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id or "")[:64],
            ip_address=_resolve_ip(request),
            user_agent=user_agent[:400],
        )
    except Exception:  # pragma: no cover - auditing must not break the request
        logger.exception(
            "Unable to write audit log entry (action=%s resource_type=%s)",
            action,
            resource_type,
        )
        return None
