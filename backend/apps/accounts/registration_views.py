"""Email sign-up + confirmation (home-lab auth path, PRD 20 / Epic 1).

All endpoints are gated by ``settings.AUTH_EMAIL_ENABLED`` and per-IP throttled.
Accounts are created ``is_active=False`` and only activate once the emailed
token is confirmed — confirm-before-login. CSRF is enforced (the SPA always
holds a csrftoken) to match the other unauthenticated auth endpoints.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .emails import send_confirmation_email
from .models import ANON_EMAIL_DOMAIN, EmailConfirmation

User = get_user_model()


class EmailAuthThrottle(SimpleRateThrottle):
    """Per-IP throttle for email sign-up / confirm / resend (scope in settings
    DEFAULT_THROTTLE_RATES). Unauthenticated, so key on the client IP."""

    scope = "email_auth"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


_DISABLED = Response(
    {"detail": "Email sign-up is not enabled on this deployment."},
    status=status.HTTP_403_FORBIDDEN,
)


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    """POST /api/register/ {email, password} — create an unconfirmed account
    and email a confirmation link. Never logs the caller in."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [EmailAuthThrottle]

    def post(self, request):
        if not settings.AUTH_EMAIL_ENABLED:
            return Response(_DISABLED.data, status=_DISABLED.status_code)

        data = request.data if isinstance(request.data, dict) else {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        try:
            validate_email(email)
        except DjangoValidationError:
            return Response(
                {"detail": "Enter a valid email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if email.endswith(f"@{ANON_EMAIL_DOMAIN}"):
            return Response(
                {"detail": "That email domain isn't allowed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            return Response(
                {"detail": " ".join(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {"detail": "An account with that email already exists. Try signing in."},
                status=status.HTTP_409_CONFLICT,
            )

        user = User.objects.create_user(
            email=email,
            password=password,
            account_type=User.AccountType.EMAIL,
            is_active=False,
        )
        confirmation = EmailConfirmation.objects.create(user=user)
        send_confirmation_email(user, confirmation)
        return Response(
            {
                "detail": "Account created. Check your email to confirm your address.",
                "email": email,
            },
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_protect, name="dispatch")
class ConfirmEmailView(APIView):
    """POST /api/auth/confirm/ {token} — activate the account behind a valid,
    unexpired token. Idempotent-ish: re-confirming an already-active account
    with a still-valid token just succeeds again."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [EmailAuthThrottle]

    INVALID = {"detail": "This confirmation link is invalid or has expired."}

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        token = (data.get("token") or "").strip()
        if not token:
            return Response(
                {"detail": "Missing confirmation token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        confirmation = (
            EmailConfirmation.objects.select_related("user")
            .filter(token=token)
            .first()
        )
        if confirmation is None or not confirmation.is_valid():
            return Response(self.INVALID, status=status.HTTP_400_BAD_REQUEST)

        user = confirmation.user
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        confirmation.confirmed_at = timezone.now()
        confirmation.save(update_fields=["confirmed_at"])
        return Response({"detail": "Email confirmed. You can now sign in."})


@method_decorator(csrf_protect, name="dispatch")
class ResendConfirmationView(APIView):
    """POST /api/auth/confirm/resend/ {email} — issue a fresh confirmation
    token for a pending account. Always returns the same generic response so
    the endpoint can't be used to probe which emails exist / are pending."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [EmailAuthThrottle]

    GENERIC = {"detail": "If that account still needs confirming, a new link is on its way."}

    def post(self, request):
        if not settings.AUTH_EMAIL_ENABLED:
            return Response(_DISABLED.data, status=_DISABLED.status_code)

        data = request.data if isinstance(request.data, dict) else {}
        email = (data.get("email") or "").strip().lower()
        user = User.objects.filter(
            email__iexact=email,
            account_type=User.AccountType.EMAIL,
            is_active=False,
        ).first()
        if user is not None:
            confirmation = EmailConfirmation.objects.create(user=user)
            send_confirmation_email(user, confirmation)
        return Response(self.GENERIC)
