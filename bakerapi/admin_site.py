"""Custom Django admin site enforcing MFA and tightening access."""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import logout
from django.utils.translation import gettext_lazy as _


class BakerAdminAuthenticationForm(AdminAuthenticationForm):
    """Admin login form that blocks accounts without two-factor enabled."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not getattr(user, "two_factor_enabled", False):
            raise forms.ValidationError(
                _("Two-factor authentication must be enabled to access the admin."),
                code="two_factor_required",
            )


class BakerAdminSite(admin.AdminSite):
    site_header = "Baker Street Administration"
    site_title = "Baker Street Admin"
    index_title = "Administration"
    login_form = BakerAdminAuthenticationForm

    def has_permission(self, request):
        has_permission = super().has_permission(request)
        if not has_permission:
            return False

        user = request.user
        if getattr(user, "two_factor_enabled", False):
            return True

        logout(request)
        messages.error(
            request,
            _("Enable two-factor authentication on your account to access the admin."),
        )
        return False


previous_admin_site = admin.site
admin_site = BakerAdminSite(name="admin")

# Re-register any ModelAdmin classes already bound to the default site.
for model, model_admin in previous_admin_site._registry.items():
    admin_site.register(model, model_admin.__class__)

# Ensure default registration decorators target the hardened site going forward.
admin.site = admin_site
