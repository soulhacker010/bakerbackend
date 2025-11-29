from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated

GENERIC_AUTH_MESSAGE = (
    "Authentication is required to access this resource. Please sign in at the Baker Street "
    "dashboard and retry your request."
)
EXPIRED_AUTH_MESSAGE = "Your session is no longer valid. Please sign in again to continue."


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Wrap DRF's default handler to present friendlier auth failures."""

    response = drf_exception_handler(exc, context)

    if response is None:
        return None

    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        if isinstance(exc, NotAuthenticated):
            response.data = {
                "detail": GENERIC_AUTH_MESSAGE,
                "code": "authentication_required",
            }
        elif isinstance(exc, AuthenticationFailed):
            response.data = {
                "detail": EXPIRED_AUTH_MESSAGE,
                "code": "authentication_failed",
            }

    return response
