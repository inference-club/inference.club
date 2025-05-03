import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.inference.models import InferenceRequest

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def test_user():
    return User.objects.create_user(email="test@example.com", password="testpass123")


@pytest.fixture
def other_user():
    return User.objects.create_user(email="other@example.com", password="testpass123")


@pytest.fixture
def authenticated_client(api_client, test_user):
    api_client.force_authenticate(user=test_user)
    return api_client


@pytest.fixture
def inference_request(test_user):
    return InferenceRequest.objects.create(
        user=test_user, inference_type="LLM", payload={"prompt": "Hello, world!"}
    )


@pytest.fixture
def other_inference_request(other_user):
    return InferenceRequest.objects.create(
        user=other_user, inference_type="LLM", payload={"prompt": "Hello, world!"}
    )


@pytest.mark.django_db
class TestInferenceViews:
    def test_create_inference_request(self, authenticated_client):
        url = reverse("inference:inference-requests")
        data = {"inference_type": "LLM", "payload": {"prompt": "Hello, world!"}}
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == 201
        assert response.data["status"] == "REQUESTED"
        assert response.data["inference_type"] == "LLM"

    def test_create_inference_request_unauthenticated(self, api_client):
        url = reverse("inference:inference-requests")
        data = {"inference_type": "LLM", "payload": {"prompt": "Hello, world!"}}
        response = api_client.post(url, data, format="json")

        assert response.status_code == 403

    @pytest.mark.parametrize("invalid_type", ["INVALID", "WRONG", "TEST"])
    def test_create_inference_request_invalid_type(
        self, authenticated_client, invalid_type
    ):
        url = reverse("inference:inference-requests")
        data = {"inference_type": invalid_type, "payload": {"prompt": "Hello, world!"}}
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == 400

    def test_retrieve_own_inference_request(
        self, authenticated_client, inference_request
    ):
        url = reverse("inference:inference-detail", args=[inference_request.id])
        response = authenticated_client.get(url)

        assert response.status_code == 200
        assert response.data["id"] == inference_request.id

    def test_retrieve_others_inference_request(
        self, authenticated_client, other_inference_request
    ):
        url = reverse("inference:inference-detail", args=[other_inference_request.id])
        response = authenticated_client.get(url)

        assert response.status_code == 404

    def test_list_inference_requests(
        self, authenticated_client, inference_request, other_inference_request
    ):
        url = reverse("inference:inference-requests")
        response = authenticated_client.get(url)

        assert response.status_code == 200
        assert len(response.data) == 1  # Should only see own requests
        assert response.data[0]["id"] == inference_request.id
