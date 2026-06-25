"""Host/GPU normalization (manifest → Host/Gpu rows), request→host/gpu linkage,
and the node-detail endpoint."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.inference.models import Gpu, Host, InferenceRequest, Provider
from apps.inference.views import sync_provider_models_from_manifest

User = get_user_model()


def _manifest(hosts):
    return {"schema_version": 1, "agent": {"name": "club-host"}, "hosts": hosts}


def _host(host_id, gpu=None, gpus=None, services=None, **extra):
    h = {"id": host_id, "services": services or []}
    if gpu is not None:
        h["gpu"] = gpu
    if gpus is not None:
        h["gpus"] = gpus
    h.update(extra)
    return h


def _svc(name, host_models=("m1",)):
    return {
        "name": name, "engine": "vllm", "url": "http://x/v1",
        "models": [{"id": m} for m in host_models],
    }


@pytest.fixture
def user():
    return User.objects.create_user(email="op@example.com", password="x")


@pytest.fixture
def provider(user):
    return Provider.objects.create(
        user=user, name="club-host", tailnet_hostname="club-host-1", is_active=True
    )


@pytest.fixture
def api_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.django_db
class TestHostGpuSync:
    def test_creates_hosts_gpus_and_links_service(self, provider):
        sync_provider_models_from_manifest(provider, _manifest([
            _host("a1", gpu={"vendor": "nvidia", "model": "RTX 4090", "vram_gb": 24},
                  hostname="spark", services=[_svc("vllm-a1")]),
        ]))
        host = Host.objects.get(provider=provider, host_id="a1")
        assert host.hostname == "spark"
        assert host.gpus.count() == 1
        g = host.gpus.first()
        assert (g.model, g.vendor, g.vram_gb) == ("RTX 4090", "nvidia", 24)
        svc = provider.services.get(name="vllm-a1")
        assert svc.host_id == host.id           # FK linked
        assert svc.manifest_host_id == "a1"     # raw key preserved

    def test_singular_gpu_count_expands_to_rows(self, provider):
        sync_provider_models_from_manifest(provider, _manifest([
            _host("multi", gpu={"vendor": "nvidia", "model": "A100", "count": 4}),
        ]))
        host = Host.objects.get(provider=provider, host_id="multi")
        assert host.gpus.count() == 4
        assert sorted(host.gpus.values_list("index", flat=True)) == [0, 1, 2, 3]
        assert set(host.gpus.values_list("model", flat=True)) == {"A100"}

    def test_gpus_list_one_row_per_device(self, provider):
        sync_provider_models_from_manifest(provider, _manifest([
            _host("k8s", gpus=[{"model": "RTX 4090"}, {"model": "RTX 3090"}]),
        ]))
        host = Host.objects.get(provider=provider, host_id="k8s")
        assert list(host.gpus.order_by("index").values_list("model", flat=True)) == [
            "RTX 4090", "RTX 3090",
        ]

    def test_removed_host_is_soft_deactivated_not_deleted(self, provider):
        sync_provider_models_from_manifest(provider, _manifest([
            _host("a1", services=[_svc("s1")]), _host("a2", services=[_svc("s2")]),
        ]))
        # Re-sync without a2.
        sync_provider_models_from_manifest(provider, _manifest([
            _host("a1", services=[_svc("s1")]),
        ]))
        assert Host.objects.filter(provider=provider).count() == 2  # kept
        assert Host.objects.get(host_id="a2").is_active is False
        assert Host.objects.get(host_id="a1").is_active is True


@pytest.mark.django_db
class TestRequestLinkage:
    def test_save_resolves_host_and_single_gpu(self, provider):
        sync_provider_models_from_manifest(provider, _manifest([
            _host("a1", gpu={"model": "RTX 4090"}, services=[_svc("s1")]),
        ]))
        host = Host.objects.get(host_id="a1")
        req = InferenceRequest.objects.create(
            user=provider.user, provider=provider, inference_type="IMAGE",
            payload={}, status="PROCESSED", dispatch_meta={"host_id": "a1"},
        )
        assert req.host_id == host.id
        assert req.gpu_id == host.gpus.first().id

    def test_save_leaves_gpu_null_for_multi_gpu_host(self, provider):
        sync_provider_models_from_manifest(provider, _manifest([
            _host("multi", gpu={"model": "A100", "count": 2}, services=[_svc("s1")]),
        ]))
        req = InferenceRequest.objects.create(
            user=provider.user, provider=provider, inference_type="IMAGE",
            payload={}, status="PROCESSED", dispatch_meta={"host_id": "multi"},
        )
        assert req.host_id == Host.objects.get(host_id="multi").id
        assert req.gpu_id is None  # can't attribute a device without an index


@pytest.mark.django_db
class TestNodeEndpoint:
    def test_node_detail_payload(self, provider, api_client):
        sync_provider_models_from_manifest(provider, _manifest([
            _host("a1", gpu={"vendor": "nvidia", "model": "RTX 4090", "vram_gb": 24},
                  hostname="spark", services=[_svc("vllm-a1")]),
        ]))
        InferenceRequest.objects.create(
            user=provider.user, provider=provider, inference_type="IMAGE",
            payload={}, status="PROCESSED", dispatch_meta={"host_id": "a1"},
            visibility="PUBLIC",
        )
        url = reverse("inference:provider-host-detail", args=[provider.id, "a1"])
        resp = api_client.get(url)
        assert resp.status_code == 200, resp.data
        data = resp.data
        assert data["host_id"] == "a1"
        assert data["hostname"] == "spark"
        assert data["is_owner"] is True
        assert [g["model"] for g in data["gpus"]] == ["RTX 4090"]
        assert {s["name"] for s in data["services"]} == {"vllm-a1"}
        assert data["stats"]["total"] == 1
        assert data["stats"]["by_modality"] == {"IMAGE": 1}
        assert len(data["recent"]) == 1

    def test_unknown_host_404(self, provider, api_client):
        url = reverse("inference:provider-host-detail", args=[provider.id, "nope"])
        assert api_client.get(url).status_code == 404
