from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminOrReadOnly(BasePermission):
    """
    Allow read-only access to authenticated users, write access to staff/admins.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_staff or request.user.is_superuser


class IsBundleOwnerOrAdmin(BasePermission):
    """Every clinician may use a bundle; only its author or an admin may change it.

    Bundles are shared across the practice, so without this one clinician could
    rename or delete a battery another clinician relies on.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if user.is_staff or user.is_superuser:
            return True
        return obj.created_by_id is not None and obj.created_by_id == user.id

