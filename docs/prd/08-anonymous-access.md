# PRD 08 — Anonymous access: guest accounts, passcodes & alias mode

> **Status:** Implemented (2026-06-12) — backend + frontend, all four
> milestones (A foundation, B passcodes, C guests + policy, D alias +
> upgrade). Backend covered by
> `apps/accounts/tests/test_anonymous_access.py` (36 tests; suite total
> 331). Handle generation uses the `coolname` library (3-word slugs +
> small blocklist) instead of a hand-rolled wordlist. Ships with
> `guest_signin_enabled=False` / `passcode_signin_enabled=True` —
> flip at /dashboard/admin/access.
>
> **Author:** Brian (spec) · drafted with Claude Code.
>
> **Decisions taken at spec time:**
> guest accounts are **persistent until revoked** (no auto-expiry);
> **one passcode = one persistent account** (re-entering the code logs
> back into the same account from any device); alias mode for GitHub
> users is a **full handle swap** (profile URL included); GitHub
> **linking/upgrade ships in V1**.
>
> **Scope:** Let people try inference.club without a GitHub identity —
> either as a one-click **guest** or via an admin-issued **passcode** —
> and let existing GitHub users go by a system-generated **anonymous
> alias** instead of their GitHub handle. Anonymous accounts are
> playground-only: no compute registration, no API tokens, no public
> content. Everything is admin-configurable in real time.
> **Explicitly out of scope:** HuggingFace sign-in, email/password
> accounts, payments/quotas beyond rate limits, social features.

---

## 1. Summary

Today the only way in is GitHub OAuth. That's a real barrier for
"just let me try it" visitors, and it forces everyone to wear their
real-world identity on a public-facing site. This PRD introduces three
related things, all built on one mechanism:

1. **Guest accounts** — a "Try anonymously" button on the login page.
   One click creates a real account with a generated handle like
   `mighty-hill-hero`, logged in via the normal session cookie. No
   email, no password, nothing typed.
