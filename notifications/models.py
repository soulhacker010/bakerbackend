from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    class EventType(models.TextChoices):
        GENERIC = "generic", "Generic"
        CLIENT_CREATED = "client.created", "Client created"
        ASSESSMENT_COMPLETED = "assessment.completed", "Assessment completed"
        SCHEDULE_SENT = "schedule.sent", "Schedule sent"

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    read_at = models.DateTimeField(blank=True, null=True)

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="notifications",
        on_delete=models.CASCADE,
    )
    event_type = models.CharField(max_length=64, choices=EventType.choices)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    payload = models.JSONField(blank=True, default=dict, help_text="Arbitrary structured data for client use.")

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("recipient", "read_at"), name="notification_read_idx"),
            models.Index(fields=("recipient", "created_at"), name="notification_created_idx"),
        ]

    def __str__(self) -> str:
        return f"Notification #{self.pk} → {self.recipient}: {self.title}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self) -> None:
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=("read_at", "updated_at"))
