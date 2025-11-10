from django.db.models import QuerySet
from django.http import Http404
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self, request: Request) -> QuerySet[Notification]:
        return Notification.objects.filter(recipient=request.user).order_by("-created_at")

    def get(self, request: Request) -> Response:
        queryset = self.get_queryset(request)
        serializer = NotificationSerializer(queryset, many=True)
        return Response(serializer.data)


class NotificationMarkReadView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request: Request, *args, **kwargs) -> Response:
        notification = self._get_notification(request, kwargs.get("pk"))
        notification.mark_read()
        serializer = NotificationSerializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def _get_notification(self, request: Request, pk: str | int) -> Notification:
        try:
            notification = Notification.objects.get(pk=pk, recipient=request.user)
        except Notification.DoesNotExist as exc:  # pragma: no cover - defensive
            raise Http404("Notification not found") from exc
        return notification
