"""Generated public handles and access-code strings.

Handles are three-word slugs (``mighty-hill-hero``) from the ``coolname``
library: memorable, anonymous, and unguessable enough that an anonymous
account's profile URL doubles as its share link. Access codes are
higher-entropy credential strings (~60 bits) since they grant login.
"""

import secrets

from coolname import generate_slug

# Crockford base32: no 0/O/1/I/L/U lookalikes, so codes survive being read
# aloud or hand-typed from a chat message.
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
ACCESS_CODE_PREFIX = "club"

# coolname's lists are broadly safe but include a few words that don't belong
# in a name people publish content under.
_BLOCKED_WORDS = {"sexy", "kinky", "frisky", "moist", "thick", "stiff"}


def random_handle() -> str:
    """One three-word candidate handle. Uniqueness is the caller's problem.

    Rejects coolname's occasional ``x-of-y`` forms (uniform three tokens make
    better usernames) and its handful of innuendo-adjacent words.
    """
    while True:
        slug = generate_slug(3)
        words = slug.split("-")
        if len(words) == 3 and not (_BLOCKED_WORDS & set(words)):
            return slug


def generate_unique_handle(extra_taken: set[str] | None = None) -> str:
    """A handle free in both ``handle`` and ``anon_alias`` columns.

    Retries a few times, then appends a 2-digit suffix — with millions of
    combinations the suffix path is effectively unreachable, but the function
    must never loop forever.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    taken = extra_taken or set()

    def is_free(h: str) -> bool:
        if h in taken:
            return False
        return not User.objects.filter(handle__iexact=h).exists() and (
            not User.objects.filter(anon_alias__iexact=h).exists()
        )

    for _ in range(10):
        candidate = random_handle()
        if is_free(candidate):
            return candidate
    base = random_handle()
    for _ in range(100):
        candidate = f"{base}-{secrets.randbelow(90) + 10}"
        if is_free(candidate):
            return candidate
    raise RuntimeError("could not generate a unique handle")


def dedupe_handle(base: str, exclude_pk=None) -> str:
    """``base`` if free, else ``base-2``, ``base-3``, … Used when adopting a
    GitHub login as the handle (logins are unique on GitHub, but may collide
    with an existing alias or a renamed account here)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()

    def is_free(h: str) -> bool:
        qs = User.objects.filter(handle__iexact=h)
        alias_qs = User.objects.filter(anon_alias__iexact=h)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
            alias_qs = alias_qs.exclude(pk=exclude_pk)
        return not qs.exists() and not alias_qs.exists()

    if is_free(base):
        return base
    for i in range(2, 1000):
        candidate = f"{base}-{i}"
        if is_free(candidate):
            return candidate
    raise RuntimeError(f"could not dedupe handle {base!r}")


def generate_access_code() -> str:
    """A new passcode: ``club-XXXX-XXXX-XXXX`` (~59 bits of entropy)."""
    groups = [
        "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4)) for _ in range(3)
    ]
    return "-".join([ACCESS_CODE_PREFIX, *groups])


def normalize_access_code(raw: str) -> str:
    """Canonical form of a user-typed code: uppercase groups, single dashes,
    tolerant of stray whitespace. The ``club`` prefix stays lowercase."""
    cleaned = "".join((raw or "").split())
    parts = [p for p in cleaned.split("-") if p]
    if parts and parts[0].lower() == ACCESS_CODE_PREFIX:
        parts = parts[1:]
    return "-".join([ACCESS_CODE_PREFIX, *[p.upper() for p in parts]])
