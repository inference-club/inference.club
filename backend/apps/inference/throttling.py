"""Throttling for anonymous accounts (PRD 08).

Guest/passcode accounts share the OpenAI-compatible surface with full members
but under tighter, admin-configurable limits: scope ``inference`` becomes
``inference_anon`` (separate cache bucket) with its rate read live from the
AccessPolicy singleton. Full members are untouched — this subclass behaves
exactly like ScopedRateThrottle for them.
"""

from rest_framework.throttling import ScopedRateThrottle

# AccessPolicy field per base scope.
_POLICY_FIELDS = {
    "inference": "anon_inference_rate",
    "models": "anon_models_rate",
}


def _valid_rate(rate) -> bool:
    try:
        num, period = rate.split("/")
        return int(num) > 0 and period[:1] in ("s", "m", "h", "d")
    except (ValueError, AttributeError, IndexError):
        return False


def anon_scope_rate(base_scope: str) -> str | None:
    """The live anonymous-account rate for a base scope: the AccessPolicy
    value when valid, else the ``<scope>_anon`` settings default."""
    from rest_framework.settings import api_settings

    fallback = api_settings.DEFAULT_THROTTLE_RATES.get(f"{base_scope}_anon")
    field = _POLICY_FIELDS.get(base_scope)
    if not field:
        return fallback
    try:
        from apps.accounts.models import AccessPolicy

        rate = getattr(AccessPolicy.load(), field, "") or ""
    except Exception:
        return fallback
    return rate if _valid_rate(rate) else fallback


def is_anon_account(user) -> bool:
    return bool(user is not None and getattr(user, "is_anonymous_account", False))


class AccountTypeScopedRateThrottle(ScopedRateThrottle):
    """ScopedRateThrottle that swaps anonymous accounts onto the tighter
    ``<scope>_anon`` bucket/rate."""

    def allow_request(self, request, view):
        self._anon_account = is_anon_account(getattr(request, "user", None))
        return super().allow_request(request, view)

    def get_rate(self):
        if getattr(self, "_anon_account", False):
            base = self.scope
            # Mutating self.scope also segregates the throttle cache key.
            self.scope = f"{base}_anon"
            rate = anon_scope_rate(base)
            if rate:
                return rate
        return super().get_rate()
