"""
Service health check functions.

Each check returns a dict with:
- status: "ok" | "degraded" | "down"
- latencyMs: response time in milliseconds
- message: optional human-readable detail

Infrastructure checks: Database, Resend, Turnstile
Feature checks: Assessments, Clients, etc.
"""

from __future__ import annotations

import time
from typing import TypedDict

import httpx
from django.conf import settings
from django.db import connection
from django.contrib.auth import get_user_model


class CheckResult(TypedDict, total=False):
    status: str
    latencyMs: float
    message: str


def check_database() -> CheckResult:
    """Ping the database with a simple query."""
    start = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latencyMs": round(latency, 2)}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return {
            "status": "down",
            "latencyMs": round(latency, 2),
            "message": str(exc)[:200],
        }


def check_resend() -> CheckResult:
    """
    Check Resend email API availability.
    We just verify the API is reachable. The API key is validated by checking
    if we get a proper response (even 401/403 means API is up).
    If no API key configured, return degraded.
    """
    api_key = getattr(settings, "RESEND_API_KEY", "") or ""
    if not api_key.strip():
        return {"status": "degraded", "latencyMs": 0, "message": "RESEND_API_KEY not configured"}

    start = time.perf_counter()
    try:
        # Just check if Resend API is reachable - any response means it's up
        # We use /emails endpoint with GET (will return 405 Method Not Allowed, but that's fine)
        response = httpx.get(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5.0,
        )
        latency = (time.perf_counter() - start) * 1000
        
        # Any HTTP response means the API is reachable and our key is configured
        # 405 = Method not allowed (expected for GET on /emails)
        # 200/401/403 = API is responding
        if response.status_code in (200, 401, 403, 405):
            return {"status": "ok", "latencyMs": round(latency, 2)}
        return {
            "status": "degraded",
            "latencyMs": round(latency, 2),
            "message": f"Unexpected status {response.status_code}",
        }
    except httpx.TimeoutException:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": "Request timed out"}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": str(exc)[:200]}


def check_turnstile() -> CheckResult:
    """
    Check Cloudflare Turnstile API availability.
    We send a dummy verification request; we expect a failure response (invalid token),
    but that confirms the API is reachable.
    """
    secret = getattr(settings, "TURNSTILE_SECRET", "") or ""
    if not secret.strip():
        return {"status": "degraded", "latencyMs": 0, "message": "TURNSTILE_SECRET not configured"}

    start = time.perf_counter()
    try:
        response = httpx.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret, "response": "health-check-dummy-token"},
            timeout=5.0,
        )
        latency = (time.perf_counter() - start) * 1000
        # We expect success=false because the token is invalid, but the API responded
        if response.status_code == 200:
            return {"status": "ok", "latencyMs": round(latency, 2)}
        return {
            "status": "degraded",
            "latencyMs": round(latency, 2),
            "message": f"Unexpected status {response.status_code}",
        }
    except httpx.TimeoutException:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": "Request timed out"}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": str(exc)[:200]}


# =============================================================================
# FEATURE CHECKS - Test internal API functionality
# =============================================================================

def check_auth() -> CheckResult:
    """Check authentication system by verifying User model is accessible."""
    start = time.perf_counter()
    try:
        User = get_user_model()
        User.objects.exists()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latencyMs": round(latency, 2)}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": str(exc)[:200]}


def check_clients() -> CheckResult:
    """Check Clients API by querying the Client model."""
    start = time.perf_counter()
    try:
        from clients.models import Client
        Client.objects.exists()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latencyMs": round(latency, 2)}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": str(exc)[:200]}


def check_client_groups() -> CheckResult:
    """Check Client Groups API by querying the ClientGroup model."""
    start = time.perf_counter()
    try:
        from clients.models import ClientGroup
        ClientGroup.objects.exists()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latencyMs": round(latency, 2)}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": str(exc)[:200]}


def check_assessments() -> CheckResult:
    """Check Assessments API by querying the Assessment model."""
    start = time.perf_counter()
    try:
        from assessments.models import Assessment
        Assessment.objects.exists()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latencyMs": round(latency, 2)}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": str(exc)[:200]}


def check_assessment_responses() -> CheckResult:
    """Check Assessment Responses by querying the AssessmentResponse model."""
    start = time.perf_counter()
    try:
        from assessments.models import AssessmentResponse
        AssessmentResponse.objects.exists()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latencyMs": round(latency, 2)}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": str(exc)[:200]}


def check_respondent_links() -> CheckResult:
    """Check Respondent Links by querying the RespondentInvite model."""
    start = time.perf_counter()
    try:
        from assessments.models import RespondentInvite
        RespondentInvite.objects.exists()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latencyMs": round(latency, 2)}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": str(exc)[:200]}


def check_scheduled_assessments() -> CheckResult:
    """Check Scheduled Assessments by querying the RespondentInviteSchedule model."""
    start = time.perf_counter()
    try:
        from assessments.models import RespondentInviteSchedule
        RespondentInviteSchedule.objects.exists()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latencyMs": round(latency, 2)}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": str(exc)[:200]}


def check_notifications() -> CheckResult:
    """Check Notifications by querying the Notification model."""
    start = time.perf_counter()
    try:
        from notifications.models import Notification
        Notification.objects.exists()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latencyMs": round(latency, 2)}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return {"status": "down", "latencyMs": round(latency, 2), "message": str(exc)[:200]}
