"""Anonymous access (PRD 08): guests, passcodes, alias mode, gating.

Covers the full surface: guest creation (policy gates, cap), passcode login
(valid/revoked/expired/unknown), session-epoch revocation, token-mint gating,
IsFullMember on the dangerous endpoints, visibility clamps, the
PRIVATE-tier-as-public rule, handle generation, alias mode round-trips, and
the GitHub-upgrade pipeline step.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from social_django.models import UserSocialAuth

from apps.accounts.handles import (
    generate_access_code,
    normalize_access_code,
    random_handle,
)
from apps.accounts.models import AccessCode, AccessPolicy, ANON_EMAIL_DOMAIN
from apps.accounts.pipeline import finalize_anonymous_upgrade
from apps.accounts.serializers import UserSerializer
from apps.accounts.services import (
    create_access_code,
    create_anonymous_user,
    regenerate_alias,
    set_alias_mode,
)
from apps.inference.models import (
    InferenceRequest,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    VISIBILITY_UNLISTED,
    visible_list_q,
)

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def policy(db):
    p, _ = AccessPolicy.objects.get_or_create(pk=AccessPolicy._SINGLETON_PK)
    return p


@pytest.fixture
def staff(db):
    return User.objects.create_user(
        email="staff@example.com", password="pw", is_staff=True, handle="staffer"
    )


@pytest.fixture
def github_user(db):
    u = User.objects.create_user(
        email="alice@example.com", password="pw", handle="alice"
    )
    UserSocialAuth.objects.create(
        user=u, provider="github", uid="1", extra_data={"login": "alice"}
    )
    return u


@pytest.fixture
def guest(db):
    return create_anonymous_user(User.AccountType.GUEST)


def enable_guests(policy, **kw):
    policy.guest_signin_enabled = True
    for k, v in kw.items():
        setattr(policy, k, v)
    policy.save()


def make_request(user, visibility=""):
    return InferenceRequest.objects.create(
        user=user,
        inference_type="LLM",
        payload={"messages": []},
        visibility=visibility,
    )


# --- handles ---------------------------------------------------------------


def test_random_handle_is_three_clean_words():
    for _ in range(50):
        h = random_handle()
        assert len(h.split("-")) == 3
        assert h == h.lower()


def test_access_code_format_and_normalize():
    code = generate_access_code()
    assert code.startswith("club-")
    assert len(code) == len("club-XXXX-XXXX-XXXX")
    # Tolerant of how a friend might re-type it.
    assert normalize_access_code(" club-ab2d-EF3G-h4jk ") == "club-AB2D-EF3G-H4JK"
    assert normalize_access_code("AB2D-EF3G-H4JK") == "club-AB2D-EF3G-H4JK"


# --- guest sign-in ----------------------------------------------------------


def test_guest_disabled_by_default(api_client, policy):
    r = api_client.post("/api/auth/guest/")
    assert r.status_code == 403


def test_guest_creation_and_shape(api_client, policy):
    enable_guests(policy)
    r = api_client.post("/api/auth/guest/")
    assert r.status_code == 201
    assert r.data["account_type"] == "GUEST"
    assert r.data["is_anonymous_account"] is True
    assert r.data["api_token"] is None
    assert len(r.data["handle"].split("-")) >= 3
    assert r.data["email"].endswith("@" + ANON_EMAIL_DOMAIN)
    # And the session is live:
    me = api_client.get("/api/account/")
    assert me.status_code == 200
    assert me.data["handle"] == r.data["handle"]


def test_guest_cap(api_client, policy):
    enable_guests(policy, max_active_guests=1)
    assert api_client.post("/api/auth/guest/").status_code == 201
    r = APIClient().post("/api/auth/guest/")
    assert r.status_code == 403
    assert "full" in r.data["detail"]


def test_auth_options_reflect_policy(api_client, policy):
    r = api_client.get("/api/auth/options/")
    assert r.data == {
        "github": True,
        "guest": False,
        "passcode": True,
        "guest_message": "",
    }
    enable_guests(policy, guest_message="demo weekend")
    r = api_client.get("/api/auth/options/")
    assert r.data["guest"] is True
    assert r.data["guest_message"] == "demo weekend"


# --- passcodes ---------------------------------------------------------------


def test_passcode_login_happy_path(api_client, policy, staff):
    code = create_access_code(staff, label="for max")
    r = api_client.post("/api/auth/passcode/", {"code": code.code}, format="json")
    assert r.status_code == 200
    assert r.data["account_type"] == "PASSCODE"
    assert r.data["handle"] == code.user.handle
    code.refresh_from_db()
    assert code.use_count == 1
    assert code.last_used_at is not None
    # Same code, new client → same account (one code = one account).
    other = APIClient()
    r2 = other.post(
        "/api/auth/passcode/", {"code": code.code.lower()}, format="json"
    )
    assert r2.status_code == 200
    assert r2.data["handle"] == r.data["handle"]


@pytest.mark.django_db
def test_passcode_rejections_are_uniform(api_client, policy, staff):
    revoked = create_access_code(staff)
    revoked.is_active = False
    revoked.save()
    expired = create_access_code(staff)
    expired.expires_at = timezone.now() - timedelta(hours=1)
    expired.save()
    locked = create_access_code(staff)
    locked.user.is_active = False
    locked.user.save()

    expected = {"detail": "Invalid or revoked passcode."}
    for bad in (revoked.code, expired.code, locked.code, "club-NOPE-NOPE-NOPE", ""):
        r = api_client.post("/api/auth/passcode/", {"code": bad}, format="json")
        assert r.status_code == 403
        assert r.data == expected


def test_passcode_signin_can_be_disabled(api_client, policy, staff):
    code = create_access_code(staff)
    policy.passcode_signin_enabled = False
    policy.save()
    r = api_client.post("/api/auth/passcode/", {"code": code.code}, format="json")
    assert r.status_code == 403


# --- session-epoch revocation ------------------------------------------------


def test_epoch_bump_kills_live_session(api_client, policy, staff):
    code = create_access_code(staff)
    api_client.post("/api/auth/passcode/", {"code": code.code}, format="json")
    assert api_client.get("/api/account/").status_code == 200
    code.user.bump_session_epoch()
    assert api_client.get("/api/account/").status_code in (401, 403)


# --- token + capability gating ------------------------------------------------


def test_no_token_minted_for_anonymous_accounts(guest):
    assert not Token.objects.filter(user=guest).exists()
    assert UserSerializer(guest).data["api_token"] is None
    assert not Token.objects.filter(user=guest).exists()  # serializer didn't backfill


def test_token_endpoints_denied(api_client, guest):
    api_client.force_authenticate(guest)
    assert api_client.post("/api/token/").status_code == 403
    assert api_client.get("/api/token/list/").status_code == 403
    assert api_client.delete("/api/token/").status_code == 403


def test_agent_register_denied(api_client, guest, github_user):
    api_client.force_authenticate(guest)
    r = api_client.post(
        "/api/inference/agent/register/", {"name": "host"}, format="json"
    )
    assert r.status_code == 403
    # Full members still pass the permission gate.
    api_client.force_authenticate(github_user)
    r = api_client.post("/api/inference/agent/register/", {}, format="json")
    assert r.status_code != 403


def test_anonymous_accounts_cannot_become_staff(guest):
    guest.is_staff = True
    with pytest.raises(Exception):
        guest.full_clean()


# --- visibility ---------------------------------------------------------------


def test_visibility_clamped_on_create(guest):
    guest.default_request_visibility = "PUBLIC"  # however it got set
    guest.save()
    ir = make_request(guest)
    assert ir.visibility == VISIBILITY_UNLISTED
    ir2 = make_request(guest, visibility="PUBLIC")
    assert ir2.visibility == VISIBILITY_UNLISTED


def test_visibility_patch_to_public_rejected(api_client, guest):
    ir = make_request(guest)
    api_client.force_authenticate(guest)
    r = api_client.patch(
        f"/api/inference/requests/{ir.id}/", {"visibility": "PUBLIC"}, format="json"
    )
    assert r.status_code == 400
    r = api_client.patch(
        f"/api/inference/requests/{ir.id}/", {"visibility": "SECRET"}, format="json"
    )
    assert r.status_code == 200


def test_account_default_visibility_public_rejected(api_client, guest):
    api_client.force_authenticate(guest)
    r = api_client.patch(
        "/api/account/", {"default_request_visibility": "PUBLIC"}, format="json"
    )
    assert r.status_code == 400


def test_private_tier_excludes_anonymous_viewers(guest, github_user):
    private = make_request(github_user, visibility=VISIBILITY_PRIVATE)
    public = make_request(github_user, visibility=VISIBILITY_PUBLIC)
    assert private.is_visible_to(github_user) is True
    assert private.is_visible_to(guest) is False
    assert public.is_visible_to(guest) is True
    listed = set(
        InferenceRequest.objects.filter(visible_list_q(guest)).values_list(
            "id", flat=True
        )
    )
    assert public.id in listed and private.id not in listed
    # Their own content still lists for them.
    mine = make_request(guest)
    listed = set(
        InferenceRequest.objects.filter(visible_list_q(guest)).values_list(
            "id", flat=True
        )
    )
    assert mine.id in listed


# --- public profiles -----------------------------------------------------------


def test_anonymous_profile_shows_unlisted_consumed(api_client, guest, github_user):
    unlisted = make_request(guest)  # UNLISTED by default
    assert unlisted.visibility == VISIBILITY_UNLISTED
    r = api_client.get(reverse("public-user-requests", args=[guest.handle]))
    assert {row["id"] for row in r.data["results"]} == {unlisted.id}
    # GitHub users' profiles still never list UNLISTED.
    u2 = make_request(github_user, visibility=VISIBILITY_UNLISTED)
    r = api_client.get(reverse("public-user-requests", args=["alice"]))
    assert u2.id not in {row["id"] for row in r.data["results"]}


def test_anonymous_profile_payload(api_client, guest):
    r = api_client.get(reverse("public-user-profile", args=[guest.handle]))
    assert r.status_code == 200
    assert r.data["handle"] == guest.handle
    assert r.data["account_badge"] == "anonymous"
    assert r.data["avatar_url"] == ""
    assert r.data["github_url"] == ""


def test_github_profile_payload(api_client, github_user):
    sa = github_user.social_auth.get()
    sa.extra_data.update({"avatar_url": "https://avatars.example/1", "name": "Alice"})
    sa.save()
    r = api_client.get(reverse("public-user-profile", args=["alice"]))
    assert r.data["account_badge"] == "github"
    assert r.data["avatar_url"] == "https://avatars.example/1"
    assert r.data["github_url"] == "https://github.com/alice"


# --- alias mode -----------------------------------------------------------------


def test_alias_round_trip(api_client, github_user):
    set_alias_mode(github_user, True)
    alias = github_user.handle
    assert alias == github_user.anon_alias and alias != "alice"

    # Old URL 404s; alias URL serves, with no GitHub identity in it.
    assert (
        api_client.get(reverse("public-user-profile", args=["alice"])).status_code
        == 404
    )
    r = api_client.get(reverse("public-user-profile", args=[alias]))
    assert r.status_code == 200
    assert r.data["account_badge"] == "github"  # provenance badge stays
    assert r.data["avatar_url"] == "" and r.data["github_url"] == ""
    assert "alice" not in str(r.data)

    # Toggle back restores the GitHub handle; alias is kept for next time.
    set_alias_mode(github_user, False)
    assert github_user.handle == "alice"
    assert github_user.anon_alias == alias
    set_alias_mode(github_user, True)
    assert github_user.handle == alias  # stable across toggles


def test_alias_toggle_via_account_patch(api_client, github_user):
    api_client.force_authenticate(github_user)
    r = api_client.patch("/api/account/", {"use_anon_alias": True}, format="json")
    assert r.status_code == 200
    assert r.data["use_anon_alias"] is True
    assert r.data["handle"] == r.data["anon_alias"]
    # github_login (own private view) still shows the real login.
    assert r.data["github_login"] == "alice"


def test_alias_toggle_rejected_for_anonymous_accounts(api_client, guest):
    api_client.force_authenticate(guest)
    r = api_client.patch("/api/account/", {"use_anon_alias": False}, format="json")
    assert r.status_code == 400


def test_alias_regenerate_cooldown(api_client, github_user, guest):
    set_alias_mode(github_user, True)
    first = github_user.anon_alias
    api_client.force_authenticate(github_user)
    r = api_client.post("/api/account/alias/regenerate/")
    assert r.status_code == 200
    github_user.refresh_from_db()
    assert github_user.anon_alias != first
    # Second regenerate inside the window → 429.
    assert api_client.post("/api/account/alias/regenerate/").status_code == 429
    # Anonymous accounts can't regenerate (their handle is their share link).
    api_client.force_authenticate(guest)
    assert api_client.post("/api/account/alias/regenerate/").status_code == 403


# --- attribution uses the handle -------------------------------------------------


def test_attribution_emits_handle_not_github_login(api_client, github_user):
    set_alias_mode(github_user, True)
    ir = make_request(github_user, visibility=VISIBILITY_PUBLIC)
    api_client.force_authenticate(github_user)
    r = api_client.get(f"/api/inference/requests/{ir.id}/")
    assert r.data["github_login"] == github_user.handle
    assert r.data["owner"] == github_user.handle


# --- upgrade ("Keep this account") ------------------------------------------------


@pytest.mark.django_db
def test_upgrade_flips_account_and_kills_code(staff):
    code = create_access_code(staff, label="for max")
    user = code.user
    old_handle = user.handle
    finalize_anonymous_upgrade(
        strategy=None,
        details={"email": "max@example.com", "username": "maxgh"},
        backend=None,
        user=user,
    )
    user.refresh_from_db()
    assert user.account_type == User.AccountType.GITHUB
    assert user.is_anonymous_account is False
    assert user.use_anon_alias is True  # upgrading must not deanonymize
    assert user.handle == old_handle
    assert user.email == "max@example.com"
    assert Token.objects.filter(user=user).exists()
    code.refresh_from_db()
    assert code.is_active is False  # no backdoor into a real account


@pytest.mark.django_db
def test_upgrade_keeps_synthetic_email_on_collision(staff, github_user):
    code = create_access_code(staff)
    user = code.user
    synthetic = user.email
    finalize_anonymous_upgrade(
        strategy=None,
        details={"email": "alice@example.com"},  # taken by github_user
        backend=None,
        user=user,
    )
    user.refresh_from_db()
    assert user.account_type == User.AccountType.GITHUB
    assert user.email == synthetic


# --- staff management API -----------------------------------------------------------


def test_access_code_admin_crud(api_client, staff, policy):
    api_client.force_authenticate(staff)
    r = api_client.post(
        "/api/admin/access-codes/", {"label": "for max"}, format="json"
    )
    assert r.status_code == 201
    code_id, code_value = r.data["id"], r.data["code"]
    assert r.data["label"] == "for max"
    assert r.data["handle"]

    listed = api_client.get("/api/admin/access-codes/")
    assert any(c["id"] == code_id for c in listed.data["codes"])

    # Friend logs in; staff revokes; the friend's session dies and the code
    # stops redeeming.
    friend = APIClient()
    assert (
        friend.post("/api/auth/passcode/", {"code": code_value}, format="json")
        .status_code
        == 200
    )
    assert friend.get("/api/account/").status_code == 200
    r = api_client.patch(
        f"/api/admin/access-codes/{code_id}/", {"is_active": False}, format="json"
    )
    assert r.data["is_active"] is False
    assert friend.get("/api/account/").status_code in (401, 403)
    assert (
        friend.post("/api/auth/passcode/", {"code": code_value}, format="json")
        .status_code
        == 403
    )


def test_admin_chosen_code_is_the_login_code(api_client, staff, policy):
    """The passcode an admin types is what redeems at login, verbatim — no
    prefix, no case-folding — not a random string."""
    api_client.force_authenticate(staff)
    r = api_client.post(
        "/api/admin/access-codes/",
        {"code": "max-2026", "label": "for max"},
        format="json",
    )
    assert r.status_code == 201
    assert r.data["code"] == "max-2026"
    assert r.data["label"] == "for max"

    # The friend logs in by typing exactly what the admin chose.
    friend = APIClient()
    assert (
        friend.post("/api/auth/passcode/", {"code": "max-2026"}, format="json")
        .status_code
        == 200
    )
    # A different-cased variant is a different code and does not redeem.
    assert (
        APIClient()
        .post("/api/auth/passcode/", {"code": "MAX-2026"}, format="json")
        .status_code
        == 403
    )

    # Re-using the same code is rejected up front.
    dup = api_client.post(
        "/api/admin/access-codes/", {"code": "max-2026"}, format="json"
    )
    assert dup.status_code == 400


def test_blank_code_falls_back_to_random(api_client, staff, policy):
    api_client.force_authenticate(staff)
    r = api_client.post(
        "/api/admin/access-codes/", {"label": "for max"}, format="json"
    )
    assert r.status_code == 201
    assert r.data["code"].startswith("club-")
    assert r.data["code"] != "club-"


def test_guest_admin_revoke_and_purge(api_client, staff, policy):
    enable_guests(policy)
    guest_client = APIClient()
    created = guest_client.post("/api/auth/guest/")
    guest = User.objects.get(handle=created.data["handle"])
    make_request(guest)

    api_client.force_authenticate(staff)
    listed = api_client.get("/api/admin/guests/")
    assert any(g["id"] == guest.id for g in listed.data["guests"])

    r = api_client.post(f"/api/admin/guests/{guest.id}/revoke/")
    assert r.data["is_active"] is False
    assert guest_client.get("/api/account/").status_code in (401, 403)

    r = api_client.post(f"/api/admin/guests/{guest.id}/purge/")
    assert r.status_code == 200
    assert not User.objects.filter(id=guest.id).exists()
    assert not InferenceRequest.objects.filter(user_id=guest.id).exists()


def test_access_policy_patch_and_validation(api_client, staff, policy):
    api_client.force_authenticate(staff)
    r = api_client.patch(
        "/api/admin/access-policy/",
        {"guest_signin_enabled": True, "anon_inference_rate": "5/min"},
        format="json",
    )
    assert r.status_code == 200
    assert AccessPolicy.load().guest_signin_enabled is True
    r = api_client.patch(
        "/api/admin/access-policy/", {"anon_inference_rate": "lots"}, format="json"
    )
    assert r.status_code == 400


def test_staff_endpoints_require_staff(api_client, github_user, guest):
    for user in (github_user, guest):
        api_client.force_authenticate(user)
        assert api_client.get("/api/admin/access-codes/").status_code == 403
        assert api_client.get("/api/admin/guests/").status_code == 403
        assert api_client.get("/api/admin/access-policy/").status_code == 403
