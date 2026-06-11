---
title: Sharing & collections
description: Who can see your generations, and how to organize them into collections.
order: 4
---

# Sharing & collections

Every inference request you make — a chat, an image, a song, a video — is stored in your dashboard. **Visibility** controls who else can see it; **collections** let you group requests into shareable, ordered sets (an album of songs, a gallery of renders).

## Visibility levels

| Level | Who can see it |
| --- | --- |
| `PUBLIC` | Anyone, even logged out. Listed on your public profile. |
| `UNLISTED` | Anyone with the share link. Not listed anywhere. *(default)* |
| `PRIVATE` | Any signed-in inference.club member. |
| `SECRET` | Only you. |

Unlisted and private requests are reachable by an unguessable share token (`/s/<token>`), never by a sequential id — links can be shared without exposing your other requests.

## Defaults

New requests inherit your account defaults. Set them either:

- from the **visibility picker next to the Generate button** in any playground (the choice persists and applies everywhere), or
- in **Dashboard → Settings → General**, or
- via the API:

```bash
curl -X PATCH https://api.inference.club/api/account/ \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{"default_request_visibility": "PUBLIC", "default_collection_name": "My album"}'
```

## Per-request overrides

Every generation endpoint accepts two optional fields on top of the OpenAI request shape. They are stripped before your request reaches a provider.

```json
{
  "model": "ace-step",
  "prompt": "dreamy lo-fi hip-hop",
  "visibility": "PUBLIC",
  "collection": "Late night beats"
}
```

- `visibility` — one of the four levels above, for this request only.
- `collection` — a collection **name**. Names are unique per account (case-insensitive); the collection is created on first use, and the request is appended to its playlist order.

## Collections

Collections have their own visibility, independent of their contents. Privacy is enforced item by item: a public collection that contains a secret request shows everyone *except* that request. A collection created implicitly by the `collection` parameter inherits the visibility of the request that created it; changing it later never touches the items.

Manage collections in **Dashboard → Collections**, or via `POST /api/inference/collections/` (get-or-creates by name).
