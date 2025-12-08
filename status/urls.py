from django.urls import path

from .views import health_simple, HealthFullView

app_name = "status"

urlpatterns = [
    path("", health_simple, name="health_simple"),
    path("full/", HealthFullView.as_view(), name="health_full"),
]
