from rest_framework.permissions import BasePermission


class IsStaff(BasePermission):
    """Allow access only to authenticated staff users (``is_staff``).

    Used to gate the in-app admin surface (activity dashboard + content
    moderation). Superusers have ``is_staff`` too, so they pass as well.
    """

    message = "Staff access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)
