from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Who did what, to which record, and when.

    Identifiers only. This table must never hold patient data: no names, email
    addresses, dates of birth, informant details or assessment answers, and no
    request bodies. ``user`` and ``user_email`` describe the acting clinician,
    not the client.
    """

    class Action(models.TextChoices):
        VIEW = "VIEW", "View"
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"
        EXPORT = "EXPORT", "Export"
        SUBMIT = "SUBMIT", "Submit"

    class ResourceType(models.TextChoices):
        CLIENT = "client", "Client"
        CLIENT_GROUP = "client_group", "Client group"
        ASSESSMENT_RESPONSE = "assessment_response", "Assessment response"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="audit_logs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Acting user. Null for unauthenticated respondent actions.",
    )
    user_email = models.CharField(
        max_length=254,
        blank=True,
        help_text="Snapshot of the acting user's email, so the trail survives account deletion.",
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    resource_type = models.CharField(max_length=32, choices=ResourceType.choices)
    resource_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="Primary key of the affected record. Identifier only.",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = (
            models.Index(fields=("resource_type", "resource_id")),
            models.Index(fields=("user", "created_at")),
        )

    def __str__(self) -> str:  # pragma: no cover - display helper
        actor = self.user_email or "anonymous"
        return f"{actor} {self.action} {self.resource_type}:{self.resource_id or '-'}"
