"""Living, git-versioned tracker for the Media Pipeline & Narration Studio
programme (see docs/prd/12-media-pipeline-and-narration-studio.md).

This module is the **source of truth for status**; the PRD is the prose behind
it. It is served read-only to staff by ``AdminRoadmapView`` (/api/admin/roadmap/)
and rendered at /dashboard/admin/roadmap. Keeping it as a plain Python literal
(rather than a DB table) means progress is reviewed in PRs, travels with the
code, and survives any interruption — edit a task's ``status`` here and the admin
page reflects it on next load.

Update protocol: when a task lands, flip its ``status`` and add a dated line to
``PROGRESS_LOG``. Statuses: "planned" | "in_progress" | "blocked" | "done".

A future public roadmap (PRD 12 V5) can reuse ``roadmap_payload()`` with
``include_internal=False`` to drop notes/log and the staff gate.
"""

from __future__ import annotations

# --- status vocabulary -------------------------------------------------------

STATUS_PLANNED = "planned"
STATUS_IN_PROGRESS = "in_progress"
STATUS_BLOCKED = "blocked"
STATUS_DONE = "done"

_STATUS_ORDER = {
    STATUS_DONE: 0,
    STATUS_IN_PROGRESS: 1,
    STATUS_BLOCKED: 2,
    STATUS_PLANNED: 3,
}

# --- the roadmap ------------------------------------------------------------
# Each phase: id, title, headline, status, gate (proof of success), tracks A/B,
# and a list of tasks. Each task: id, title, status, note (optional).

ROADMAP_META = {
    "title": "Media Pipeline & Narration Studio",
    "prd": "docs/prd/12-media-pipeline-and-narration-studio.md",
    "updated": "2026-06-15",
    "summary": (
        "Adapt two of Brian's repos — hn.fm (URL→narrated/subtitled/illustrated "
        "video pipeline) and inference-club-studio (the Narrations review app) — "
        "into inference.club, expressed on the existing async-job + workflow "
        "engine. Track A is the headless media pipeline (new node kinds + a "
        "provenance-bearing media-asset model); Track B is the human-in-the-loop "
        "Narration Studio (retakes, trim, clean, Dia voices, dynamic image "
        "series). Every artifact traces back to its parts and any node re-runs."
    ),
    "tracks": {
        "A": "Media Pipeline (from hn.fm)",
        "B": "Narration Studio (from inference-club-studio)",
        "meta": "Admin roadmap & docs",
    },
}

