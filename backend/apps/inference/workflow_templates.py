"""Curated, ready-to-run workflow templates (PRD 10).

Each template is a small DAG a user can seed with a few inputs and run — the
engine fans out, chains modalities, and produces all the media. Templates are
**portable**: inference steps declare a `type` (modality) but *omit* the model,
so the engine resolves whatever model the running user can actually route to
(see workflows._enqueue_step_jobs / jobs.auto_model_for). That's what lets the
same template work for any user with any compatible provider.

Inputs are declared with a tiny schema the frontend renders into a form:
  {name, label, type: text|textarea|number|select, default, placeholder,
   required, min, max, options}

Templates reference inputs via `{{inputs.<name>}}` and chain steps via
`{{steps.<id>.output...}}`, exactly like a hand-written spec.
"""
from copy import deepcopy


def _t(key, title, description, icon, inputs, steps, name=None):
    return {
        "key": key,
        "title": title,
        "description": description,
        "icon": icon,
        "inputs": inputs,
        "spec": {"name": name or title, "steps": steps},
    }


# A reusable instruction nudging the LLM to answer with strict JSON so the
# `extract: json` step can hand structured data to a fan-out.
_JSON_NOTE = " Respond with ONLY valid JSON, no prose, no code fences."


TEMPLATES = [
    _t(
        key="illustrated-story",
        title="Illustrated story",
        description="Write a short story about your topic, break it into scenes, "
                    "and generate an illustration for each — then review before finishing.",
        icon="BookOpen",
        inputs=[
            {"name": "topic", "label": "Story topic", "type": "text", "required": True,
             "placeholder": "a lighthouse keeper who befriends a whale"},
            {"name": "scenes", "label": "Number of scenes", "type": "number",
             "default": 4, "min": 1, "max": 8},
            {"name": "style", "label": "Illustration style", "type": "text",
             "default": "soft watercolor, warm light"},
        ],
        steps=[
            {"id": "outline", "kind": "inference", "type": "chat", "title": "Write & split into scenes",
             "extract": "json",
             "body": {"messages": [{"role": "user", "content":
                "Write a short illustrated story about: {{inputs.topic}}. "
                "Split it into exactly {{inputs.scenes}} scenes. For each scene give a "
                "2-3 sentence narration and a vivid single-sentence image prompt in the "
                "style: {{inputs.style}}. "
                "Return JSON: {\"scenes\":[{\"narration\":\"...\",\"image_prompt\":\"...\"}]}." + _JSON_NOTE}]}},
            {"id": "illustrations", "kind": "map", "type": "image", "title": "Illustrate each scene",
             "over": "{{steps.outline.output.scenes}}",
             "body": {"prompt": "{{item.image_prompt}}"}},
            {"id": "review", "kind": "gate", "title": "Review illustrations",
             "depends_on": ["illustrations"]},
        ],
    ),
    _t(
        key="image-variations",
        title="Image idea explorer",
        description="Turn one subject into several distinct image concepts, then render them all.",
        icon="Images",
        inputs=[
            {"name": "subject", "label": "Subject", "type": "text", "required": True,
             "placeholder": "a cozy reading nook"},
            {"name": "count", "label": "How many variations", "type": "number",
             "default": 4, "min": 1, "max": 8},
            {"name": "vibe", "label": "Vibe / constraints", "type": "text",
             "default": "cinematic, highly detailed"},
        ],
        steps=[
            {"id": "prompts", "kind": "inference", "type": "chat", "title": "Brainstorm prompts",
             "extract": "json",
             "body": {"messages": [{"role": "user", "content":
                "Give {{inputs.count}} distinct, creative image-generation prompts for: "
                "{{inputs.subject}} ({{inputs.vibe}}). Vary composition, lighting and angle. "
                "Return JSON: {\"prompts\":[\"...\"]}." + _JSON_NOTE}]}},
            {"id": "images", "kind": "map", "type": "image", "title": "Render variations",
             "over": "{{steps.prompts.output.prompts}}",
             "body": {"prompt": "{{item}}"}},
        ],
    ),
    _t(
        key="storyboard-to-video",
        title="Storyboard to video",
        description="Plan a few shots from a concept, illustrate each as a frame, then "
                    "animate each frame into a clip (image-to-video, so motion matches "
                    "the picture and keeps its aspect ratio).",
        icon="Clapperboard",
        inputs=[
            {"name": "concept", "label": "Concept", "type": "textarea", "required": True,
             "placeholder": "a seed sprouting into a glowing tree, time-lapse"},
            {"name": "shots", "label": "Number of shots", "type": "number",
             "default": 3, "min": 1, "max": 5},
            {"name": "size", "label": "Frame size (square, px)", "type": "number",
             "default": 768, "min": 256, "max": 1024},
        ],
        steps=[
            {"id": "board", "kind": "inference", "type": "chat", "title": "Plan the shots",
             "extract": "json",
             "body": {"messages": [{"role": "user", "content":
                "Storyboard this concept into {{inputs.shots}} shots: {{inputs.concept}}. "
                "For each shot give an `image_prompt` (the first frame, square composition) "
                "and a short `motion` description for how it should animate. "
                "Return JSON: {\"shots\":[{\"image_prompt\":\"...\",\"motion\":\"...\"}]}." + _JSON_NOTE}]}},
            {"id": "frames", "kind": "map", "type": "image", "title": "Render first frames",
             "over": "{{steps.board.output.shots}}",
             "body": {"prompt": "{{item.image_prompt}}",
                      "size": "{{inputs.size}}x{{inputs.size}}"}},
            {"id": "review", "kind": "gate", "title": "Approve frames", "depends_on": ["frames"]},
            # Pair each shot (its motion) with its rendered frame (its asset id),
            # gated behind the review so clips only run after approval.
            {"id": "shots_with_frames", "kind": "transform", "op": "zip", "title": "Pair frames + motion",
             "depends_on": ["review"],
             "inputs": ["{{steps.board.output.shots}}", "{{steps.frames.output}}"]},
            {"id": "clips", "kind": "map", "type": "video", "title": "Animate each frame",
             "over": "{{steps.shots_with_frames.output}}",
             "body": {"prompt": "{{item.0.motion}}",
                      "image_asset_id": "{{item.1.asset_id}}",
                      "width": "{{inputs.size}}", "height": "{{inputs.size}}"}},
        ],
    ),
    _t(
        key="miniature-construction-timelapse",
        title="Miniature construction timelapse",
        description="Turn one concept into a cozy tilt-shift scene of tiny workers "
                    "building it, then animate a smooth time-lapse of the construction.",
        icon="HardHat",
        inputs=[
            {"name": "subject", "label": "What's being built", "type": "text", "required": True,
             "placeholder": "a gazebo"},
            {"name": "size", "label": "Frame size (square, px)", "type": "number",
             "default": 768, "min": 256, "max": 1024},
            {"name": "seconds", "label": "Clip length (seconds)", "type": "number",
             "default": 5, "min": 2, "max": 12},
        ],
        steps=[
            {"id": "plan", "kind": "inference", "type": "chat", "title": "Art-direct the scene",
             "extract": "json",
             "body": {"messages": [{"role": "user", "content":
                "You are art-directing a COZY MINIATURE CONSTRUCTION TIME-LAPSE shot as tilt-shift "
                "faux-miniature photography. The thing being built is: {{inputs.subject}}. Give two "
                "prompts. `image_prompt`: a vivid one-paragraph FIRST-FRAME prompt of an adorable "
                "miniature construction site where tiny model workers, mini cranes, scaffolding and "
                "toy machinery are building {{inputs.subject}} — tilt-shift, shallow depth of field, "
                "warm cozy light, diorama feel, highly detailed. `video_prompt`: a short motion prompt "
                "for a smooth time-lapse of the {{inputs.subject}} coming together — workers bustling, "
                "the structure rising piece by piece, light and shadows shifting through the day. "
                "Return JSON: {\"image_prompt\":\"...\",\"video_prompt\":\"...\"}." + _JSON_NOTE}]}},
            {"id": "frame", "kind": "inference", "type": "image", "title": "Render the first frame",
             "body": {"prompt": "{{steps.plan.output.image_prompt}}, tilt-shift miniature photography, "
                      "faux-model diorama, shallow depth of field, cozy warm lighting, highly detailed",
                      "size": "{{inputs.size}}x{{inputs.size}}"}},
            {"id": "clip", "kind": "inference", "type": "video", "title": "Animate the time-lapse",
             "body": {"prompt": "{{steps.plan.output.video_prompt}}, smooth construction time-lapse, "
                      "tilt-shift miniature look",
                      "image_asset_id": "{{steps.frame.output.asset_id}}",
                      "width": "{{inputs.size}}", "height": "{{inputs.size}}",
                      "duration": "{{inputs.seconds}}"}},
        ],
    ),
    _t(
        key="song-and-cover",
        title="Song + cover art",
        description="Write lyrics and a music brief, then generate the track and its cover art together.",
        icon="Music",
        inputs=[
            {"name": "theme", "label": "Theme", "type": "text", "required": True,
             "placeholder": "late-night drive through neon city rain"},
            {"name": "genre", "label": "Genre", "type": "text", "default": "synthwave"},
        ],
        steps=[
            {"id": "brief", "kind": "inference", "type": "chat", "title": "Write lyrics & brief",
             "extract": "json",
             "body": {"messages": [{"role": "user", "content":
                "Create a {{inputs.genre}} song about: {{inputs.theme}}. "
                "Return JSON: {\"music_prompt\":\"a short style/production brief\","
                "\"lyrics\":\"a few short verses\",\"cover_prompt\":\"an album-cover image prompt\"}." + _JSON_NOTE}]}},
            {"id": "track", "kind": "inference", "type": "music", "title": "Generate the track",
             "body": {"prompt": "{{steps.brief.output.music_prompt}}",
                      "lyrics": "{{steps.brief.output.lyrics}}"}},
            {"id": "cover", "kind": "inference", "type": "image", "title": "Generate cover art",
             "body": {"prompt": "{{steps.brief.output.cover_prompt}}"}},
        ],
    ),
    _t(
        key="narrated-explainer",
        title="Narrated explainer",
        description="Turn a topic into a short script, then narrate each line with text-to-speech.",
        icon="Mic",
        inputs=[
            {"name": "topic", "label": "Topic to explain", "type": "text", "required": True,
             "placeholder": "how lighthouses work"},
            {"name": "lines", "label": "Number of lines", "type": "number",
             "default": 4, "min": 1, "max": 8},
        ],
        steps=[
            {"id": "script", "kind": "inference", "type": "chat", "title": "Write the script",
             "extract": "json",
             "body": {"messages": [{"role": "user", "content":
                "Write a friendly {{inputs.lines}}-line spoken explainer about: {{inputs.topic}}. "
                "Each line should be one or two sentences. "
                "Return JSON: {\"lines\":[\"...\"]}." + _JSON_NOTE}]}},
            {"id": "narration", "kind": "map", "type": "tts", "title": "Narrate each line",
             "over": "{{steps.script.output.lines}}",
             "body": {"input": "{{item}}"}},
        ],
    ),
    _t(
        key="url-to-video",
        title="URL → narrated video",
        description="Scrape an article, turn it into a two-host dialog, voice and "
                    "illustrate each section, then compose a narrated video. "
                    "(Needs providers for the scrape, speech and video-compose "
                    "services — see PRD 12.)",
        icon="Newspaper",
        inputs=[
            {"name": "url", "label": "Article URL", "type": "text", "required": True,
             "placeholder": "https://example.com/an-interesting-post"},
            {"name": "style", "label": "Illustration style", "type": "text",
             "default": "clean editorial illustration, soft light"},
        ],
        steps=[
            {"id": "fetch", "kind": "inference", "type": "scrape", "title": "Scrape the article",
             "body": {"url": "{{inputs.url}}"}},
            {"id": "script", "kind": "inference", "type": "chat", "title": "Write a 2-host dialog",
             "body": {"messages": [{"role": "user", "content":
                "Turn this article into a lively two-host podcast dialog. Use exactly "
                "two speakers, tagging each line [S1] or [S2], one line per turn, no "
                "prose around it.\n\nARTICLE:\n{{steps.fetch.output.text}}"}]}},
            {"id": "sections", "kind": "transform", "op": "split_sections", "title": "Group into sections",
             "input": "{{steps.script.output.text}}", "size": 2},
            {"id": "speech", "kind": "map", "type": "tts", "title": "Voice each section",
             "over": "{{steps.sections.output}}",
             "body": {"input": "{{item.text}}"}},
            {"id": "art", "kind": "map", "type": "image", "title": "Illustrate each section",
             "over": "{{steps.sections.output}}",
             "body": {"prompt": "{{inputs.style}} — {{item.text}}"}},
            {"id": "review", "kind": "gate", "title": "Review before composing",
             "depends_on": ["speech", "art"]},
            {"id": "video", "kind": "inference", "type": "compose", "title": "Compose the video",
             "depends_on": ["review"],
             # Provenance: the finished video traces back to every section's
             # audio and image (PRD 12 §5.1).
             "derive_from": ["{{steps.speech.output}}", "{{steps.art.output}}"],
             "body": {"audio": "{{steps.speech.output}}",
                      "images": "{{steps.art.output}}"}},
        ],
    ),
]

