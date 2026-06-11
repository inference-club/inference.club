"""Shared fixtures for the inference test suite."""
import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _isolate_throttle_state():
    """DRF's ScopedRateThrottle counts requests in the (LocMem) cache, which
    outlives each test's DB rollback — and user PKs repeat across tests, so a
    busy enough suite trips the 60/min inference rate with spurious 429s.
    Clearing between tests keeps throttle state test-local."""
    cache.clear()
    yield
