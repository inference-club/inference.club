from rest_framework.authentication import TokenAuthentication


class BearerTokenAuthentication(TokenAuthentication):
    """DRF TokenAuthentication that accepts the OpenAI-style ``Authorization: Bearer <key>`` header."""

    keyword = "Bearer"
