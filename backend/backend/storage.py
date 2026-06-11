"""Media storage backends.

KindRoutedGCSStorage splits media between two Google Cloud Storage buckets
based on the object key's kind prefix (``media_asset_upload_to`` keys start
with the lowercased MediaAsset kind):

- ``input_audio/`` (the only non-public kind) goes to the private bucket,
  which has public-access-prevention enforced. It is read back through the
  backend's owner-gated asset route.
- Everything else goes to the public bucket and is served to browsers
  directly from ``storage.googleapis.com`` — no app hop, no signed-URL
  expiry to break long-lived links, and an immutable Cache-Control set at
  upload time (keys embed a UUID, so they never change content).

Two buckets instead of per-object ACLs keeps uniform bucket-level access on
(Google's recommendation) and makes the public/private boundary auditable
from the bucket list alone.
"""

import base64
import json
from datetime import timedelta

from django.conf import settings
from django.core.files.storage import Storage
from django.utils.functional import cached_property


def _gcs_credentials():
    """Service-account credentials from the base64 key JSON in the env, or
    None to let google-auth fall back to application-default credentials."""
    if not settings.GCS_CREDENTIALS_B64:
        return None
    from google.oauth2 import service_account

    info = json.loads(base64.b64decode(settings.GCS_CREDENTIALS_B64))
    return service_account.Credentials.from_service_account_info(info)


# Keys under this prefix hold owner-gated content (MediaAsset.INPUT_AUDIO is
# the only kind outside MediaAsset.PUBLIC_KINDS).
PRIVATE_PREFIX = "input_audio/"


class KindRoutedGCSStorage(Storage):
    def _backend(self, name):
        if (name or "").startswith(PRIVATE_PREFIX):
            return self._private
        return self._public

    @cached_property
    def _public(self):
        from storages.backends.gcloud import GoogleCloudStorage

        return GoogleCloudStorage(
            bucket_name=settings.GCS_PUBLIC_BUCKET,
            credentials=_gcs_credentials(),
            # Bucket grants allUsers objectViewer via uniform IAM; no object
            # ACLs, no signed query strings — .url() is the plain public URL.
            default_acl=None,
            querystring_auth=False,
            file_overwrite=False,
            object_parameters={
                "cache_control": "public, max-age=31536000, immutable"
            },
        )

    @cached_property
    def _private(self):
        from storages.backends.gcloud import GoogleCloudStorage

        return GoogleCloudStorage(
            bucket_name=settings.GCS_PRIVATE_BUCKET,
            credentials=_gcs_credentials(),
            default_acl=None,
            # .url() on a private object is a signed URL; the app only uses
            # it as an escape hatch (normal reads stream through open()).
            querystring_auth=True,
            expiration=timedelta(hours=1),
            file_overwrite=False,
        )

    # Storage's public API, delegated per key. save() goes through the
    # target backend's own save so its get_available_name/overwrite logic
    # applies to the bucket the object actually lands in.
    def open(self, name, mode="rb"):
        return self._backend(name).open(name, mode)

    def save(self, name, content, max_length=None):
        return self._backend(name).save(name, content, max_length=max_length)

    def get_available_name(self, name, max_length=None):
        return self._backend(name).get_available_name(name, max_length=max_length)

    def url(self, name):
        return self._backend(name).url(name)

    def exists(self, name):
        return self._backend(name).exists(name)

    def delete(self, name):
        return self._backend(name).delete(name)

    def size(self, name):
        return self._backend(name).size(name)

    def listdir(self, path):
        return self._backend(path).listdir(path)

    def get_modified_time(self, name):
        return self._backend(name).get_modified_time(name)

    def get_created_time(self, name):
        return self._backend(name).get_created_time(name)
