"""Cross-cutting operational endpoints: liveness and build/version metadata.

These are deliberately dependency-light and unauthenticated so they can back
container health probes (k8s liveness) and let the frontend display which
build/environment it's talking to (the git-tag / image-tag surfaced per the
home-lab deploy work). Values come from env vars set at deploy time.
"""

from django.conf import settings
from django.db import connections
from django.db.utils import Error as DBError
from django.http import JsonResponse


def healthz(request):
    """Liveness probe. Intentionally does NO I/O (no DB/cache/network) so it
    stays green whenever the process is up and can serve requests — readiness
    of downstream deps is a separate concern (see readyz)."""
    return JsonResponse({"status": "ok"})


def readyz(request):
    """Readiness probe: can this replica actually serve traffic? Checks the
    database is reachable. k8s should route to the pod only when this is 200;
    a 503 here (DB down / not yet migrated) sheds traffic without killing the
    pod the way a failed liveness probe would."""
    checks = {}
    ok = True
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except DBError:
        checks["database"] = "error"
        ok = False
    return JsonResponse(
        {"status": "ready" if ok else "not-ready", "checks": checks},
        status=200 if ok else 503,
    )


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
