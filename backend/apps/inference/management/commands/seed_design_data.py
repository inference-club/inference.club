"""Seed deterministic design-test fixtures (dev-only).

Creates the ``designbot`` user plus one provider with a service/model per
modality, and PUBLIC, PROCESSED InferenceRequests covering every
inference_type (LLM, STT, TTS, MUSIC, IMAGE, MESH, VIDEO) with real media
assets (PNG/WAV/MP4/GLB) generated in-code — so Playwright design tests can
screenshot every page fully populated. Also seeds two worst-case overflow
requests (unbroken 200-300 char tokens, max-length model name) as
side-scroll regression fixtures, and a collection / stars / bookmarks.

Idempotent: rows are keyed by stable identifiers (email, provider name,
deterministic share_tokens), so re-running updates in place. Refuses to run
unless settings.DEBUG is True (override with --force).
"""

import colorsys
import io
import json
import math
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.inference.models import (
    Bookmark,
    Collection,
    CollectionItem,
    InferenceRequest,
    MediaAsset,
    Provider,
    ProviderModel,
    ProviderService,
    ServiceManifest,
    Star,
    link_catalog_model,
)

DESIGNBOT_EMAIL = "designbot@inference.club"
DESIGNBOT_PASSWORD = "designbot-pass-1"
DESIGNBOT_LOGIN = "designbot"
PROVIDER_NAME = "design-rig"

# (service name, service_type, engine, served model name, hf repo id)
SERVICES = [
    ("vllm-main", "llm", "vllm", "qwen/qwen3-30b-a3b", "Qwen/Qwen3-30B-A3B"),
    ("whisper-stt", "stt", "other", "openai/whisper-large-v3", "openai/whisper-large-v3"),
    ("kokoro-tts", "tts", "other", "hexgrad/kokoro-82m", "hexgrad/Kokoro-82M"),
    ("flux-image", "image", "other", "black-forest-labs/flux.1-schnell", "black-forest-labs/FLUX.1-schnell"),
    ("trellis-mesh", "mesh", "other", "microsoft/trellis-image-large", "microsoft/TRELLIS-image-large"),
    ("ace-step-music", "music", "other", "ace-step/ace-step-v1-3.5b", "ACE-Step/ACE-Step-v1-3.5B"),
    ("ltx-video", "video", "other", "lightricks/ltx-2", "Lightricks/LTX-2"),
]

# Side-scroll regression fixtures: long unbroken tokens that must not widen
# the cards. 120 'A's + a 180-char URL = one 300-char unbreakable run.
_LONG_URL = "https://design.example.com/" + "a" * 153  # 180 chars, no spaces
OVERFLOW_PROMPT = "A" * 120 + _LONG_URL
OVERFLOW_RESPONSE = "B" * 120 + _LONG_URL
OVERFLOW_MUSIC_PROMPT = ("hyperdetailed-cinematic-synthwave-" * 6)[:199] + "x"  # 200 chars, no spaces
# model_name is max_length=255
OVERFLOW_MODEL_NAME = "design/" + "x" * 248  # 255 chars

TRANSCRIPT = (
    "Welcome to inference club, where members share their home GPUs to run "
    "open models for each other across the network."
)


# --- media generators --------------------------------------------------------


def make_png(hue: float, size: int = 512) -> bytes:
    """A solid vertical lightness gradient in the given hue (0..1)."""
    from PIL import Image

    raw = bytearray()
    for y in range(size):
        light = 0.22 + 0.55 * (y / (size - 1))
        r, g, b = colorsys.hls_to_rgb(hue, light, 0.85)
        raw += bytes((int(r * 255), int(g * 255), int(b * 255))) * size
    img = Image.frombytes("RGB", (size, size), bytes(raw))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def make_wav(seconds: float = 2.0, freq: float = 440.0, rate: int = 22050) -> bytes:
    """16-bit mono PCM sine tone."""
    n = int(seconds * rate)
    frames = bytearray()
    for i in range(n):
        sample = int(0.4 * 32767 * math.sin(2 * math.pi * freq * i / rate))
        frames += struct.pack("<h", sample)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def make_mp4() -> tuple[bytes, bool]:
    """A 2s 640x360 testsrc clip via ffmpeg; (bytes, real). Falls back to a
    1-byte placeholder when ffmpeg isn't installed."""
    if shutil.which("ffmpeg") is None:
        return b"\x00", False
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "design.mp4"
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "testsrc=duration=2:size=640x360:rate=24",
                "-pix_fmt", "yuv420p", str(out),
            ],
            capture_output=True,
        )
        if proc.returncode != 0 or not out.exists():
            return b"\x00", False
        return out.read_bytes(), True


