"""Sharing extensions to the OpenAI-compatible /v1 request shape.

Every generation endpoint accepts two optional inference.club-specific body
fields on top of the OpenAI schema:

  visibility — PUBLIC | UNLISTED | PRIVATE | SECRET; overrides the account's
               default visibility for this one request.
  collection — a collection *name* (unique per user, case-insensitive); the
               request is filed into that collection, creating it on first
               use. Falls back to the account's default collection.

Both are stripped before anything is forwarded upstream, so providers never
see them. Lives in its own module (importing only models) because both
``views`` and ``openai_views`` need it and ``openai_views`` already imports
from ``views``.
"""
import logging

from django.db.models import Max
from django.utils.text import slugify

from .models import (
    VISIBILITY_VALUES,
    Collection,
    CollectionItem,
)

logger = logging.getLogger("django")

COLLECTION_NAME_MAX_LENGTH = Collection._meta.get_field("name").max_length


def pop_sharing_params(request):
    """Extract ``(visibility, collection_name)`` from the request body.

    Mutable JSON bodies have the keys *removed* so raw-body proxies (chat) and
    ``dict(body)`` forwards (image generations) never leak them upstream;
    immutable multipart ``QueryDict``s are only read — their forward loops
    must skip ``SHARING_KEYS`` explicitly. Invalid values are ignored rather
    than rejected: a generation should never fail over a sharing knob.
    """
    data = request.data
    if isinstance(data, dict):
        visibility = data.pop("visibility", None)
        collection = data.pop("collection", None)
    else:
        visibility = data.get("visibility")
        collection = data.get("collection")

    if not isinstance(visibility, str) or visibility.upper() not in VISIBILITY_VALUES:
        visibility = None
    else:
        visibility = visibility.upper()

    if not isinstance(collection, str):
        collection = None
    else:
        collection = collection.strip()[:COLLECTION_NAME_MAX_LENGTH] or None

    return visibility, collection


# Body keys that multipart views must exclude when forwarding form fields.
SHARING_KEYS = {"visibility", "collection"}


def unique_collection_slug(user, name, instance=None) -> str:
    """A slug unique within ``user``'s collections, derived from ``name``."""
    base = slugify(name) or "collection"
    slug = base
    n = 2
    qs = Collection.objects.filter(user=user)
    if instance is not None:
        qs = qs.exclude(pk=instance.pk)
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def get_or_create_collection(user, name, visibility=None):
    """The user's collection with this name (case-insensitive), created on
    first use. Names are the API's unique handle for collections; matching
    existing names instead of always creating keeps them unique without a DB
    constraint (which couldn't be added under pre-existing duplicates —
    ``first()`` picks the oldest then)."""
    existing = (
        Collection.objects.filter(user=user, name__iexact=name)
        .order_by("created_on")
        .first()
    )
    if existing is not None:
        return existing
    return Collection.objects.create(
        user=user,
        name=name,
        slug=unique_collection_slug(user, name),
        # A collection born from a generation inherits that generation's
        # effective visibility — privacy-first, since the request's own
        # visibility still gates each item wherever the collection shows.
        **({"visibility": visibility} if visibility in VISIBILITY_VALUES else {}),
    )


def file_into_collection(user, ir, collection_name=None) -> None:
    """Append a freshly created request to the named collection (or the
    account's default collection when no name was given). Never raises: a
    filing hiccup must not fail the generation that already ran."""
    name = collection_name or (user.default_collection_name or "").strip()
    if not name:
        return
    try:
        col = get_or_create_collection(user, name, visibility=ir.visibility)
        next_pos = (col.items.aggregate(max_pos=Max("position"))["max_pos"] or 0) + 1
        CollectionItem.objects.get_or_create(
            collection=col, request=ir, defaults={"position": next_pos}
        )
    except Exception as e:
        logger.warning("collection filing failed for request %s: %s", ir.id, e)