PHASES = [
    {
        "id": "v0-foundations",
        "phase": "V0",
        "title": "Foundations: media assets, provenance & core nodes",
        "track": "A",
        "status": STATUS_PLANNED,
        "gate": (
            "A saved workflow takes a URL → scraped doc → (canned narration) → "
            "slideshow MP4, fully re-runnable per node."
        ),
        "tasks": [
            {"id": "media-asset-model", "title": "MediaAsset provenance: derived_from M2M + DOC/SUBTITLE kinds + record_derivation() + migration 0028", "status": STATUS_DONE, "note": "Extended the existing MediaAsset model rather than adding a new one."},
            {"id": "asset-api", "title": "GET /v1/assets/<id> (metadata + provenance) + MediaAssetDetailSerializer + useAsyncJobs.getAsset", "status": STATUS_DONE, "note": "6 tests in test_media_assets.py, all green."},
            {"id": "steps-emit-assets", "title": "Workflow steps emit MediaAsset ids + record provenance edges (vs transient results)", "status": STATUS_DONE, "note": "on_job_finished resolves a step's `derive_from` refs and links produced assets via record_derivation(); builder has a Derived-from field. _extract_asset_ids + integration tests green."},
            {"id": "scrape-node", "title": "`scrape` node kind + `scrape` manifest service type (Firecrawl via agent)", "status": STATUS_DONE, "note": "FULL STACK: Firecrawl deployed+proven in k3s (uses cluster vLLM); agent serveScrape (3 tests); inference.club SCRAPE modality — ScrapeView /v1/scrape + _run_scrape/_rerun_scrape storing OUTPUT_DOC + _job_output exposing markdown as text + async/queue support (6 tests); playground page /dashboard/playground/scrape. Goes live once the agent is rebuilt/redeployed (or run locally) so it routes /v1/scrape."},
            {"id": "transcribe-node", "title": "`transcribe` node wrapping existing STT → text + word timestamps", "status": STATUS_IN_PROGRESS, "note": "Routes to existing STT (transcribe→STT/stt, /v1/audio/transcriptions). Authorable + validates; the JSON/asset-ref word-timestamp runner is the remaining agent work."},
            {"id": "compose-node", "title": "`compose` node + `render` service: FFmpeg slideshow (images+audio) → MP4", "status": STATUS_DONE, "note": "DONE: render.py renders centrally on the worker (no provider) — pairs per-section image+audio, builds a 720p narrated slideshow MP4 (each still held for its audio's length), stores OUTPUT_VIDEO + records provenance. New CENTRAL_TYPES dispatch path in jobs.py (RENDER claimed provider-free under RENDER_MAX_CONCURRENT), ComposeView POST /v1/videos/compose (always async), _rerun_render runner. 6 tests in test_compose.py (real ffmpeg). ffmpeg already in the runtime image."},
            {"id": "v0-tests", "title": "End-to-end test: URL → doc → canned audio → MP4, per-node rerun", "status": STATUS_DONE, "note": "DONE: test_async_jobs.TestUrlToVideoEndToEnd runs the whole url-to-video graph (scrape→dialog→split→tts+image fan-out→gate→compose) with mocked upstream providers and REAL central FFmpeg, asserting a captioned MP4 that traces back to every section's audio+image. Also covers preflight graceful-fail (409 services_unavailable when providers are missing). 54 tests green."},
        ],
    },
    {
        "id": "v1-dialog-audio",
        "phase": "V1",
        "title": "Dialog & audio pipeline",
        "track": "A",
        "status": STATUS_PLANNED,
        "gate": (
            "URL → [S1]/[S2] script → Dia-cloned, StudioVoice-cleaned, stitched "
            "narration track."
        ),
        "tasks": [
            {"id": "dialog-node", "title": "`dialog` node: LLM → [S1]/[S2] script via response_schema (structured)", "status": STATUS_PLANNED},
            {"id": "section-split", "title": "Section-split transform (2 dialog lines → 1 section) + mapping to assets", "status": STATUS_DONE, "note": "`split_sections` op in _run_transform → [{index,lines,text}]; builder inspector + 4 tests."},
            {"id": "tts-clone-map", "title": "`tts-clone`: per-section Dia voice (map over sections) → audio assets", "status": STATUS_DONE, "note": "DONE: `voice` workflow step type (VOICE→Dia via /v1/voice/generations) + async _rerun_voice runner (JOB_SERVICE_TYPE/_RETRY_RUNNERS, tts capacity pool). url-to-video's speech map now narrates each section's [S1]/[S2] dialogue with Dia, passing the SAME `voice_seed` (template input, default 42) to every section so the voice stays consistent. Verified live: VOICE job → club-host → Dia, seed honored, OUTPUT_AUDIO stored. Sample-based cloning stays on the sync VoiceGenerationsView (needs an upload)."},
            {"id": "clean-node", "title": "`clean` node + `audio-enhance` service (StudioVoice), keep original separate", "status": STATUS_DONE, "note": "DONE: async _rerun_enhance runner (ENHANCE→agent /audio/enhance→Maxine Studio Voice) reads the upstream audio asset by id, stores the cleaned result as a NEW OUTPUT_AUDIO (original kept separate). Registered in _RETRY_RUNNERS/_RETRY_SERVICE_TYPE/JOB_SERVICE_TYPE. url-to-video now has a `clean` map step over the Dia speech output; compose uses the cleaned track (provenance video→clean→speech). studio-voice deployed in-cluster (a1, HTTP bridge). Covered by the e2e test (clean jobs PROCESSED, cleaned OUTPUT_AUDIO)."},
            {"id": "stitch-node", "title": "`stitch` transform: pydub concat + section offsets/timeline", "status": STATUS_PLANNED},
            {"id": "v1-tests", "title": "Tests: dialog→sections→tts→clean→stitch with provenance assertions", "status": STATUS_PLANNED},
        ],
    },
    {
        "id": "v2-subtitles-images",
        "phase": "V2",
        "title": "Subtitles & illustrated video",
        "track": "A",
        "status": STATUS_PLANNED,
        "gate": (
            "The full hn.fm flow as one inference.club workflow: URL → narrated, "
            "subtitled, illustrated MP4."
        ),
        "tasks": [
            {"id": "subtitle-node", "title": "`subtitle` transform: word timestamps → ASS/VTT (word-synced)", "status": STATUS_IN_PROGRESS, "note": "VTT+ASS rendering shipped (`subtitle` op, 5 tests); persisting the result as an OUTPUT_SUBTITLE asset is pending the compose/agent path."},
            {"id": "image-prompt-node", "title": "Per-section image-prompt LLM node", "status": STATUS_PLANNED},
            {"id": "image-series-map", "title": "`image-series`: IMAGE map over sections, timeline-aligned to audio", "status": STATUS_PLANNED},
            {"id": "compose-full", "title": "`compose` upgrade: images + audio + subtitles + timeline → final MP4", "status": STATUS_DONE, "note": "DONE: compose now burns per-section captions into each clip (ASS subtitles filter, in the same encode pass so concat stays lossless). The url-to-video template passes each section's dialog text as `captions`, aligned to the audio/image order. Word-level karaoke subtitles (from the `subtitle` op's word timestamps) remain a future polish, but section captions are burned in. Covered by the end-to-end test (asserts metadata.captions)."},
            {"id": "pipeline-template", "title": "Ship 'URL → video' workflow template in the gallery", "status": STATUS_DONE, "note": "`url-to-video` template (scrape→dialog→split_sections→tts+image maps→compose w/ derive_from); validates via validate_spec. A test now guards every template. Runs once media providers exist."},
        ],
    },
    {
        "id": "v3-narration-studio",
        "phase": "V3",
        "title": "Narration Studio (review app)",
        "track": "B",
        "status": STATUS_PLANNED,
        "gate": "A user hand-builds & polishes an episode in the Studio and renders it.",
        "tasks": [
            {"id": "episode-models", "title": "Episode / Segment / Variant / ImageSeries / ImageFrame models + migrations", "status": STATUS_IN_PROGRESS, "note": "Episode/Segment/Variant shipped (migration 0030): takes/variants, selected_variant, per-segment voice override, words, separate cleaned_audio. ImageSeries/ImageFrame come with the dynamic-image-series task."},
            {"id": "episode-api", "title": "Episode/Segment CRUD + reorder API + serializers + composable", "status": STATUS_IN_PROGRESS, "note": "/v1/episodes + /v1/segments CRUD, reorder, edit-undo stash, variant select (studio_views/studio_serializers); 10 tests green. Frontend composable + studio shell pending."},
            {"id": "studio-shell", "title": "/dashboard/studio shell: segment list, reorder, inline edit, status", "status": STATUS_PLANNED},
            {"id": "timeline-waveform", "title": "Waveform timeline + word-level highlight + seek (from transcribe)", "status": STATUS_PLANNED},
            {"id": "retakes", "title": "Retakes/variants: regenerate, A/B player, select active, auto-fallback", "status": STATUS_PLANNED},
            {"id": "trim-panel", "title": "Headspace trim: drag-handle waveform, preview/apply, auto re-transcribe", "status": STATUS_PLANNED},
            {"id": "clean-toggle", "title": "StudioVoice clean toggle (cleaned-vs-original, original preserved)", "status": STATUS_PLANNED},
            {"id": "voices-dialog", "title": "Dia voice-sample manager + per-segment override (reuse PRD 09 VoiceSample)", "status": STATUS_PLANNED},
            {"id": "dynamic-image-series", "title": "Dynamic image-series panel: LLM plan, i2i continuity, suggest-next", "status": STATUS_PLANNED},
            {"id": "export-render", "title": "Export bar: concat/gaps/fade/normalize → audio; 'send to compose' → video", "status": STATUS_PLANNED},
        ],
    },
    {
        "id": "v4-advanced-compositing",
        "phase": "V4",
        "title": "Advanced compositing & 3D",
        "track": "B",
        "status": STATUS_PLANNED,
        "gate": (
            "An episode rendered with title cards + a 3D scene + music; Blender "
            "export opens."
        ),
        "tasks": [
            {"id": "hyperframes", "title": "HyperFrames title cards / lower-thirds / animated text / alpha overlays", "status": STATUS_PLANNED},
            {"id": "image-to-video", "title": "Per-section image→video (LTX-2) instead of static slides", "status": STATUS_PLANNED},
            {"id": "frame-interp", "title": "`frame-interp` service + effects/filters", "status": STATUS_PLANNED},
            {"id": "music-bed", "title": "Music bed (existing MUSIC modality) ducked under narration", "status": STATUS_DONE, "note": "DONE (compose side): render.mix_music_bed lays an optional music track under the narration — looped to length, attenuated, and side-chain-ducked by the speech (swells in the gaps). compose accepts an optional `music` asset (ComposeView + RENDER payload); the video records music in metadata + provenance. Kept OFF the default url-to-video template so it doesn't trip preflight while acestep is scaled to 0. Real-ffmpeg test in test_compose.py."},
            {"id": "threed-compositing", "title": "TRELLIS meshes + ThreeJS scenes composited into video (image+video+3D)", "status": STATUS_PLANNED},
            {"id": "blender-export", "title": "Blender export: episode → .blend + Python build script", "status": STATUS_PLANNED},
        ],
    },
    {
        "id": "v5-sharing-public-roadmap",
        "phase": "V5",
        "title": "Sharing & roadmap surfaces",
        "track": "meta",
        "status": STATUS_PLANNED,
        "gate": "Template gallery for these pipelines; public roadmap live.",
        "tasks": [
            {"id": "pipeline-templates", "title": "Template gallery entries for the media pipelines", "status": STATUS_PLANNED},
            {"id": "episode-sharing", "title": "Episode sharing/visibility (reuse PRD 01 sharing model)", "status": STATUS_PLANNED},
            {"id": "public-roadmap", "title": "Public roadmap reusing roadmap_payload(include_internal=False)", "status": STATUS_PLANNED},
        ],
    },
]

