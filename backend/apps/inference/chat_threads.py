"""AI-generated titles for saved chat threads.

Runs off the request path (Celery) so creating a thread stays instant. Picks an
LLM the thread owner can route to and asks it for a short title with *thinking
disabled*.

Verified empirically against the Nemotron-Omni build in the cluster: the
documented ``"detailed thinking off"`` system directive does NOT suppress
reasoning there, but ``chat_template_kwargs={"enable_thinking": False}`` does
(0 reasoning tokens). We send the body straight to the provider, so the flag
reaches vLLM unchanged.
"""
import logging
import re

import requests

logger = logging.getLogger("django")

_TITLE_SYSTEM = (
    "You write a short, specific title for a chat conversation. "
    "Reply with ONLY the title: 3 to 6 words, in Title Case, with no "
    "surrounding quotes, no trailing punctuation, and no emoji. Summarize the "
    "user's topic."
)
_TITLE_TIMEOUT = 60


def _as_text(content) -> str:
    """Flatten an OpenAI message ``content`` (str or multimodal parts) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            p.get("text") or ""
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return " ".join(parts).strip()
    return ""


def _first_exchange(messages):
    """The first user message and first assistant reply, as plain text."""
    user_text = assistant_text = ""
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "user" and not user_text:
            user_text = _as_text(m.get("content"))
        elif role == "assistant" and not assistant_text:
            assistant_text = _as_text(m.get("content"))
        if user_text and assistant_text:
            break
    return user_text.strip(), assistant_text.strip()


def _clean_title(raw: str) -> str:
    """Normalize the model's reply into a tidy title."""
    t = (raw or "").strip()
    if not t:
        return ""
    t = t.splitlines()[0].strip()  # first line only
    t = re.sub(r"^(title)\s*[:\-]\s*", "", t, flags=re.IGNORECASE).strip()
    t = t.strip("\"'").strip()
    t = t.rstrip(".")
    return t[:120].strip()


def generate_thread_title(thread_id) -> None:
    from .jobs import auto_model_for
    from .models import ChatThread
    from .openai_views import _find_provider_for_model, _retry_endpoint
    from .views import _tailnet_proxies

    thread = ChatThread.objects.filter(id=thread_id).select_related("user").first()
    if thread is None or thread.title_generated:
        return

    user_text, assistant_text = _first_exchange(thread.messages)
    if not user_text:
        return  # nothing to summarize yet

    user = thread.user
    model = thread.model or auto_model_for(user, "llm")
    pm = _find_provider_for_model(user, model) if model else None
    if pm is None:
        # Fall back to any LLM the user can reach (their chosen model may be
        # offline now even though the conversation used it earlier).
        model = auto_model_for(user, "llm")
        pm = _find_provider_for_model(user, model) if model else None
    if pm is None:
        logger.info("chat title: no online LLM for thread %s; skipping", thread_id)
        return

    convo = f"User: {user_text[:1500]}"
    if assistant_text:
        convo += f"\n\nAssistant: {assistant_text[:800]}"

    body = {
        "model": pm.name or model,
        "messages": [
            {"role": "system", "content": _TITLE_SYSTEM},
            {"role": "user", "content": convo + "\n\nTitle:"},
        ],
        "stream": False,
        "max_tokens": 24,
        "temperature": 0.3,
        # Verified to disable Nemotron reasoning — see module docstring.
        "chat_template_kwargs": {"enable_thinking": False},
    }

    try:
        resp = requests.post(
            _retry_endpoint(pm.provider, "/chat/completions"),
            json=body,
            timeout=_TITLE_TIMEOUT,
            verify=False,
            proxies=_tailnet_proxies(),
        )
        resp.raise_for_status()
        data = resp.json()
        raw = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    except Exception:
        logger.exception("chat title generation failed for thread %s", thread_id)
        return

    title = _clean_title(raw)
    if not title:
        return

    # Re-load so we never clobber a concurrent message update with a stale row.
    thread = ChatThread.objects.filter(id=thread_id).first()
    if thread is None:
        return
    thread.title = title
    thread.title_generated = True
    thread.save(update_fields=["title", "title_generated", "modified_on"])
    logger.info("chat title for thread %s: %r", thread_id, title)
