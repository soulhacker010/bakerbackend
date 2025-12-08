"""
URL configuration for bakerapi project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf import settings
from django.conf import settings
from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import include, path
from django.conf import settings

from .admin_site import admin_site

urlpatterns = [
    path(settings.ADMIN_URL, admin_site.urls),
    path('api/auth/', include('accounts.urls', namespace='accounts')),
    path('api/', include('clients.urls', namespace='clients')),
    path('api/', include('assessments.urls', namespace='assessments')),
    path('api/', include('notifications.urls', namespace='notifications')),
    path('api/health/', include('status.urls', namespace='status')),
]