# Most recent first. Add a line whenever a task changes status.
PROGRESS_LOG = [
    {
        "date": "2026-06-15",
        "note": (
            "StudioVoice cleaning wired into url-to-video (V1 clean-node): every "
            "Dia narration clip now runs through Maxine Studio Voice before "
            "compose. Added the async _rerun_enhance runner (ENHANCE → agent "
            "/audio/enhance), a `clean` map step over the speech output, and "
            "repointed compose at the cleaned audio (original kept separate; "
            "provenance video→clean→speech). studio-voice is deployed in-cluster "
            "on a1 behind an HTTP bridge. 48 tests green. NOTE: the bridge's LAN "
            "hostPort 8090 on a1 wasn't reachable from the dev agent at "
            "integration time — works in-cluster, so prod is fine, but the local "
            "dev run needs a1:8090 reachable (pod recreate / node check)."
        ),
    },
    {
        "date": "2026-06-15",
        "note": (
            "url-to-video now narrates with Dia, not Riva (V1 tts-clone): added a "
            "`voice` workflow step type + async _rerun_voice runner routing "
            "VOICE→Dia (/v1/voice/generations), and switched the template's "
            "speech map to it. A `voice_seed` template input (default 42) is "
            "passed identically to every section so Dia's generated voice stays "
            "consistent across the whole video. Root cause it fixed: the old "
            "`type: tts` step hit the agent's Riva tts backend (magpie, scaled "
            "to 0) → connection refused; Dia only answers the voice-cloning "
            "path. Verified live end to end (VOICE job → club-host → Dia, seed "
            "honored, OUTPUT_AUDIO stored). 40 tests green. Also exposed "
            "firecrawl on a3's hostPort 3002 so the dev agent can reach scrape."
        ),
    },
    {
        "date": "2026-06-15",
        "note": (
            "V4 first slice — music bed: compose can now duck an optional music "
            "track under the narration (looped, attenuated, side-chain "
            "compressed by speech) via render.mix_music_bed; exposed as a "
            "`music` asset on compose/RENDER, recorded in metadata + "
            "provenance. Left off the default url-to-video template (acestep is "
            "scaled to 0, so requiring it would trip preflight). Also VERIFIED "
            "the home k3s cluster serves every modality url-to-video needs and "
            "the agent advertises them to api.inference.club: firecrawl=scrape, "
            "nemotron-omni=llm (vLLM), dia=tts, flux2-klein=image (acestep/"
            "music, magpie-tts, nemotron-asr, trellis2 are scaled to 0). The "
            "live run is gated only on deploying this branch — compose runs on "
            "the central worker, which still has the old code. 7 compose tests "
            "green."
        ),
    },
    {
        "date": "2026-06-15",
        "note": (
            "URL→video closed out (V0/V2 headless path): (1) a full-graph "
            "end-to-end test runs scrape→dialog→split→tts+image→gate→compose "
            "with mocked providers + REAL central FFmpeg, asserting a captioned "
            "MP4 with provenance; (2) compose burns per-section captions into "
            "each clip (ASS subtitles in the same encode pass; template feeds "
            "section text); (3) graceful-fail preflight — start_run now checks "
            "the user can route to a provider for every modality the workflow "
            "needs (RENDER excluded — it's central) and returns 409 "
            "services_unavailable listing what's missing, before spending any "
            "compute. 54 tests green."
        ),
    },
    {
        "date": "2026-06-15",
        "note": (
            "Compose lands — the last executable node in the URL→video graph. "
            "render.py renders centrally on the worker with FFmpeg (no provider): "
            "pairs each section's image + audio into a 720p slideshow MP4 (still "
            "held for its narration's length), stores OUTPUT_VIDEO + records "
            "provenance. New RENDER central-dispatch path in jobs.py (claimed "
            "provider-free under RENDER_MAX_CONCURRENT), ComposeView POST "
            "/v1/videos/compose, _rerun_render. Found & fixed a real hang: a 1x1 "
            "PNG fixture made FFmpeg's looped-image parser overflow and spin to "
            "the 600s timeout — switched the test to a real Pillow image. 6 "
            "compose tests + 39 regression green. The whole url-to-video template "
            "is now executable end to end (subtitle burn-in into the video is the "
            "one remaining compose enhancement)."
        ),
    },
    {
        "date": "2026-06-15",
        "note": (
            "Scrape end to end: rebuilt the agent with serveScrape (routes "
            "/v1/scrape → Firecrawl, 3 tests), and added the inference.club SCRAPE "
            "modality — /v1/scrape ScrapeView, _run_scrape/_rerun_scrape storing "
            "the markdown as an OUTPUT_DOC asset, workflow output exposing it as "
            "`text`, async/queue support, and a /dashboard/playground/scrape page. "
            "6 scrape tests + 45 regression green. Paste a link → markdown works "
            "in the app and feeds the url-to-video workflow's scrape node."
        ),
    },
    {
        "date": "2026-06-15",
        "note": (
            "V3 Narration Studio spine: Episode/Segment/Variant models "
            "(migration 0030) + owner-scoped CRUD API (/v1/episodes, /v1/segments, "
            "reorder, edit-undo stash, variant select). Clarified that `scrape` is "
            "an inference service — Firecrawl calls an LLM under the hood, default "
            "the local cluster vLLM via a service-URL env var. 10 studio tests "
            "green."
        ),
    },
    {
        "date": "2026-06-14",
        "note": (
            "Shipped the `url-to-video` gallery template — the whole hn.fm flow "
            "as one authorable graph (scrape → 2-host dialog → split_sections → "
            "TTS + image fan-out → compose, with derive_from provenance). Added "
            "a guard test that validates every shipped template; Newspaper icon "
            "registered. 67 tests green. Runs end-to-end once providers serve the "
            "scrape/speech/compose services."
        ),
    },
    {
        "date": "2026-06-14",
        "note": (
            "Wired steps-emit-assets provenance: a step's `derive_from` refs are "
            "resolved at job completion and its produced assets are linked via "
            "MediaAsset.record_derivation() (_extract_asset_ids handles ids / "
            "job-output dicts / map lists); builder gained a 'Derived from' "
            "field. Closes V0's spine. 59 tests green."
        ),
    },
    {
        "date": "2026-06-14",
        "note": (
            "Registered the media-pipeline modality vocabulary (PRD 12 option 1): "
            "SCRAPE/RENDER/ENHANCE inference types + scrape/render/audio-enhance "
            "service types (migration 0029), engine routing (_ENDPOINT_TYPE/"
            "_SHORT_TYPE incl. transcribe→STT), manifest_validator acceptance, and "
            "builder modality options with a 'needs a provider' note. The "
            "scrape/transcribe/compose/clean nodes are now authorable and "
            "validate; agent-side runners are the remaining work. 12 media "
            "tests + 38 regression + 34 manifest/modality tests green."
        ),
    },
    {
        "date": "2026-06-14",
        "note": (
            "Added two inline media-pipeline transforms to the engine (no agent "
            "needed): `split_sections` (hn.fm 2-lines-per-section, V1) and "
            "`subtitle` (word timestamps → VTT/ASS, V2), both wired into the "
            "builder inspector. 9 new tests green; 38 workflow/job tests still "
            "green."
        ),
    },
    {
        "date": "2026-06-14",
        "note": (
            "V0 scaffold started: extended MediaAsset with a derived_from "
            "provenance graph + DOC/SUBTITLE kinds + record_derivation() "
            "(migration 0028), and shipped GET /v1/assets/<id> "
            "(MediaAssetDetailSerializer, useAsyncJobs.getAsset). 6 new tests "
            "green, 38 related tests still green. Next: scrape/transcribe/compose "
            "node kinds."
        ),
    },
    {
        "date": "2026-06-14",
        "note": (
            "Programme kicked off. Studied hn.fm and inference-club-studio; wrote "
            "PRD 12 and this tracker; shipped the staff-only admin roadmap page "
            "(/dashboard/admin/roadmap). No feature phases started yet."
        ),
    },
]


