"""Cross-cutting operational endpoints: liveness and build/version metadata.

These are deliberately dependency-light and unauthenticated so they can back
container health probes (k8s liveness) and let the frontend display which
build/environment it's talking to (the git-tag / image-tag surfaced per the
home-lab deploy work). Values come from env vars set at deploy time.
"""

from django.conf import settings
from django.http import JsonResponse


def healthz(request):
    """Liveness probe. Intentionally does NO I/O (no DB/cache/network) so it
    stays green whenever the process is up and can serve requests — readiness
    of downstream deps is a separate concern."""
    return JsonResponse({"status": "ok"})


def meta(request):
    """Public build/version metadata. Powers the version indicator in the UI
    and lets the frontend and backend agree on 'which version is running'.

    - ``version``: the release/tag (or "dev" locally). Set via APP_VERSION,
      which the deploy pipeline feeds from the git tag / image tag.
    - ``git_sha``: the built commit (short), when the pipeline provides it.
    - ``env``: which deployment this is (local / homelab / cloud).
    """
    return JsonResponse(
        {
            "name": "inference.club",
            "version": settings.APP_VERSION,
            "git_sha": settings.GIT_SHA,
            "env": settings.DEPLOY_ENV,
        }
    )
