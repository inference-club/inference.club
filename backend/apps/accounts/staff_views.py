"""Staff-only management surface for anonymous access (PRD 08):
passcodes, guest accounts, and the live access policy.

Mounted under /api/admin/ next to the moderation endpoints.
"""

from django.utils.dateparse import parse_datetime

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsStaff

from .handles import normalize_access_code
from .models import AccessCode, AccessPolicy, CustomUser
from .services import create_access_code, revoke_anonymous_user


class AccessCodeSerializer(serializers.ModelSerializer):
    handle = serializers.CharField(source="user.handle", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    user_is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    request_count = serializers.SerializerMethodField()

    class Meta:
        model = AccessCode
        fields = (
            "id",
            "code",
            "label",
            "handle",
            "user_id",
            "user_is_active",
            "is_active",
            "expires_at",
            "created_at",
            "last_used_at",
            "use_count",
            "request_count",
        )

    def get_request_count(self, obj) -> int:
        if hasattr(obj, "request_count"):
            return obj.request_count
        return obj.user.inference_requests.count()


class AccessPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessPolicy
        fields = (
            "guest_signin_enabled",
            "passcode_signin_enabled",
            "max_active_guests",
            "guest_creation_rate",
            "passcode_attempt_rate",
            "anon_inference_rate",
            "anon_models_rate",
            "guest_message",
        )

    def _validate_rate(self, value):
        # DRF rate strings: "<num>/<period>" with period in s/m/h/d (or the
        # long forms "sec", "min", "hour", "day").
        try:
            num, period = value.split("/")
            assert int(num) > 0
            assert period[0] in ("s", "m", "h", "d")
        except (ValueError, AssertionError, IndexError):
            raise serializers.ValidationError(
                'Must be a rate like "15/min", "5/hour" or "100/day".'
            )
        return value

    validate_guest_creation_rate = _validate_rate
    validate_passcode_attempt_rate = _validate_rate
    validate_anon_inference_rate = _validate_rate
    validate_anon_models_rate = _validate_rate


class GuestAccountSerializer(serializers.ModelSerializer):
    request_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "handle",
            "is_active",
            "date_joined",
            "last_login",
            "request_count",
        )

    def get_request_count(self, obj) -> int:
        if hasattr(obj, "request_count"):
            return obj.request_count
        return obj.inference_requests.count()


def _codes_qs():
    from django.db.models import Count

    return (
        AccessCode.objects.select_related("user")
        .annotate(request_count=Count("user__inference_requests"))
        .order_by("-created_at")
    )


class AdminAccessCodeListView(APIView):
    """GET = list all passcodes; POST = mint a code + its account."""

    permission_classes = [IsStaff]

    def get(self, request):
        return Response(
            {"codes": AccessCodeSerializer(_codes_qs(), many=True).data}
        )

    def post(self, request):
        label = str(request.data.get("label") or "").strip()
        raw_code = str(request.data.get("code") or "").strip()
        if raw_code:
            normalized = normalize_access_code(raw_code)
            if len(normalized) > 40:
                return Response(
                    {"detail": "Passcode is too long (max 40 characters)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if AccessCode.objects.filter(code=normalized).exists():
                return Response(
                    {"detail": f'Code "{normalized}" is already in use.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        expires_at = None
        raw_expiry = request.data.get("expires_at")
        if raw_expiry:
            expires_at = parse_datetime(str(raw_expiry))
            if expires_at is None:
                return Response(
                    {"detail": "expires_at must be an ISO-8601 datetime."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        code = create_access_code(
            request.user, label=label, code=raw_code or None, expires_at=expires_at
        )
        return Response(
            AccessCodeSerializer(code).data, status=status.HTTP_201_CREATED
        )


class AdminAccessCodeDetailView(APIView):
    """PATCH = edit label/expiry, revoke (is_active=false kills sessions) or
    reactivate; DELETE = revoke the code AND lock its account."""

    permission_classes = [IsStaff]

    def _get(self, id):
        return _codes_qs().filter(id=id).first()

    def patch(self, request, id):
        code = self._get(id)
        if code is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if "label" in request.data:
            code.label = str(request.data["label"] or "").strip()
        if "expires_at" in request.data:
            raw = request.data["expires_at"]
            code.expires_at = parse_datetime(str(raw)) if raw else None
        if "is_active" in request.data:
            want_active = bool(request.data["is_active"])
            if code.is_active and not want_active:
                code.user.bump_session_epoch()  # revoke = boot live sessions
            if want_active and not code.user.is_active:
                # Reactivating a code unlocks its account too.
                code.user.is_active = True
                code.user.save(update_fields=["is_active"])
            code.is_active = want_active
        code.save()
        return Response(AccessCodeSerializer(self._get(id)).data)

    def delete(self, request, id):
        code = self._get(id)
        if code is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        code.is_active = False
        code.save(update_fields=["is_active"])
        revoke_anonymous_user(code.user)
        return Response(AccessCodeSerializer(self._get(id)).data)


class AdminGuestListView(APIView):
    """GET /api/admin/guests/ — guest accounts with light activity stats."""

    permission_classes = [IsStaff]

    def get(self, request):
        from django.db.models import Count

        qs = (
            CustomUser.objects.filter(account_type=CustomUser.AccountType.GUEST)
            .annotate(request_count=Count("inference_requests"))
            .order_by("-date_joined")
        )
        return Response({"guests": GuestAccountSerializer(qs, many=True).data})


class AdminGuestRevokeView(APIView):
    """POST /api/admin/guests/<id>/revoke/ — lock the account + kill sessions."""

    permission_classes = [IsStaff]

    def post(self, request, id):
        user = CustomUser.objects.filter(
            id=id, account_type=CustomUser.AccountType.GUEST
        ).first()
        if user is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        revoke_anonymous_user(user)
        return Response(GuestAccountSerializer(user).data)


class AdminGuestPurgeView(APIView):
    """POST /api/admin/guests/<id>/purge/ — delete the account and all its
    content (cascade). Destructive; the UI confirm-gates it."""

    permission_classes = [IsStaff]

    def post(self, request, id):
        user = CustomUser.objects.filter(
            id=id, account_type=CustomUser.AccountType.GUEST
        ).first()
        if user is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        user.bump_session_epoch()
        # The request FK is SET_NULL — delete content explicitly so a purge
        # doesn't leave ownerless rows behind.
        user.inference_requests.all().delete()
        user.delete()
        return Response({"detail": "guest account purged"})


class AdminAccessPolicyView(APIView):
    """GET/PATCH /api/admin/access-policy/ — the real-time rollout knobs."""

    permission_classes = [IsStaff]

    def get(self, request):
        return Response(AccessPolicySerializer(AccessPolicy.load()).data)

    def patch(self, request):
        policy, _ = AccessPolicy.objects.get_or_create(pk=AccessPolicy._SINGLETON_PK)
        ser = AccessPolicySerializer(policy, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()  # save() busts the cache
        return Response(ser.data)
