from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only view of the audit trail.

    The trail is evidence, so it is never editable: no add, change or delete,
    here or anywhere else in the application.
    """

    list_display = (
        "created_at",
        "user_email",
        "action",
        "resource_type",
        "resource_id",
        "ip_address",
    )
    list_filter = ("action", "resource_type", "created_at")
    search_fields = ("user_email", "resource_id")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = tuple(field.name for field in AuditLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
