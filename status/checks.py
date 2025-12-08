"""
Service health check functions.

Each check returns a dict with:
- status: "ok" | "degraded" | "down"
- latencyMs: response time in milliseconds
- message: optional human-readable detail
"""

from __future__ import annotations

import time
from typing import TypedDict

import httpx
from django.conf import settings
from django.db import connection


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
    We hit their /emails endpoint with a HEAD-like GET to /domains (lightweight).
    If no API key configured, return degraded.
    """
    api_key = getattr(settings, "RESEND_API_KEY", "") or ""
    if not api_key.strip():
        return {"status": "degraded", "latencyMs": 0, "message": "RESEND_API_KEY not configured"}

    start = time.perf_counter()
    try:
        # Use the /domains endpoint as a lightweight check (list domains)
        response = httpx.get(
            "https://api.resend.com/domains",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5.0,
        )
        latency = (time.perf_counter() - start) * 1000
        if response.status_code in (200, 401, 403):
            # 401/403 means API is reachable but key might be invalid
            if response.status_code == 200:
                return {"status": "ok", "latencyMs": round(latency, 2)}
            return {
                "status": "degraded",
                "latencyMs": round(latency, 2),
                "message": f"API returned {response.status_code}",
            }
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
