from rest_framework.routers import DefaultRouter

from .views import ClientGroupViewSet, ClientViewSet

app_name = "clients"

router = DefaultRouter()
router.register(r"clients", ClientViewSet, basename="client")
router.register(r"client-groups", ClientGroupViewSet, basename="client-group")

urlpatterns = router.urls
