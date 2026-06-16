"""Per-device locks (apps.inference.locks): the key derivation that mirrors the
job dispatcher's capacity groups, and the no-op fallback when Redis is absent."""
from types import SimpleNamespace

from apps.inference.locks import device_lock, provider_device_key


def test_key_prefers_resource_group():
    pm = SimpleNamespace(
        provider=SimpleNamespace(id=7),
        service=SimpleNamespace(resource_group="gpu0", service_type="tts"),
    )
    assert provider_device_key(pm) == "device:7:gpu0"


def test_key_falls_back_to_service_type():
    pm = SimpleNamespace(
        provider=SimpleNamespace(id=7),
        service=SimpleNamespace(resource_group="", service_type="tts"),
    )
    assert provider_device_key(pm) == "device:7:tts"


def test_key_handles_missing_pieces():
    assert provider_device_key(None) == ""
    pm = SimpleNamespace(provider=SimpleNamespace(id=3), service=None)
    assert provider_device_key(pm) == "device:3:default"


def test_lock_is_noop_without_redis(settings):
    settings.DEVICE_LOCK_REDIS_URL = ""
    import apps.inference.locks as locks
    locks._client = None
    locks._client_ready = False
    with device_lock("device:1:tts") as held:
        assert held is True
    with device_lock("") as held:  # empty key never locks
        assert held is True
