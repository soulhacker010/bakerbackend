"""
Health check API views.

- /api/health/ - Public, simple "ok" response for uptime monitors
- /api/health/full/ - Private, detailed service checks (admin only)
"""

from __future__ import annotations

import concurrent.futures
import time
from datetime import datetime, timezone
from ipaddress import ip_address, ip_network

from django.conf import settings
from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication

from .cache import get_cached, set_cached
from .checks import check_database, check_resend, check_turnstile


CACHE_KEY = "health_full_result"
CACHE_TTL_SECONDS = 30


def _normalise_ip_list(raw_items: tuple[str, ...]) -> tuple[ip_network, ...]:
    """Convert IP strings to network objects."""
    networks: list[ip_network] = []
    for item in raw_items:
        cleaned = item.strip()
        if not cleaned:
            continue
        try:
            networks.append(ip_network(cleaned, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _client_ip(request) -> str | None:
    """Extract client IP from request headers."""
    header_value = request.META.get("HTTP_X_FORWARDED_FOR")
    if header_value:
        first = header_value.split(",")[0].strip()
        if first:
            return first
    remote = request.META.get("REMOTE_ADDR")
    if remote:
        return remote.strip()
    return None


def _is_ip_allowed(ip_value: str | None, networks: tuple[ip_network, ...]) -> bool:
    """Check if IP is in allowed networks."""
    if not networks:
        return True
    if not ip_value:
        return False
    try:
        addr = ip_address(ip_value)
    except ValueError:
        return False
    return any(addr in network for network in networks)


def _token_matches(request, token: str) -> bool:
    """Check if provided token matches expected."""
    if not token:
        return False
    provided = request.META.get("HTTP_X_ADMIN_ACCESS_TOKEN", "").strip()
    return provided == token


def _is_admin_allowed(request) -> bool:
    """Check if request is allowed to access admin endpoints."""
    if settings.DEBUG:
        return True

    raw_allowed = getattr(settings, "ADMIN_ALLOWED_IPS", tuple())
    allowed_networks = _normalise_ip_list(tuple(raw_allowed))
    token = getattr(settings, "ADMIN_ACCESS_TOKEN", "")

    allowed_by_ip = _is_ip_allowed(_client_ip(request), allowed_networks)
    return allowed_by_ip or _token_matches(request, token)


def health_simple(request):
    """
    Public health endpoint for uptime monitors.
    Returns simple {"status": "ok"} with HTTP 200.
    """
    return JsonResponse({"status": "ok"})


class HealthFullView(APIView):
    """
    Private detailed health endpoint.
    Requires authenticated user (JWT) OR admin IP/token.
    Returns status of all services with latency metrics.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = []

    def get(self, request):
        # Allow if user is authenticated AND is superuser/staff (can manage assessments)
        is_superadmin = (
            request.user
            and request.user.is_authenticated
            and (request.user.is_superuser or request.user.is_staff)
        )

        # Also allow via IP allowlist or admin token (for external monitoring)
        is_admin_allowed = _is_admin_allowed(request)

        if not is_superadmin and not is_admin_allowed:
            return Response(
                {"detail": "Access denied. Superadmin privileges required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check cache first
        cached = get_cached(CACHE_KEY)
        if cached is not None:
            return Response(cached)

        # Run checks in parallel with timeout
        start = time.perf_counter()
        results = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(check_database): "database",
                executor.submit(check_resend): "email",
                executor.submit(check_turnstile): "turnstile",
            }

            for future in concurrent.futures.as_completed(futures, timeout=10):
                service_name = futures[future]
                try:
                    results[service_name] = future.result()
                except Exception as exc:
                    results[service_name] = {
                        "status": "down",
                        "latencyMs": 0,
                        "message": str(exc)[:200],
                    }

        total_latency = (time.perf_counter() - start) * 1000

        # Determine overall status
        statuses = [r.get("status", "down") for r in results.values()]
        if all(s == "ok" for s in statuses):
            overall = "ok"
        elif any(s == "down" for s in statuses):
            overall = "down"
        else:
            overall = "degraded"

        response_data = {
            "status": overall,
            "services": results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "responseTimeMs": round(total_latency, 2),
        }

        # Cache the result
        set_cached(CACHE_KEY, response_data, CACHE_TTL_SECONDS)

        return Response(response_data)
