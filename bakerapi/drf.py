from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated

PLAIN_401_MESSAGE = "HTTP 401 Unauthorized"


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Collapse authentication failures into a single-line response."""

    response = drf_exception_handler(exc, context)

    if response is None:
        return None

    if response.status_code == status.HTTP_401_UNAUTHORIZED and isinstance(
        exc, (NotAuthenticated, AuthenticationFailed)
    ):
        return Response(
            PLAIN_401_MESSAGE,
            status=status.HTTP_401_UNAUTHORIZED,
            content_type="text/plain",
        )

    return response
