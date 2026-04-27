"""Background prober that keeps ``Provider.last_seen_at`` warm.

Without this, idle providers fall outside the 120s online window between
inference requests and show as offline on the dashboard / public profile,
even though they're perfectly healthy. See BACKLOG.md and
``docs/plans/tailscale-agent-integration.md`` §6.

Runs as a small sidecar service in the prod compose template. Single
process, no Celery / Redis broker. Each tick parallel-probes every
active provider's ``/healthz`` over the tailnet SOCKS5 sidecar (same
proxy the backend itself uses for ``refresh_provider_models``).
"""

from __future__ import annotations

import logging
import signal
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.inference.models import Provider
from apps.inference.views import _tailnet_proxies

logger = logging.getLogger("django")


class Command(BaseCommand):
    help = (
        "Probes each active provider's /healthz over the tailnet on a fixed "
        "interval and bumps last_seen_at on success. Run as a long-lived "
        "sidecar so providers don't appear offline between inference requests."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=30,
            help=(
                "Seconds between probe rounds. 30s by default — well below "
                "the 120s online window in PROVIDER_LAST_SEEN_WINDOW."
            ),
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=2.0,
            help="Per-probe HTTP timeout in seconds.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=8,
            help="Concurrent probes per round.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run a single probe round and exit (for tests / cron).",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        timeout = options["timeout"]
        workers = options["workers"]
        once = options["once"]

        stopping = {"v": False}

        def _stop(signum, _frame):
            self.stdout.write(f"received signal {signum}, draining…")
            stopping["v"] = True

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        if once:
            self._round(timeout=timeout, workers=workers)
            return

        self.stdout.write(
            f"probe_providers running (interval={interval}s, "
            f"timeout={timeout}s, workers={workers})"
        )
        while not stopping["v"]:
            try:
                self._round(timeout=timeout, workers=workers)
            except Exception:
                # A bug here must not take the loop down — log and try again
                # next tick. Loud + recoverable beats silent crash-loops.
                logger.exception("probe_providers round failed")
            # Sleep in 1s slices so SIGTERM is responsive.
            for _ in range(interval):
                if stopping["v"]:
                    break
                time.sleep(1)

    def _round(self, *, timeout: float, workers: int) -> None:
        providers = list(
            Provider.objects.filter(is_active=True)
            .exclude(tailnet_hostname="")
            .only("id", "tailnet_hostname", "agent_port")
        )
        if not providers:
            return

        proxies = _tailnet_proxies()
        ok = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(self._probe, p, timeout, proxies): p for p in providers
            }
            for fut in futures:
                if fut.result():
                    ok += 1

        logger.info(
            "probe_providers: %d/%d providers responded ok",
            ok,
            len(providers),
        )

    def _probe(self, provider: Provider, timeout: float, proxies) -> bool:
        url = f"http://{provider.tailnet_hostname}:{provider.agent_port}/healthz"
        try:
            resp = requests.get(url, timeout=timeout, proxies=proxies, verify=False)
        except requests.RequestException as e:
            logger.debug("probe_providers: %s unreachable: %s", provider, e)
            return False
        if not resp.ok:
            logger.debug(
                "probe_providers: %s returned HTTP %d", provider, resp.status_code
            )
            return False
        # update() avoids touching modified_on / triggering signals; this is
        # a heartbeat, not a real change.
        Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
        return True
