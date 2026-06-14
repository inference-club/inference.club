"""Generate high-level workflow prompts using a local LLM and store them in the
WorkflowPromptSuggestion table. Run this once (or periodically) to seed the
suggestion gallery on the queue dashboard.

Usage:
    python manage.py generate_workflow_prompts
    python manage.py generate_workflow_prompts --template illustrated-story --count 30
    python manage.py generate_workflow_prompts --clear

The command uses the Django test client so it goes through the full proxy
routing stack without needing a running HTTP server — it finds whatever chat
model the superuser can reach and calls it in-process.
"""

import json
import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

User = get_user_model()
logger = logging.getLogger("django")

# One carefully-worded system prompt per template. Keep them concise so the
# model fills the JSON array without padding.
_SYSTEM = (
    "You are a creative assistant. Respond with ONLY a JSON array of strings "
    "— no prose, no code fences, no keys, just the raw JSON array."
)

_TEMPLATE_PROMPTS = {
    "illustrated-story": (
        "Generate {count} diverse, imaginative story topics for a short illustrated story. "
        "Each topic should be a vivid 5-15 word description of a scenario, character, or theme. "
        "Vary the mood: whimsical, melancholic, adventurous, mysterious, heartwarming. "
        "Examples: 'a lighthouse keeper who befriends a lonely whale', "
        "'a clockmaker whose clocks reveal lost memories'. "
        "Return a JSON array of {count} strings."
    ),
    "image-variations": (
        "Generate {count} creative subjects for an image-variation explorer. "
        "Each subject should be a short noun phrase (3-8 words) that's visually interesting "
        "and amenable to multiple artistic interpretations. "
        "Examples: 'a cozy reading nook', 'an ancient library in the clouds'. "
        "Return a JSON array of {count} strings."
    ),
    "storyboard-to-video": (
        "Generate {count} vivid video concept descriptions for a storyboard-to-video pipeline. "
        "Each should be a single evocative sentence describing motion and atmosphere — "
        "something a cinematographer could storyboard. "
        "Examples: 'a seed sprouting into a glowing tree in time-lapse', "
        "'waves crashing over tide pools at golden hour, slow motion'. "
        "Return a JSON array of {count} strings."
    ),
    "song-and-cover": (
        "Generate {count} music themes for a song + cover art generator. "
        "Each theme should be 4-10 words capturing a mood, scene, or feeling "
        "that translates well into both lyrics and visual art. "
        "Examples: 'late-night drive through neon city rain', 'first snow in a forgotten town'. "
        "Return a JSON array of {count} strings."
    ),
    "narrated-explainer": (
        "Generate {count} interesting topics for a short narrated explainer video. "
        "Each should be a concrete, curiosity-sparking subject that can be explained "
        "in 4-8 spoken lines. "
        "Examples: 'how lighthouses work', 'why cats purr', 'the life cycle of a star'. "
        "Return a JSON array of {count} strings."
    ),
}


def _call_chat(user, messages):
    """Call /v1/chat/completions via the Django test client (in-process, no
    running server needed). Returns the assistant content string or raises."""
    from django.test import Client
    client = Client()
    client.force_login(user)
    resp = client.post(
        "/v1/chat/completions",
        data=json.dumps({"messages": messages, "stream": False}),
        content_type="application/json",
    )
    if resp.status_code != 200:
        try:
            detail = resp.json()
        except Exception:
            detail = {"raw": resp.content[:200].decode(errors="replace")}
        raise CommandError(f"Chat completions failed ({resp.status_code}): {detail}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _parse_suggestions(raw):
    """Extract a list of strings from LLM output, tolerating minor formatting
    quirks (code fences, leading/trailing whitespace, single vs double quotes)."""
    text = raw.strip()
    # Strip markdown code fences if the model added them
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            l for l in lines if not l.startswith("```")
        ).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError(f"Expected a JSON array, got {type(parsed).__name__}")
    return [str(s).strip() for s in parsed if str(s).strip()]


class Command(BaseCommand):
    help = "Generate LLM workflow prompt suggestions and store them in the DB"

    def add_arguments(self, parser):
        parser.add_argument(
            "--template",
            default="",
            help="Template key to generate for (default: all templates)",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Number of suggestions to generate per template (default: 20)",
        )
        parser.add_argument(
            "--user",
            default="",
            help="Email of the user whose models to use (default: first superuser)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing suggestions before generating new ones",
        )

    def handle(self, *args, **options):
        from apps.inference.models import WorkflowPromptSuggestion
        from apps.inference.workflow_templates import TEMPLATES

        # Resolve user
        if options["user"]:
            try:
                user = User.objects.get(email=options["user"])
            except User.DoesNotExist:
                raise CommandError(f"User {options['user']!r} not found")
        else:
            user = User.objects.filter(is_superuser=True, is_active=True).first()
            if user is None:
                raise CommandError("No superuser found — pass --user <email>")

        self.stdout.write(f"Using user: {user.email}")

        # Which templates to process
        keys = [options["template"]] if options["template"] else [t["key"] for t in TEMPLATES]
        unknown = [k for k in keys if k not in _TEMPLATE_PROMPTS]
        if unknown:
            raise CommandError(f"Unknown template key(s): {', '.join(unknown)}")

        if options["clear"]:
            deleted, _ = WorkflowPromptSuggestion.objects.filter(
                template_key__in=keys
            ).delete()
            self.stdout.write(self.style.WARNING(f"Cleared {deleted} existing suggestions"))

        count = options["count"]

        for key in keys:
            self.stdout.write(f"Generating {count} suggestions for '{key}'…")
            user_prompt = _TEMPLATE_PROMPTS[key].format(count=count)
            messages = [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_prompt},
            ]
            try:
                raw = _call_chat(user, messages)
            except CommandError:
                raise
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  Failed: {exc}"))
                continue

            try:
                suggestions = _parse_suggestions(raw)
            except (json.JSONDecodeError, ValueError) as exc:
                self.stdout.write(self.style.ERROR(f"  Could not parse response: {exc}"))
                self.stdout.write(f"  Raw: {raw[:300]}")
                continue

            objs = [
                WorkflowPromptSuggestion(template_key=key, text=s)
                for s in suggestions
            ]
            WorkflowPromptSuggestion.objects.bulk_create(objs)
            self.stdout.write(
                self.style.SUCCESS(f"  Saved {len(objs)} suggestions for '{key}'")
            )

        self.stdout.write(self.style.SUCCESS("Done."))
