from django.urls import path

from .views import NotificationListView, NotificationMarkReadView

app_name = "notifications"

urlpatterns = [
    path("notifications/", NotificationListView.as_view(), name="list"),
    path("notifications/<int:pk>/read/", NotificationMarkReadView.as_view(), name="mark-read"),
]