# --- derived payload --------------------------------------------------------

def _phase_progress(phase: dict) -> dict:
    tasks = phase.get("tasks", [])
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == STATUS_DONE)
    in_progress = sum(1 for t in tasks if t.get("status") == STATUS_IN_PROGRESS)
    return {"total": total, "done": done, "in_progress": in_progress}


def _derive_phase_status(phase: dict) -> str:
    """If a phase's own status is left "planned" but its tasks have moved,
    surface the real state so the board never lies."""
    declared = phase.get("status", STATUS_PLANNED)
    if declared != STATUS_PLANNED:
        return declared
    p = _phase_progress(phase)
    if p["total"] and p["done"] == p["total"]:
        return STATUS_DONE
    if p["in_progress"] or p["done"]:
        return STATUS_IN_PROGRESS
    return STATUS_PLANNED


def roadmap_payload(include_internal: bool = True) -> dict:
    """Serializable roadmap for the admin (and, later, public) surface.

    ``include_internal=False`` strips the progress log (future public view).
    """
    phases = []
    for phase in PHASES:
        prog = _phase_progress(phase)
        phases.append(
            {
                "id": phase["id"],
                "phase": phase["phase"],
                "title": phase["title"],
                "track": phase["track"],
                "status": _derive_phase_status(phase),
                "gate": phase["gate"],
                "progress": prog,
                "tasks": [
                    {
                        "id": t["id"],
                        "title": t["title"],
                        "status": t.get("status", STATUS_PLANNED),
                        "note": t.get("note", ""),
                    }
                    for t in phase.get("tasks", [])
                ],
            }
        )

    all_tasks = [t for p in PHASES for t in p.get("tasks", [])]
    totals = {
        "tasks": len(all_tasks),
        "done": sum(1 for t in all_tasks if t.get("status") == STATUS_DONE),
        "in_progress": sum(1 for t in all_tasks if t.get("status") == STATUS_IN_PROGRESS),
        "phases": len(PHASES),
        "phases_done": sum(1 for p in phases if p["status"] == STATUS_DONE),
    }

    payload = {
        "meta": ROADMAP_META,
        "totals": totals,
        "phases": phases,
    }
    if include_internal:
        payload["progress_log"] = PROGRESS_LOG
    return payload