def make_glb() -> bytes:
    """A minimal valid glTF 2.0 binary: one unit cube (POSITION + indices)."""
    positions = [
        (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5),
    ]
    indices = [
        0, 2, 1, 0, 3, 2,  # back
        4, 5, 6, 4, 6, 7,  # front
        0, 4, 7, 0, 7, 3,  # left
        1, 2, 6, 1, 6, 5,  # right
        0, 1, 5, 0, 5, 4,  # bottom
        3, 7, 6, 3, 6, 2,  # top
    ]
    pos_bytes = b"".join(struct.pack("<fff", *p) for p in positions)  # 96 B
    idx_bytes = b"".join(struct.pack("<H", i) for i in indices)  # 72 B
    bin_chunk = pos_bytes + idx_bytes
    bin_chunk += b"\x00" * (-len(bin_chunk) % 4)

    gltf = {
        "asset": {"version": "2.0", "generator": "seed_design_data"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "buffers": [{"byteLength": len(bin_chunk)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pos_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": len(pos_bytes), "byteLength": len(idx_bytes), "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0, "componentType": 5126, "count": len(positions),
                "type": "VEC3", "min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5],
            },
            {"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
        ],
    }
    json_chunk = json.dumps(gltf, separators=(",", ":")).encode()
    json_chunk += b" " * (-len(json_chunk) % 4)

    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    out = bytearray()
    out += struct.pack("<III", 0x46546C67, 2, total)  # magic 'glTF', version 2
    out += struct.pack("<II", len(json_chunk), 0x4E4F534A) + json_chunk  # 'JSON'
    out += struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk  # 'BIN\0'
    return bytes(out)


class Command(BaseCommand):
    help = (
        "Seed deterministic designbot fixtures (every modality + overflow "
        "cases) for Playwright design screenshots. Dev-only."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even when settings.DEBUG is False.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_design_data is a dev-only fixture command; refusing to "
                "run with DEBUG=False (use --force to override)."
            )

        user = self._seed_user()
        provider, models = self._seed_provider(user)
        requests = self._seed_requests(user, provider, models)
        self._seed_curation(user, requests)
        self._print_verification(user)

    # --- user ---------------------------------------------------------------

    def _seed_user(self):
        User = get_user_model()
        user, created = User.objects.get_or_create(email=DESIGNBOT_EMAIL)
        user.set_password(DESIGNBOT_PASSWORD)
        user.is_staff = True
        user.is_active = True
        user.public_profile_enabled = True
        user.default_request_visibility = "PUBLIC"
        # The custom user model has no username column; save() flips
        # profile_setup_complete from the (instance) attribute.
        user.username = DESIGNBOT_LOGIN
        user.save()

        # github_login is resolved from social_django's UserSocialAuth
        # (extra_data["login"]), not a user field — seed that association so
        # /designbot (the public profile) resolves.
        from social_django.models import UserSocialAuth

        social, _ = UserSocialAuth.objects.get_or_create(
            user=user, provider="github", defaults={"uid": "99000001"}
        )
        extra = dict(social.extra_data or {})
        extra["login"] = DESIGNBOT_LOGIN
        social.extra_data = extra
        social.save()

        self.stdout.write(
            f"{'Created' if created else 'Updated'} user {DESIGNBOT_EMAIL} "
            f"(staff, github_login={DESIGNBOT_LOGIN})"
        )
        return user

    # --- provider / services / models / manifest ------------------------------

    def _seed_provider(self, user):
        provider, _ = Provider.objects.update_or_create(
            user=user,
            name=PROVIDER_NAME,
            defaults={
                "tailnet_hostname": "design-rig-1",
                "agent_port": 443,
                "is_active": True,
                "accepting_requests": True,
                "registered_at": timezone.now(),
                "last_seen_at": timezone.now(),
            },
        )

        models: dict[str, ProviderModel] = {}
        manifest_services = []
        for svc_name, svc_type, engine, model_name, hf_repo in SERVICES:
            svc, _ = ProviderService.objects.update_or_create(
                provider=provider,
                name=svc_name,
                defaults={
                    "host_id": "design-host",
                    "engine": engine,
                    "service_type": svc_type,
                    "is_active": True,
                    "access_policy": ProviderService.ACCESS_AUTHENTICATED,
                },
            )
            pm, _ = ProviderModel.objects.update_or_create(
                provider=provider,
                name=model_name,
                defaults={
                    "service": svc,
                    "hf_repo_id": hf_repo,
                    "is_active": True,
                },
            )
            link_catalog_model(pm)
            pm.save()
            models[svc_type] = pm
            manifest_services.append(
                {
                    "name": svc_name,
                    "engine": engine,
                    "type": svc_type,
                    "url": "http://localhost:8000/v1",
                    "models": [{"id": model_name, "hf_repo_id": hf_repo}],
                }
            )

        parsed = {
            "schema_version": 1,
            "agent": {"name": PROVIDER_NAME},
            "hosts": [
                {
                    "id": "design-host",
                    "gpus": [{"model": "RTX 4090", "vram_gb": 24}],
                    "services": manifest_services,
                }
            ],
        }
        raw_yaml = (
            "schema_version: 1\n"
            f"agent: {{name: {PROVIDER_NAME}}}\n"
            "# Deterministic manifest seeded by seed_design_data.\n"
        )
        ServiceManifest.objects.update_or_create(
            provider=provider,
            defaults={
                "schema_version": 1,
                "raw_yaml": raw_yaml,
                "parsed": parsed,
                "is_valid": True,
                "validation_errors": [],
            },
        )
        self.stdout.write(
            f"Provider '{PROVIDER_NAME}' ready with {len(SERVICES)} services/models"
        )
        return provider, models

    # --- inference requests ----------------------------------------------------

    def _upsert_request(self, user, provider, token: str, **fields):
        """Idempotent request upsert keyed by a deterministic share_token."""
        ir = InferenceRequest.objects.filter(share_token=token).first()
        if ir is None:
            ir = InferenceRequest(share_token=token)
        ir.user = user
        ir.provider = provider
        ir.status = "PROCESSED"
        ir.visibility = "PUBLIC"
        for key, value in fields.items():
            setattr(ir, key, value)
        ir.save()
        return ir

    def _ensure_assets(self, ir, kind: str, builders):
        """Make sure ``ir`` has exactly len(builders) assets of ``kind``.
        ``builders`` is a list of (filename, bytes, content_type,
        duration_seconds, metadata) tuples. Existing matching sets are reused.
        Saves files exactly like openai_views does."""
        existing = list(ir.assets.filter(kind=kind).order_by("id"))
        if len(existing) == len(builders):
            return existing
        for asset in existing:
            asset.file.delete(save=False)
            asset.delete()
        created = []
        for name, data, content_type, duration, metadata in builders:
            asset = MediaAsset(
                user=ir.user,
                inference_request=ir,
                kind=kind,
                content_type=content_type,
                size_bytes=len(data),
                duration_seconds=duration,
                metadata=metadata or {},
            )
            asset.file.save(name, ContentFile(data), save=False)
            asset.save()
            created.append(asset)
        return created

    def _seed_requests(self, user, provider, models):
        now_ts = int(timezone.now().timestamp())
        requests: dict[str, InferenceRequest] = {}

        # --- LLM (messages, usage, reasoning) --------------------------------
        llm_model = models["llm"].name
        requests["llm"] = self._upsert_request(
            user, provider, "design-llm",
            inference_type="LLM",
            model_name=llm_model,
            payload={
                "model": llm_model,
                "messages": [
                    {"role": "system", "content": "You are a concise, helpful assistant."},
                    {
                        "role": "user",
                        "content": "Explain in two short paragraphs how a community "
                        "of home GPU owners can pool capacity to serve open models.",
                    },
                ],
                "stream": False,
            },
            results={
                "id": "chatcmpl-design-fixture",
                "object": "chat.completion",
                "created": now_ts,
                "model": llm_model,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": (
                                "A community of home GPU owners can pool capacity by "
                                "registering each machine as a provider on a shared "
                                "network. Requests are routed to whichever node is "
                                "online and serves the requested model, so idle "
                                "hardware earns its keep while members get access to "
                                "models bigger than any single rig could host.\n\n"
                                "Fair scheduling and per-service access controls keep "
                                "the pool healthy: operators decide who may route to "
                                "each service, and usage metering (tokens, seconds, "
                                "images) makes contributions visible on the leaderboard."
                            ),
                            "reasoning": (
                                "The user wants two short paragraphs. First paragraph: "
                                "the mechanics of pooling (registration, routing, "
                                "availability). Second paragraph: governance — access "
                                "policy and metering. Keep it concrete and brief."
                            ),
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 42,
                    "completion_tokens": 187,
                    "total_tokens": 229,
                },
            },
            latency_ms=2840,
            ttft_ms=310,
            prompt_tokens=42,
            completion_tokens=187,
            total_tokens=229,
        )

        # --- LLM overflow (side-scroll regression fixture) --------------------
        requests["llm_overflow"] = self._upsert_request(
            user, provider, "design-llm-overflow",
            inference_type="LLM",
            model_name=llm_model,
            payload={
                "model": llm_model,
                "messages": [{"role": "user", "content": OVERFLOW_PROMPT}],
                "stream": False,
            },
            results={
                "id": "chatcmpl-design-overflow",
                "object": "chat.completion",
                "created": now_ts,
                "model": llm_model,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": OVERFLOW_RESPONSE},
                    }
                ],
                "usage": {
                    "prompt_tokens": 90,
                    "completion_tokens": 90,
                    "total_tokens": 180,
                },
            },
            latency_ms=1430,
            ttft_ms=200,
            prompt_tokens=90,
            completion_tokens=90,
            total_tokens=180,
        )

        # --- STT (input audio + verbose_json transcript) -----------------------
        wav = make_wav()
        stt = self._upsert_request(
            user, provider, "design-stt",
            inference_type="STT",
            model_name=models["stt"].name,
            payload={
                "model": models["stt"].name,
                "filename": "welcome.wav",
                "content_type": "audio/wav",
                "size_bytes": len(wav),
                "response_format": "verbose_json",
                "language": "en",
                # Whisper conditioning prompt — also what the card's
                # prompt_preview renders for STT.
                "prompt": "A short welcome message about the inference.club GPU network.",
            },
            results={
                "text": TRANSCRIPT,
                "language": "english",
                "duration": 2.0,
                "segments": [
                    {"id": 0, "start": 0.0, "end": 1.1, "text": TRANSCRIPT[:64]},
                    {"id": 1, "start": 1.1, "end": 2.0, "text": TRANSCRIPT[64:]},
                ],
                "words": [
                    {
                        "word": w,
                        "start": round(i * 2.0 / len(TRANSCRIPT.split()), 3),
                        "end": round((i + 1) * 2.0 / len(TRANSCRIPT.split()), 3),
                    }
                    for i, w in enumerate(TRANSCRIPT.split())
                ],
            },
            latency_ms=950,
            audio_seconds=2.0,
        )
        (stt_asset,) = self._ensure_assets(
            stt, MediaAsset.INPUT_AUDIO,
            [("welcome.wav", wav, "audio/wav", 2.0, None)],
        )
        if stt.payload.get("asset_id") != stt_asset.id:
            stt.payload["asset_id"] = stt_asset.id
            stt.save(update_fields=["payload", "modified_on"])
        requests["stt"] = stt

        # --- TTS (output audio) -------------------------------------------------
        tts_text = "Welcome to inference club. Your request has been routed to a community node."
        tts = self._upsert_request(
            user, provider, "design-tts",
            inference_type="TTS",
            model_name=models["tts"].name,
            payload={
                "model": models["tts"].name,
                "input": tts_text,
                "voice": "af_heart",
                "language": "en-US",
                "response_format": "wav",
            },
            results={},  # filled with the asset id below
            latency_ms=1210,
            audio_seconds=2.0,
        )
        (tts_asset,) = self._ensure_assets(
            tts, MediaAsset.OUTPUT_AUDIO,
            [("speech.wav", make_wav(freq=523.25), "audio/wav", 2.0, None)],
        )
        tts.results = {
            "audio_asset_id": tts_asset.id,
            "content_type": "audio/wav",
            "voice": "af_heart",
            "characters": len(tts_text),
        }
        tts.save(update_fields=["results", "modified_on"])
        requests["tts"] = tts

        # --- MUSIC (output audio) ------------------------------------------------
        music_prompt = "warm lo-fi hip hop, dusty vinyl crackle, mellow rhodes chords, relaxed boom-bap drums"
        music_lyrics = "[verse]\nCity lights are fading low\nGPUs hum soft and slow\n[chorus]\nRun it on the club tonight"
        music = self._upsert_request(
            user, provider, "design-music",
            inference_type="MUSIC",
            model_name=models["music"].name,
            payload={
                "model": models["music"].name,
                "prompt": music_prompt,
                "lyrics": music_lyrics,
                "audio_duration": 2.0,
                "inference_steps": 27,
                "guidance_scale": 15,
                "seed": 4242,
                "use_random_seed": False,
                "audio_format": "wav",
                "bpm": 84,
                "key_scale": "C minor",
            },
            results={},
            latency_ms=6400,
            audio_seconds=2.0,
        )
        (music_asset,) = self._ensure_assets(
            music, MediaAsset.OUTPUT_AUDIO,
            [("song.wav", make_wav(freq=329.63), "audio/wav", 2.0, None)],
        )
        music.results = {
            "audio_asset_id": music_asset.id,
            "content_type": "audio/wav",
            "characters": len(music_prompt) + len(music_lyrics),
        }
        music.save(update_fields=["results", "modified_on"])
        requests["music"] = music

        # --- MUSIC #2 (second playlist track; gets cover art below) ------------
        music2_prompt = "uptempo synthwave with arpeggiated bass, neon pads, driving four-on-the-floor drums"
        music2 = self._upsert_request(
            user, provider, "design-music-2",
            inference_type="MUSIC",
            model_name=models["music"].name,
            payload={
                "model": models["music"].name,
                "prompt": music2_prompt,
                "lyrics": "",
                "audio_duration": 2.0,
                "inference_steps": 27,
                "guidance_scale": 15,
                "seed": 9001,
                "use_random_seed": False,
                "audio_format": "wav",
                "bpm": 118,
                "key_scale": "A minor",
            },
            results={},
            latency_ms=5980,
            audio_seconds=2.0,
        )
        (music2_asset,) = self._ensure_assets(
            music2, MediaAsset.OUTPUT_AUDIO,
            [("song.wav", make_wav(freq=440.0), "audio/wav", 2.0, None)],
        )
        music2.results = {
            "audio_asset_id": music2_asset.id,
            "content_type": "audio/wav",
            "characters": len(music2_prompt),
        }
        music2.save(update_fields=["results", "modified_on"])
        requests["music_2"] = music2

        # --- MUSIC overflow (unbroken prompt + max-length model name) -----------
        music_of = self._upsert_request(
            user, provider, "design-music-overflow",
            inference_type="MUSIC",
            model_name=OVERFLOW_MODEL_NAME,
            payload={
                "model": OVERFLOW_MODEL_NAME,
                "prompt": OVERFLOW_MUSIC_PROMPT,
                "lyrics": "",
                "audio_duration": 2.0,
                "inference_steps": 27,
                "guidance_scale": 15,
                "seed": 7,
                "use_random_seed": False,
                "audio_format": "wav",
                "bpm": None,
                "key_scale": "",
            },
            results={},
            latency_ms=5120,
            audio_seconds=2.0,
        )
        (music_of_asset,) = self._ensure_assets(
            music_of, MediaAsset.OUTPUT_AUDIO,
            [("song.wav", make_wav(freq=392.0), "audio/wav", 2.0, None)],
        )
        music_of.results = {
            "audio_asset_id": music_of_asset.id,
            "content_type": "audio/wav",
            "characters": len(OVERFLOW_MUSIC_PROMPT),
        }
        music_of.save(update_fields=["results", "modified_on"])
        requests["music_overflow"] = music_of

        # --- IMAGE (4 output images) ----------------------------------------------
        image = self._upsert_request(
            user, provider, "design-image",
            inference_type="IMAGE",
            model_name=models["image"].name,
            payload={
                "model": models["image"].name,
                "prompt": "four color studies of a sunrise over a server rack, soft gradient light",
                "n": 4,
                "size": "512x512",
                "quality": None,
                "response_format": "url",
            },
            results={},
            latency_ms=8300,
            image_count=4,
        )
        image_assets = self._ensure_assets(
            image, MediaAsset.OUTPUT_IMAGE,
            [
                (f"image-{i}.png", make_png(hue), "image/png", None, None)
                for i, hue in enumerate((0.02, 0.32, 0.58, 0.78))
            ],
        )
        image.results = {
            "created": now_ts,
            "image_asset_ids": [a.id for a in image_assets],
            "count": len(image_assets),
        }
        image.save(update_fields=["results", "modified_on"])
        requests["image"] = image

        # --- MESH (input image + output GLB + trellis-style metadata) -------------
        mesh_meta = {
            "seed": 42,
            "resolution": "512",
            "vertices": 8,
            "faces": 12,
            "generation_time_s": 41.7,
        }
        mesh_options = {"resolution": "512", "seed": 42}
        mesh = self._upsert_request(
            user, provider, "design-mesh",
            inference_type="MESH",
            model_name=models["mesh"].name,
            payload={
                "model": models["mesh"].name,
                "options": mesh_options,
                "source_filename": "cube-source.png",
            },
            results={},
            latency_ms=41700,
        )
        self._ensure_assets(
            mesh, MediaAsset.INPUT_IMAGE,
            [("cube-source.png", make_png(0.12), "image/png", None, None)],
        )
        (mesh_asset,) = self._ensure_assets(
            mesh, MediaAsset.OUTPUT_MODEL,
            [("model.glb", make_glb(), "model/gltf-binary", None, mesh_meta)],
        )
        mesh.results = {
            "model_asset_id": mesh_asset.id,
            "content_type": "model/gltf-binary",
            "metadata": mesh_meta,
            "options": mesh_options,
        }
        mesh.save(update_fields=["results", "modified_on"])
        requests["mesh"] = mesh

        # --- VIDEO (output mp4 + resolved params) ----------------------------------
        mp4, real_mp4 = make_mp4()
        if not real_mp4:
            self.stdout.write(self.style.WARNING(
                "ffmpeg not available — OUTPUT_VIDEO is a 1-byte placeholder "
                "(video players will show an error state)."
            ))
        video_params = {"width": 640, "height": 360, "fps": 24, "num_frames": 48, "seed": 7}
        video_seconds = round(48 / 24, 3)
        video = self._upsert_request(
            user, provider, "design-video",
            inference_type="VIDEO",
            model_name=models["video"].name,
            payload={
                "model": models["video"].name,
                "prompt": "a slow dolly shot of test bars dissolving into a sunrise gradient",
                "negative_prompt": "",
                "has_image": False,
                "image_strength": None,
                "duration": 2.0,
                "num_frames": 48,
                "fps": 24,
                "width": 640,
                "height": 360,
                "num_inference_steps": 24,
                "guidance_scale": 4.0,
                "enhance_prompt": False,
                "seed": 7,
            },
            results={},
            latency_ms=58200,
            audio_seconds=video_seconds,  # reused as the duration meter for video
        )
        (video_asset,) = self._ensure_assets(
            video, MediaAsset.OUTPUT_VIDEO,
            [(
                "video.mp4", mp4, "video/mp4", video_seconds,
                {k: video_params[k] for k in ("width", "height", "fps", "num_frames")},
            )],
        )
        video.results = {
            "video_asset_id": video_asset.id,
            "content_type": "video/mp4",
            "duration": video_seconds,
            "params": video_params,
        }
        video.save(update_fields=["results", "modified_on"])
        requests["video"] = video

        # --- VIDEO #2 (second item for the video-playlist watch flow) -----------
        video2 = self._upsert_request(
            user, provider, "design-video-2",
            inference_type="VIDEO",
            model_name=models["video"].name,
            payload={
                "model": models["video"].name,
                "prompt": "macro shot of GPU fans spinning up, shallow depth of field, warm light",
                "negative_prompt": "",
                "has_image": False,
                "image_strength": None,
                "duration": 2.0,
                "num_frames": 48,
                "fps": 24,
                "width": 640,
                "height": 360,
                "num_inference_steps": 24,
                "guidance_scale": 4.0,
                "enhance_prompt": False,
                "seed": 11,
            },
            results={},
            latency_ms=61400,
            audio_seconds=video_seconds,
        )
        (video2_asset,) = self._ensure_assets(
            video2, MediaAsset.OUTPUT_VIDEO,
            [(
                "video.mp4", mp4, "video/mp4", video_seconds,
                {k: video_params[k] for k in ("width", "height", "fps", "num_frames")},
            )],
        )
        video2.results = {
            "video_asset_id": video2_asset.id,
            "content_type": "video/mp4",
            "duration": video_seconds,
            "params": {**video_params, "seed": 11},
        }
        video2.save(update_fields=["results", "modified_on"])
        requests["video_2"] = video2

        # Track cover art (PRD 06): the music track links the IMAGE request as
        # its square cover, exercising cover rendering in the player/playlists.
        if requests["music"].cover_request_id != requests["image"].id:
            requests["music"].cover_request = requests["image"]
            requests["music"].save(update_fields=["cover_request", "modified_on"])

        self.stdout.write(f"Seeded {len(requests)} inference requests")
        return requests

    # --- collection / stars / bookmarks -----------------------------------------

    def _seed_curation(self, user, requests):
        collection, _ = Collection.objects.update_or_create(
            user=user,
            slug="design-fixtures",
            defaults={
                "name": "Design fixtures",
                "description": "Deterministic examples of every modality, used by the design screenshot tests.",
                "visibility": "PUBLIC",
                "cover_request": requests["image"],
            },
        )
        for position, key in enumerate(("image", "video", "mesh", "music", "llm")):
            item, _ = CollectionItem.objects.get_or_create(
                collection=collection, request=requests[key],
                defaults={"position": position},
            )
            if item.position != position:
                item.position = position
                item.save(update_fields=["position", "modified_on"])

        # Ordered playlists (PRD 06): a music mixtape with cover art and a
        # video playlist, exercising the playlist view + watch up-next panel.
        mixtape, _ = Collection.objects.update_or_create(
            user=user,
            slug="design-mixtape",
            defaults={
                "name": "Design mixtape",
                "description": "Seeded music playlist for the player/playlist design tests.",
                "visibility": "PUBLIC",
                "cover_request": requests["image"],
            },
        )
        for position, key in enumerate(("music", "music_2", "music_overflow")):
            item, _ = CollectionItem.objects.get_or_create(
                collection=mixtape, request=requests[key],
                defaults={"position": position},
            )
            if item.position != position:
                item.position = position
                item.save(update_fields=["position", "modified_on"])

        video_list, _ = Collection.objects.update_or_create(
            user=user,
            slug="design-video-playlist",
            defaults={
                "name": "Design video playlist",
                "description": "Seeded video playlist for the watch-page design tests.",
                "visibility": "PUBLIC",
            },
        )
        for position, key in enumerate(("video", "video_2")):
            item, _ = CollectionItem.objects.get_or_create(
                collection=video_list, request=requests[key],
                defaults={"position": position},
            )
            if item.position != position:
                item.position = position
                item.save(update_fields=["position", "modified_on"])

        for key in ("llm", "image", "video"):
            Star.objects.get_or_create(user=user, request=requests[key])
            requests[key].recount_stars()
        for key in ("image", "mesh"):
            Bookmark.objects.get_or_create(user=user, request=requests[key])

        # Home-page featured showcase: one per modality, deterministic order
        # (newest featured first on the page).
        base_ts = timezone.now()
        for offset, key in enumerate(
            ("image", "video", "music", "mesh", "llm", "tts", "stt")
        ):
            ir = requests[key]
            ir.featured_at = base_ts - timezone.timedelta(minutes=offset)
            ir.save(update_fields=["featured_at", "modified_on"])

        self.stdout.write(
            "Collections 'design-fixtures' / 'design-mixtape' / "
            "'design-video-playlist' + stars/bookmarks ready"
        )

    # --- verification --------------------------------------------------------------

    def _print_verification(self, user):
        self.stdout.write(self.style.MIGRATE_HEADING("Verification"))
        by_type = (
            InferenceRequest.objects.filter(user=user)
            .values("inference_type")
            .annotate(n=Count("id"))
            .order_by("inference_type")
        )
        for row in by_type:
            self.stdout.write(f"  requests {row['inference_type']:<6} {row['n']}")
        by_kind = (
            MediaAsset.objects.filter(user=user)
            .values("kind")
            .annotate(n=Count("id"))
            .order_by("kind")
        )
        for row in by_kind:
            self.stdout.write(f"  assets   {row['kind']:<13} {row['n']}")
        storage = default_storage.__class__.__name__
        location = getattr(default_storage, "location", "") or getattr(
            settings, "MEDIA_ROOT", ""
        )
        self.stdout.write(f"  storage  {storage} ({location})")
        self.stdout.write(self.style.SUCCESS(
            f"Login: {DESIGNBOT_EMAIL} / {DESIGNBOT_PASSWORD} "
            f"(staff, public profile /{DESIGNBOT_LOGIN})"
        ))
