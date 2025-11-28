from __future__ import annotations

from ipaddress import ip_address, ip_network

from django.conf import settings
from django.http import HttpResponseNotFound


def _normalise_ip_list(raw_items: tuple[str, ...]) -> tuple[ip_network, ...]:
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
    header_value = request.META.get("HTTP_X_FORWARDED_FOR")
    if header_value:
        first = header_value.split(",")[0].strip()
        if first:
            return first
    remote = request.META.get("REMOTE_ADDR")
    if remote:
        return remote.strip()
    return None


class AdminAccessMiddleware:
    """Restrict access to the Django admin using IP allowlists and optional header tokens."""

    def __init__(self, get_response):
        self.get_response = get_response
        slug = getattr(settings, "ADMIN_URL", "admin/").strip("/")
        self._admin_prefix = f"/{slug}" if slug else "/admin"

    def __call__(self, request):
        if request.path.startswith(self._admin_prefix):
            if not self._is_allowed(request):
                return HttpResponseNotFound()
        return self.get_response(request)

    def _is_allowed(self, request) -> bool:
        if settings.DEBUG:
            return True

        raw_allowed = getattr(settings, "ADMIN_ALLOWED_IPS", tuple())
        allowed_networks = _normalise_ip_list(tuple(raw_allowed))
        token = getattr(settings, "ADMIN_ACCESS_TOKEN", "")

        ip_value = _client_ip(request)
        allowed_by_ip = not allowed_networks
        if ip_value and allowed_networks:
            try:
                addr = ip_address(ip_value)
                allowed_by_ip = any(addr in network for network in allowed_networks)
            except ValueError:
                allowed_by_ip = False

        provided = request.META.get("HTTP_X_ADMIN_TOKEN", "").strip()
        token_matches = bool(token) and provided == token

        if token:
            return allowed_by_ip or token_matches

        return allowed_by_ip