2. **Passcode accounts** — admin-created codes handed to friends. Each
   code is the login credential for **one persistent account** with its
   own generated handle and unlisted profile. Codes can be labeled
   ("for Max"), given an optional expiry, and revoked (which kills the
   account's sessions instantly).
3. **Alias mode** — a GitHub-authenticated user can flip a switch and
   go by a generated handle instead of their GitHub login, everywhere:
   profile URL, content attribution, feeds. A GitHub icon may still be
   shown (provenance signal: "this is a verified-human account") but it
   never links to github.com.

Plus an **access policy panel** so the admin can turn each pathway on
or off, cap guest volume, and tighten anonymous rate limits — live,
without a deploy.

The unifying primitive is a **canonical `handle` on `CustomUser`** and
an **`account_type`** discriminator. Guests and passcode users are
ordinary `CustomUser` rows — every existing feature (visibility,
collections, moderation, throttling, the playground) works on them
unchanged. The work is mostly *subtraction*: a permission class that
denies anonymous accounts the dangerous endpoints, and UI that says
clearly "you're anonymous, here's what that means."

---

## 2. Current state (grounded in code)

| Concern | Where | Today |
| --- | --- | --- |
| Sign-in | Python Social Auth, `social_core.backends.github.GithubOAuth2` (`backend/settings.py:239`), URLs at `/oauth/…` (`backend/urls.py:25`) | GitHub OAuth only. `SOCIAL_AUTH_USER_FIELDS = ["email"]`. |
| User model | `apps/accounts/models.py:9` (`CustomUser`) | **`email` is `USERNAME_FIELD`** (unique). No username/handle field of its own. |
| Identity in API/URLs | `UserSerializer.get_github_login` (`apps/accounts/serializers.py:35-42`) iterates `user.social_auth` for `extra_data["login"]`; public profile at `/api/users/<github_login>/` (`apps/inference/views.py:1825`) | The GitHub login *is* the public handle. No alias possible. |
| API tokens | DRF `Token`, auto-minted on user creation by signal (`apps/accounts/signals.py:9-18`); lazily backfilled in `UserSerializer.get_api_token`; rotate at `POST /api/token/` (`apps/accounts/views.py:91-102`) | **Every** new user gets a token instantly. |
| Inference auth | `BearerTokenAuthentication` then `SessionAuthentication` (`settings.py:188-208`); `/v1/*` views require `IsAuthenticated` (`apps/inference/openai_views.py`) | Playground uses the session cookie (`usePlayground.ts:28-122`); CLI/SDK uses Bearer tokens. |
| Compute registration | `POST /api/inference/agent/register/` (`apps/inference/views.py:410-465`), `IsAuthenticated` | Any logged-in user can register providers and get a tailnet key. |
| Visibility | `Visibility` choices + `is_visible_to` / `visible_list_q` (`apps/inference/models.py:26-38, 587-601`) | PRIVATE = "any authenticated member". Default per-user visibility is UNLISTED. |
| Staff surface | `IsStaff` (`apps/core/permissions.py:4-15`), `/api/admin/*` (`apps/inference/staff_views.py`), `/dashboard/admin/*` + `staff` middleware | Activity dashboard + moderation queue exist; access-code management slots in beside them. |
| Throttling | `ScopedRateThrottle`, scopes `inference` 60/min, `models` 120/min (`settings.py:199-208`), Redis-backed cache | Per-user, one rate for everyone. |
| Login UI | `LoginForm.vue:15-17` → `window.location.href = '/oauth/login/github/'`; auth state in `useAuth.ts` / `stores/auth.ts` | Single GitHub button. Email/password forms exist but are dead. |
| Sessions | Standard Django sessions (`sessionid` cookie) | No way to revoke a specific user's sessions server-side. |

**Three facts that shape the design:**

1. `email` is the `USERNAME_FIELD` and is unique — anonymous accounts
   need a synthetic, collision-free email (`<handle>@anon.inference.club`).
2. The token-minting signal means anonymous accounts would get API keys
   *by default* — the signal and the lazy backfill must both be gated,
   in addition to gating the endpoints.
3. The public handle currently lives in `social_auth.extra_data`, not
   on the user — alias mode and guest handles both require promoting
   the handle to a first-class `CustomUser` field and migrating lookups.

---

## 3. Design

### 3.1 Canonical handle + account type (the foundation)

Add to `CustomUser`:

```python
class AccountType(models.TextChoices):
    GITHUB = "GITHUB"      # OAuth-backed, full member
    GUEST = "GUEST"        # self-serve anonymous
    PASSCODE = "PASSCODE"  # admin-issued anonymous

account_type = CharField(choices=AccountType, default=GITHUB)
handle = SlugField(unique=True, db_index=True)   # canonical public identity
anon_alias = SlugField(unique=True, null=True)   # generated once, stable
use_anon_alias = BooleanField(default=False)     # GitHub users only
session_epoch = PositiveIntegerField(default=0)  # bump to kill sessions
```

- `handle` is **the** public identity: profile URL, attribution, API.
  - GitHub user, alias off → `handle = github_login`.
  - GitHub user, alias on → `handle = anon_alias`.
  - Guest/passcode user → `handle = anon_alias` always.
- `anon_alias` is generated once and **stable across toggles** — turning
  alias mode off and on again returns the same alias, so links don't
  churn and aliases can't be farmed.
- Convenience property `is_anonymous_account` →
  `account_type in (GUEST, PASSCODE)`.
- **Migration:** backfill `handle` from each user's `social_auth`
  `extra_data["login"]` (fallback: email local-part slugified, suffixed
  on collision). Switch `PublicUserProfileView` / `PublicUserRequestsView`
  and `OwnerAttributionMixin` to look up / emit `handle`.
- **API compat:** serializers gain a `handle` key; the existing
  `github_login` key keeps being emitted but **populated with `handle`**
  (it's used as a URL slug throughout the frontend, and for non-alias
  GitHub users the value is identical). Frontend migrates to `handle`;
  `github_login` is removed once nothing reads it.

### 3.2 Handle generator

Three-word `adjective-noun-noun` slugs (`mighty-hill-hero`,
`quiet-fox-garden`) from curated wordlists in
`apps/accounts/wordlists.py` (~250 adjectives × ~250 × ~250 nouns ≈ 15M
combos — no profanity, no brand names, all lowercase ASCII). Generate,
check uniqueness against `handle` *and* `anon_alias`, retry up to 10×,
then append a 2-digit suffix. Pure function + property test.

### 3.3 Guest accounts

`POST /api/auth/guest/` (`AllowAny`, CSRF-protected, IP-throttled —
see §3.7):

1. Check `AccessPolicy.guest_signin_enabled`; check
   `max_active_guests` cap (count of non-revoked GUEST rows; `0` =
   unlimited). Return 403 with a human-readable reason if closed.
2. Create `CustomUser(account_type=GUEST, handle=<generated>,
   email=f"{handle}@anon.inference.club",
   default_request_visibility=UNLISTED, public_profile_enabled=True)`.
3. `django.contrib.auth.login(request, user)` — same session cookie as
   OAuth; everything downstream Just Works.
4. Return the serialized user.

Guests are **persistent until revoked**: closing the browser before the
session cookie expires loses access (acceptable — guests are told this,
and the upgrade path exists), but the account and its generations stay
until the admin revokes/purges. Session cookie age for guests uses the
default `SESSION_COOKIE_AGE` (2 weeks) — fine.

### 3.4 Passcodes

New model in `apps/accounts`:

```python
class AccessCode(models.Model):
    code = CharField(unique=True, db_index=True)   # e.g. "club-RV7K-XM2P-9QFD"
    user = OneToOneField(CustomUser, on_delete=CASCADE, related_name="access_code")
    label = CharField(blank=True)                  # "for Max"
    is_active = BooleanField(default=True)
    expires_at = DateTimeField(null=True, blank=True)
    created_by = ForeignKey(CustomUser, SET_NULL, null=True, related_name="+")
    created_at / last_used_at = DateTimeField(...)
    use_count = PositiveIntegerField(default=0)    # successful logins
```

- **Creating a code creates its account** (`account_type=PASSCODE`,
  generated handle) in the same transaction. The code *is* the login
  credential for that one account, forever.
- `code` is stored **plaintext**, deliberately: the admin must be able
  to re-display and re-send it to a friend who lost it. These are
  low-privilege, individually revocable, hard-throttled credentials —
  not password-grade secrets. Format: `club-` prefix + 12 chars of
  Crockford base32 in groups of 4 (~60 bits, unguessable at 10
  attempts/hour).
- `POST /api/auth/passcode/ {code}` (`AllowAny`, CSRF, IP-throttled):
  constant-time lookup; reject if `is_active=False`, expired, or the
  bound user `is_active=False`; else bump `use_count`/`last_used_at`
  and `login()`. Uniform error ("invalid or revoked code") regardless
  of failure reason.
- **Revoke** = `is_active=False` + bump the user's `session_epoch`
  (kills live sessions, §3.6) + optionally `user.is_active=False`.
  Content stays (unlisted) unless the admin purges it.

### 3.5 What anonymous accounts can and cannot do

| Capability | GitHub | Guest / Passcode |
| --- | --- | --- |
| Playground (all modalities, session-auth `/v1/*`) | ✓ | ✓ (tighter throttle) |
| Generations history, collections, stars, bookmarks | ✓ | ✓ |
| Visibility on own content | any | **UNLISTED / PRIVATE / SECRET only — never PUBLIC** |
| See other members' PRIVATE content | ✓ | **✗ — treated as unauthenticated for visibility** |
| Public profile `/<handle>` | ✓ | ✓ but *unlisted* (see below) |
| API tokens (`/api/token/*`) | ✓ | **✗** |
| Bearer-token calls to `/v1/*` | ✓ | **✗** (no token exists; Bearer path also denies) |
| Register compute / agents / providers | ✓ | **✗** |
| Reporting content, account settings (subset) | ✓ | ✓ |
| Staff endpoints | per `is_staff` | ✗ (anonymous accounts can never be staff — enforced in `clean()`) |

Enforcement, layered:

1. **New permission class** `IsFullMember` (`apps/core/permissions.py`):
   authenticated **and** `not user.is_anonymous_account`. Applied to:
   token views, `AgentRegisterView`, all provider/service/deployment
   management views, and `PATCH /api/account/` fields that don't apply
   (e.g. `routing_preference`).
2. **Signal gating:** `apps/accounts/signals.py` skips token creation
   when `instance.is_anonymous_account`; `UserSerializer.get_api_token`
   returns `None` for them instead of lazily minting.
3. **Visibility clamp:** serializers validating
   `visibility` / `default_request_visibility` reject `PUBLIC` for
   anonymous accounts (and the create-request path clamps to UNLISTED).
   `is_visible_to` / `visible_list_q` treat anonymous accounts like
   unauthenticated viewers for the PRIVATE tier.
4. **Throttle split:** a small `ScopedRateThrottle` subclass resolves
   scope `inference` → `inference_anon` (and `models` →
   `models_anon`) when the request user is anonymous-type. Rates come
   from `AccessPolicy` (§3.7) with env-var defaults
   (`ANON_INFERENCE_RATE_LIMIT`, default `15/min`).

The **"unlisted public profile"**: `/<handle>` resolves for anonymous
accounts (it's a normal profile page), but since all their content is
≤ UNLISTED, `visible_list_q` would show an empty page. Instead, the
profile view shows the owner's **UNLISTED** items *when the profile
belongs to an anonymous account* — the random handle is itself the
unguessable share token, and nothing links to the page. This matches
the spirit of "their own unlisted public profile": shareable by the
owner, discoverable by no one. (For GitHub users, UNLISTED stays
excluded from profiles — no behavior change.)

### 3.6 Session revocation (`session_epoch`)

Django can't natively kill one user's sessions. Standard fix:

- On `login()`, stamp `request.session["epoch"] = user.session_epoch`.
- A lightweight middleware (after `AuthenticationMiddleware`) compares;
  mismatch → `logout(request)`. O(1), no session-table scans.
- **Revoke a user** = `session_epoch += 1`. Used by: passcode revoke,
  guest revoke, and a "log out everywhere" button later for free.

### 3.7 Real-time access policy (the admin knobs)

Singleton `AccessPolicy` model (`apps/accounts`), cached 30 s:

| Field | Default | Effect |
| --- | --- | --- |
| `guest_signin_enabled` | `False` | Shows/hides the guest button (login page reads `GET /api/auth/options/`) and gates the endpoint. |
| `passcode_signin_enabled` | `True` | Same for the passcode form. |
| `max_active_guests` | `100` | Cap on non-revoked guest accounts; `0` = unlimited. Endpoint returns "guest access is full" when hit. |
| `guest_creation_rate` | `5/hour` | Per-IP throttle on `POST /api/auth/guest/`. |
| `passcode_attempt_rate` | `10/hour` | Per-IP throttle on `POST /api/auth/passcode/`. |
| `anon_inference_rate` | `15/min` | Throttle for anonymous accounts on `/v1/*`. |
| `anon_models_rate` | `60/min` | Same for `/v1/models`. |
| `guest_message` | `""` | Optional banner copy shown to guests (e.g. "demo weekend — accounts may be reset"). |

Editable from Django admin **and** the in-app admin panel (§3.9).
`GET /api/auth/options/` (`AllowAny`) returns
`{github: true, guest: bool, passcode: bool, guest_message}` so the
login page renders the right buttons without hardcoding.

This is the rollout dial: ship with guests **off**, hand passcodes to
friends, watch the activity dashboard, then flip `guest_signin_enabled`
when ready — no deploy.

### 3.8 Alias mode for GitHub users

- Settings → Privacy section: **"Use an anonymous alias"** toggle.
  - On: generate `anon_alias` if absent, set `use_anon_alias=True`,
    `handle = anon_alias`. The old `/<github_login>` URL now 404s —
    the UI says so explicitly before confirming.
  - Off: `handle = github_login` again. Alias is kept for next time.
  - One **regenerate** allowed per 30 days (prevents churn/squatting).
- While aliased, **nothing public emits the GitHub login**: profile
  API, attribution mixin, request serializers all emit `handle` only.
  Avatar: the GitHub avatar URL is itself identifying (it contains the
  user ID and is reverse-searchable) — aliased users get a generated
  identicon derived from the handle instead.
- **GitHub badge:** profiles show a small GitHub mark meaning
  "GitHub-verified account" — *no link, no login shown*. Anonymous
  accounts show a mask badge instead ("anonymous account"). This gives
  viewers a provenance signal without deanonymizing anyone.

### 3.9 Admin surface

**Backend** (`/api/admin/…`, all `IsStaff`, alongside existing staff views):

- `GET/POST /api/admin/access-codes/` — list (label, handle, active,
  expiry, last_used, use_count, request count) / create
  (label, optional expiry → returns code + handle).
- `PATCH/DELETE /api/admin/access-codes/<id>/` — edit label/expiry,
  **revoke** (deactivate + epoch bump), reactivate; DELETE also
  deactivates the bound user.
- `GET /api/admin/guests/` — guest accounts with created, last_seen,
  request count; `POST /api/admin/guests/<id>/revoke/` (epoch bump +
  `is_active=False`); `POST …/purge/` (delete account + content —
  confirm-gated).
- `GET/PATCH /api/admin/access-policy/` — the §3.7 knobs.
- Activity dashboard additions: guest/passcode counts, requests by
  account type, "guests created (24h/7d)".

**Frontend:** new `/dashboard/admin/access/` page (staff middleware):
policy toggles with live save, passcode table with **copy-code**
button + create modal, guest table with revoke/purge. Register
`AccessCode` + `AccessPolicy` in Django admin too (belt and braces).

### 3.10 Upgrade path: "Keep this account"

PSA's default pipeline associates a social identity with the
*currently logged-in* user. So:

1. Anonymous user clicks **"Keep this account — sign in with GitHub"**
   → normal `/oauth/login/github/` redirect while their session is live.
2. A pipeline step (custom, inserted before `create_user`): if
   `request.user` is an anonymous account and this GitHub identity
   isn't already linked to another user → associate, then:
   `account_type = GITHUB`, real email from GitHub replaces the
   synthetic one (uniqueness check — if that email already owns an
   account, abort with "you already have an account; log into it
   instead"), mint API token, deactivate any bound `AccessCode`
   (the code must not remain a backdoor into a now-real account), set
   `use_anon_alias = True` (**they keep their anonymous handle by
   default** — upgrading shouldn't deanonymize; they can switch to
   their GitHub handle in settings).
3. All generations, collections, stars survive untouched — same user row.

### 3.11 Frontend UX

**Login page** (`LoginForm.vue` rework, driven by `/api/auth/options/`):

```
┌──────────────────────────────────────┐
│  [  Continue with GitHub  ]          │
│  ──────────── or ────────────        │
│  [ 🎭 Try anonymously ]              │   ← only if guest_signin_enabled
│  Have a passcode? [__________] [→]   │   ← only if passcode_signin_enabled
│                                      │
│  Anonymous sessions get a random     │
│  name like mighty-hill-hero. No      │
│  email, nothing to identify you.     │
└──────────────────────────────────────┘
```

**Being-anonymous indicators** (clear, not nagging — one persistent
affordance + one dismissible banner):

- **Persistent:** mask icon + handle in the dashboard sidebar/header
  user chip, with a popover: what's stored (generations under a random
  name), what's not (no email, no identity), how to keep the account
  (GitHub link), and for guests: "access lives in this browser — if
  you log out or clear cookies, it's gone."
- **Once:** a dismissible welcome banner on first dashboard load:
  "You're anonymous as **mighty-hill-hero**" + the same three facts +
  `guest_message` from policy if set.
- **Gated features:** Compute and API-token sections render a quiet
  locked state — "Available with a GitHub account" + the keep-account
  CTA — rather than disappearing (discoverability beats mystery).
- **Visibility picker:** PUBLIC option shown disabled with tooltip
  "Anonymous accounts can't publish publicly."

**Alias mode (GitHub users):** Settings → Privacy card with the toggle,
current alias preview, regenerate (rate-limited), and an explicit
confirm dialog listing consequences ("your profile moves to
/mighty-hill-hero; /briancaffey will 404; your GitHub avatar is
replaced with an identicon").

**i18n:** all new strings through `@nuxtjs/i18n` across the 7 locales,
same as everything else.

---

## 4. API summary (new/changed)

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `GET /api/auth/options/` | AllowAny | Which sign-in methods are live + guest message. |
| `POST /api/auth/guest/` | AllowAny + IP throttle | Create + log in a guest. |
| `POST /api/auth/passcode/` | AllowAny + IP throttle | Log into a passcode account. |
| `PATCH /api/account/` | IsAuthenticated | + `use_anon_alias` toggle, alias regenerate action. |
| `GET /api/users/<handle>/` (+`/requests/`) | AllowAny | Lookup switches from github_login to `handle`; anonymous-owner profiles include their UNLISTED items. |
| `/api/token/*`, `/api/inference/agent/register/`, provider mgmt | **IsFullMember** | Anonymous accounts denied (403 with explanatory detail). |
| `/api/admin/access-codes/…`, `/api/admin/guests/…`, `/api/admin/access-policy/` | IsStaff | §3.9. |

---

## 5. Rollout

| Milestone | Contents | Gate |
| --- | --- | --- |
| **A — Foundation** | `handle`/`account_type`/epoch migration + backfill, handle generator, `IsFullMember`, signal/serializer token gating, visibility clamp, session-epoch middleware. | Invisible to users; full test pass. |
| **B — Passcodes** | `AccessCode` + auth endpoint + admin UI/API + login-page passcode form + anonymous-UX indicators + gated-feature states. | Hand codes to friends. `guest_signin_enabled` still false. |
| **C — Guests + policy** | `AccessPolicy` + options endpoint + guest endpoint + guest button + caps/throttles + activity-dashboard counters. | Flip the toggle when comfortable. |
| **D — Alias + upgrade** | Alias toggle for GitHub users, identicon avatars, GitHub badge, PSA upgrade pipeline step. | Independent of B/C exposure. |

Each milestone is shippable alone; B before C means friends test the
whole anonymous UX before strangers can.

---

## 6. Abuse & safety considerations

- **Creation throttles** (per-IP, policy-configurable) + the
  `max_active_guests` cap bound the blast radius; guests can't publish
  PUBLIC content, so the feeds/profiles surface can't be spammed.
- **Moderation:** anonymous users' content flows through the existing
  ContentReport/moderation queue unchanged (they're normal users); the
  moderation queue and admin tables show account type.
- **No staff escalation:** model `clean()` forbids
  `is_staff/is_superuser` on anonymous account types.
- **Code hygiene:** uniform error on passcode failure; constant-time
  compare; ~60-bit codes; per-IP attempt throttle.
- **Cleanup:** management command `purge_anonymous` (flags:
  `--inactive-days N`, `--revoked-only`, `--dry-run`) for manual or
  cron use later — no automatic deletion since guests are
  persistent-by-decision.
- **Synthetic email domain** `anon.inference.club`: never emailed; if
  transactional email ever ships, sender must skip this domain.

## 7. Testing

- `apps/accounts/tests/test_anonymous_access.py`: guest creation
  (enabled/disabled/cap/throttle), passcode login (valid, revoked,
  expired, wrong, throttled), epoch revocation, token-mint gating,
  `IsFullMember` on every gated endpoint, visibility clamp +
  PRIVATE-as-anonymous, handle generator (uniqueness, retries, format),
  alias toggle round-trip + old-URL 404, upgrade pipeline (happy path,
  email-collision abort, code deactivation).
- Frontend: login-page option rendering from `/api/auth/options/`,
  gated-feature locked states, anonymity chip/banner.
- Existing suites must pass unmodified except the handle/serializer
  migration (mind the throttle-cache flakiness conftest fix).

## 8. Open questions (fine to decide at implementation)

1. Should guests be allowed *all* playground modalities, or should
   expensive ones (video, 3D) be passcode-and-up? (Lean: all, the
   throttle is the control; revisit if abused.)
2. Does an anonymous account's profile "served" tab matter? They can't
   register compute, so it's always empty — probably hide it.
3. Should the unused email/password `login()`/`register()` code in
   `useAuth.ts` be deleted as part of the LoginForm rework? (Lean: yes.)
