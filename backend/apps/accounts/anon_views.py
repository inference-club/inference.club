"""Anonymous sign-in endpoints: auth options, guest creation, passcode login.

All AllowAny + per-IP throttled, with rates read live from the admin-editable
AccessPolicy. Login CSRF is enforced (the SPA always holds a csrftoken via
/api/login-set-cookie/) so an attacker can't silently log a victim into an
attacker-controlled anonymous account.
"""

import secrets

from django.contrib.auth import login
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .handles import normalize_access_code
from .models import AccessCode, AccessPolicy, CustomUser
from .serializers import UserSerializer
from .services import create_anonymous_user

# Anonymous users authenticate by session only; pin the backend since several
# AUTHENTICATION_BACKENDS are configured.
_MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"


class _PolicyIPThrottle(SimpleRateThrottle):
    """Per-IP throttle whose rate is an AccessPolicy field (live-editable)."""

    policy_field = ""  # subclasses set
    fallback_rate = "5/hour"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }

    def get_rate(self):
        try:
            rate = getattr(AccessPolicy.load(), self.policy_field, "") or ""
            self.parse_rate(rate)  # validate; falls through on bad strings
            return rate
        except Exception:
            return self.fallback_rate


class GuestCreationThrottle(_PolicyIPThrottle):
    scope = "guest_create"
    policy_field = "guest_creation_rate"
    fallback_rate = "5/hour"


class PasscodeAttemptThrottle(_PolicyIPThrottle):
    scope = "passcode_attempt"
    policy_field = "passcode_attempt_rate"
    fallback_rate = "10/hour"


class AuthOptionsView(APIView):
    """GET /api/auth/options/ — which sign-in methods are live right now.
    Drives the login page so enabling/disabling pathways needs no deploy."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        policy = AccessPolicy.load()
        return Response(
            {
                "github": True,
                "guest": policy.guest_signin_enabled,
                "passcode": policy.passcode_signin_enabled,
                "guest_message": policy.guest_message,
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class GuestLoginView(APIView):
    """POST /api/auth/guest/ — create a guest account and log it in."""

    permission_classes = [AllowAny]
    throttle_classes = [GuestCreationThrottle]

    def post(self, request):
        policy = AccessPolicy.load()
        if not policy.guest_signin_enabled:
            return Response(
                {"detail": "Guest sign-in is currently disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if policy.max_active_guests:
            active = CustomUser.objects.filter(
                account_type=CustomUser.AccountType.GUEST, is_active=True
            ).count()
            if active >= policy.max_active_guests:
                return Response(
                    {"detail": "Guest access is full right now — try again later."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        user = create_anonymous_user(CustomUser.AccountType.GUEST)
        login(request, user, backend=_MODEL_BACKEND)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class PasscodeLoginView(APIView):
    """POST /api/auth/passcode/ {code} — log into the code's bound account.

    Uniform error whatever the failure (unknown / revoked / expired / locked)
    so codes can't be probed for state.
    """

    permission_classes = [AllowAny]
    throttle_classes = [PasscodeAttemptThrottle]

    INVALID = {"detail": "Invalid or revoked passcode."}

    def post(self, request):
        policy = AccessPolicy.load()
        if not policy.passcode_signin_enabled:
            return Response(
                {"detail": "Passcode sign-in is currently disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        raw = request.data.get("code") if isinstance(request.data, dict) else ""
        typed = str(raw or "").strip()
        access_code = (
            AccessCode.objects.select_related("user")
            .filter(code__in=_constant_time_candidates(typed))
            .first()
        )
        if access_code is None or not access_code.is_redeemable():
            return Response(self.INVALID, status=status.HTTP_403_FORBIDDEN)

        access_code.use_count += 1
        access_code.last_used_at = timezone.now()
        access_code.save(update_fields=["use_count", "last_used_at"])
        login(request, access_code.user, backend=_MODEL_BACKEND)
        return Response(UserSerializer(access_code.user).data)


def _constant_time_candidates(typed: str) -> list[str]:
    """Resolve the typed code against stored codes with constant-time
    comparison (codes are few; a linear scan is cheap and avoids leaking
    prefix-match timing through the DB index).

    Admin-chosen codes are matched verbatim — what they typed is what
    redeems. The generated ``club-XXXX`` codes additionally match their
    normalized (case- and prefix-tolerant) form so they survive being read
    aloud or retyped.
    """
    candidates = {typed, normalize_access_code(typed)}
    return [
        stored
        for stored in AccessCode.objects.values_list("code", flat=True)
        if any(secrets.compare_digest(stored, c) for c in candidates)
    ]
