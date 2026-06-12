"""Shared fixtures for the accounts test suite."""
import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _isolate_cache_state():
    """Throttle counters and the AccessPolicy singleton both live in the
    (LocMem) cache, which outlives each test's DB rollback. Clearing between
    tests keeps both test-local (same gotcha as the inference suite)."""
    cache.clear()
    yield
