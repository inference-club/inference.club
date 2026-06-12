from rest_framework.permissions import BasePermission


class IsFullMember(BasePermission):
    """Allow access only to authenticated *full* members — i.e. not guest or
    passcode accounts (``user.is_anonymous_account``).

    Gates the capabilities anonymous accounts must never reach: API tokens,
    compute/agent registration, and provider management. See
    docs/prd/08-anonymous-access.md.
    """

    message = "Not available for guest or passcode accounts. Sign in with GitHub to use this."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and not getattr(user, "is_anonymous_account", False)
        )


class IsStaff(BasePermission):
    """Allow access only to authenticated staff users (``is_staff``).

    Used to gate the in-app admin surface (activity dashboard + content
    moderation). Superusers have ``is_staff`` too, so they pass as well.
    """

    message = "Staff access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)
