from rest_framework import permissions


class HasClientAccess(permissions.BasePermission):
    """Ensures requests act only on the authenticated user's clients."""

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id
