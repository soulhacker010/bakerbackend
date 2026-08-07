"""Viewset mixin that records access to protected records."""
from __future__ import annotations

from .models import AuditLog
from .services import record_audit

# The lifecycle actions a viewset records by default.
ALL_ACTIONS = (
    AuditLog.Action.VIEW,
    AuditLog.Action.CREATE,
    AuditLog.Action.UPDATE,
    AuditLog.Action.DELETE,
)


class AuditLogMixin:
    """Log retrieve, create, update and delete against ``audit_resource_type``.

    Hooks the DRF action methods rather than ``perform_create``/``perform_update``/
    ``perform_destroy``, because viewsets in this project override those to carry
    their own ownership checks and a mixin would be shadowed by them.

    Only successful requests are recorded: a permission or lookup failure raises
    inside ``super()`` before the entry is written.

    Entries carry the record's primary key, never its slug. Client slugs are
    generated from the client's name, so logging one would put patient data in
    the trail.
    """

    audit_resource_type: str = ""
    audit_actions: tuple[str, ...] = ALL_ACTIONS

    def get_object(self):
        instance = super().get_object()
        # Captured now, as a string: Django clears the primary key on delete, so
        # reading it after super().destroy() would record "None".
        self._audited_resource_id = str(instance.pk)
        return instance

    def _audited_identifier(self) -> str:
        return getattr(self, "_audited_resource_id", "")

    def record_audit_entry(self, action: str, resource_id: str = "") -> None:
        if action not in self.audit_actions:
            return
        record_audit(
            self.request,
            action=action,
            resource_type=self.audit_resource_type,
            resource_id=resource_id,
        )

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        self.record_audit_entry(AuditLog.Action.VIEW, self._audited_identifier())
        return response

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        identifier = ""
        if isinstance(getattr(response, "data", None), dict):
            identifier = str(response.data.get("id") or "")
        self.record_audit_entry(AuditLog.Action.CREATE, identifier)
        return response

    def update(self, request, *args, **kwargs):
        # DRF routes PATCH through update() with partial=True, so this covers both.
        response = super().update(request, *args, **kwargs)
        self.record_audit_entry(AuditLog.Action.UPDATE, self._audited_identifier())
        return response

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        self.record_audit_entry(AuditLog.Action.DELETE, self._audited_identifier())
        return response
