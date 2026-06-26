"""External-service API keys: the registry of known services + the per-user
accessors that every agent/tool must use.

Keys are stored per-user and encrypted at rest (``accounts.UserApiKey``), so a
key set once works across the text agent, the voice agent, and any future tool —
they all run as the user and read keys through ``get_user_api_key``. Add a new
service by appending one ``ExternalService`` entry here; the settings UI and the
accessor pick it up automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.conf import settings


@dataclass(frozen=True)
class ExternalService:
    slug: str
    name: str
    description: str
    docs_url: str = ""
    # settings attribute holding an instance-wide fallback key (optional).
    env_setting: str = ""
    # "tool" (an agent-tool key, e.g. Brave) or "llm_provider" (an external
    # OpenAI-compatible cloud the user can run LLM inference against — PRD 19).
    category: str = "tool"
    # For llm_provider services: the OpenAI-compatible API root the user's key
    # authenticates against, and the path under it that lists models.
    base_url: str = ""
    models_path: str = "/models"


CATEGORY_TOOL = "tool"
CATEGORY_LLM_PROVIDER = "llm_provider"


# The known services users can store keys for. Brave is wired today; the others
# are seeded so users can store keys ahead of the features that will use them.
EXTERNAL_SERVICES = [
    ExternalService(
        slug="brave",
        name="Brave Search",
        description="Web search for the agents' web_search_brave tool.",
        docs_url="https://brave.com/search/api/",
        env_setting="AGENT_BRAVE_API_KEY",
    ),
    ExternalService(
        slug="elevenlabs",
        name="ElevenLabs",
        description="High-quality text-to-speech voices (planned voice output).",
        docs_url="https://elevenlabs.io/app/settings/api-keys",
    ),
    ExternalService(
        slug="openai",
        name="OpenAI",
        description="Hosted LLM fallback when local models are unavailable (planned).",
        docs_url="https://platform.openai.com/api-keys",
    ),
    # --- external LLM providers (PRD 19): OpenAI-compatible clouds the user
    # brings a key for and pins models from. base_url is the /v1 root. ---
    ExternalService(
        slug="openrouter",
        name="OpenRouter",
        description="Hundreds of models from many labs behind one key.",
        docs_url="https://openrouter.ai/keys",
        category=CATEGORY_LLM_PROVIDER,
        base_url="https://openrouter.ai/api/v1",
    ),
    ExternalService(
        slug="nvidia",
        name="NVIDIA NIM",
        description="NVIDIA-hosted models from build.nvidia.com.",
        docs_url="https://build.nvidia.com/",
        category=CATEGORY_LLM_PROVIDER,
        base_url="https://integrate.api.nvidia.com/v1",
    ),
    ExternalService(
        slug="groq",
        name="Groq",
        description="Very fast inference on Groq LPUs.",
        docs_url="https://console.groq.com/keys",
        category=CATEGORY_LLM_PROVIDER,
        base_url="https://api.groq.com/openai/v1",
    ),
]

_BY_SLUG = {s.slug: s for s in EXTERNAL_SERVICES}


def llm_providers() -> list[ExternalService]:
    """The external LLM-provider services (PRD 19)."""
    return [s for s in EXTERNAL_SERVICES if s.category == CATEGORY_LLM_PROVIDER]


def is_llm_provider(slug: str) -> bool:
    svc = _BY_SLUG.get(slug)
    return bool(svc and svc.category == CATEGORY_LLM_PROVIDER)


def get_service(slug: str) -> Optional[ExternalService]:
    return _BY_SLUG.get(slug)


def get_user_api_key(user, service: str) -> str:
    """Return the user's key for ``service`` (decrypted), else the instance-wide
    env fallback. The ONE accessor every tool/agent should call."""
    if user is not None and getattr(user, "is_authenticated", False):
        from apps.accounts.models import UserApiKey

        row = UserApiKey.objects.filter(user=user, service=service).first()
        if row and row.value:
            return row.value
        # Back-compat: the legacy single Brave field on the user model.
        if service == "brave" and getattr(user, "brave_api_key", ""):
            return user.brave_api_key
    svc = _BY_SLUG.get(service)
    if svc and svc.env_setting:
        return getattr(settings, svc.env_setting, "") or ""
    return ""


def set_user_api_key(user, service: str, plaintext: str):
    from apps.accounts.models import UserApiKey

    row, _created = UserApiKey.objects.get_or_create(user=user, service=service)
    row.set_value(plaintext)
    row.save(update_fields=["value_encrypted", "modified_on"])
    return row


def clear_user_api_key(user, service: str) -> None:
    from apps.accounts.models import UserApiKey

    UserApiKey.objects.filter(user=user, service=service).delete()