_BY_KEY = {t["key"]: t for t in TEMPLATES}


def list_templates():
    """Public, form-renderable view of the templates (no internal spec needed
    by the gallery, but included so an agent can introspect)."""
    out = []
    for t in TEMPLATES:
        out.append({
            "key": t["key"], "title": t["title"], "description": t["description"],
            "icon": t["icon"], "inputs": t["inputs"],
            "step_count": len(t["spec"]["steps"]),
        })
    return out


def get_template(key):
    return _BY_KEY.get(key)


def clean_inputs(fields, inputs):
    """Validate required inputs and coerce number fields against an input
    ``fields`` schema (the ``{name,label,type,default,required,min,max}`` shape
    templates and saved workflows both use). Returns (cleaned, error). Shared by
    curated templates and PRD 11 saved-workflow runs."""
    cleaned = {}
    for field in fields or []:
        name = field.get("name")
        if not name:
            continue
        val = inputs.get(name) if isinstance(inputs, dict) else None
        if val in (None, "") and field.get("default") is not None:
            val = field["default"]
        if val in (None, "") and field.get("required"):
            return None, f"`{field.get('label') or name}` is required."
        if field.get("type") == "number" and val not in (None, ""):
            try:
                val = int(val)
            except (TypeError, ValueError):
                return None, f"`{field.get('label') or name}` must be a number."
            lo, hi = field.get("min"), field.get("max")
            if lo is not None:
                val = max(lo, val)
            if hi is not None:
                val = min(hi, val)
        cleaned[name] = val
    return cleaned, None


def build_spec(key, inputs):
    """Return (spec, name, cleaned_inputs, error). Validates required inputs and
    coerces number fields; the spec + cleaned inputs are ready to hand to
    workflows.start_run."""
    t = _BY_KEY.get(key)
    if t is None:
        return None, None, None, f"Unknown template {key!r}."
    cleaned, err = clean_inputs(t["inputs"], inputs)
    if err:
        return None, None, None, err
    return deepcopy(t["spec"]), t["title"], cleaned, None
