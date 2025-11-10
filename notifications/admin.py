from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "recipient", "title", "event_type", "created_at", "read_at")
    list_filter = ("event_type", "created_at", "read_at")
    search_fields = ("title", "body", "recipient__email")
    autocomplete_fields = ("recipient",)
    ordering = ("-created_at",)
