"""Account auth tests: API tokens are auto-minted and exposed on the user."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.serializers import UserSerializer

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="alice@example.com", password="x")


def test_token_minted_on_user_creation(user):
    # The post_save signal mints a key the moment the account exists.
    assert Token.objects.filter(user=user).exists()


def test_serializer_exposes_api_token(user):
    data = UserSerializer(user).data
    assert data["api_token"] == Token.objects.get(user=user).key


def test_serializer_backfills_missing_token(user):
    # Pre-existing users without a token get one lazily on serialization.
    Token.objects.filter(user=user).delete()
    data = UserSerializer(user).data
    assert data["api_token"]
    assert Token.objects.filter(user=user).exists()


def test_account_endpoint_returns_api_token(user):
    client = APIClient()
    client.force_authenticate(user=user)
    resp = client.get("/api/account/")
    assert resp.status_code == 200
    assert resp.data["api_token"] == Token.objects.get(user=user).key
