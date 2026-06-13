# PRD 09 — Voice cloning (Dia): voice samples, dialogue & `/v1/voice/generations`

> **Status:** Draft / in progress (2026-06-13). First implementation in
> flight across four repos: the **dia** service (new standalone repo +
> GHCR image), **inference-club-agent** (new `serveVoice` route),
> **inference.club** backend (`VoiceSample` model + `/v1/voice/generations`)
> and frontend (voice-cloning playground + sample library), and
> **home-cluster** (k8s manifest, GPU node a1/a2/a3).
>
> **Author:** Brian (spec) · drafted with Claude Code.
>
> **Decisions taken at spec time:**
> voice samples are **private-only** for now (no public/shared visibility —
> avoids voice-likeness/consent questions; can revisit later); the API is a
> **dedicated `/v1/voice/generations`** endpoint (the OpenAI `/audio/speech`
> shape stays clean for Riva TTS); Dia runs on **one of a1/a2/a3** (whichever
> has ≥10 GB free VRAM — we may stop another service to make room); the dia
> service gets its **own GitHub repo** under the `inference-club` org.
>
> **Scope:** Make inference.club do great **voice cloning** with
> [nari-labs/Dia](https://github.com/nari-labs/dia). Users build a private
> **library of voice samples** (one default sample per speaker + optional
> variations), each with a transcript (auto-filled via our own STT), and
> generate speech in those voices from the playground or the API. Single-
> and multi-speaker dialogue via `[S1]`/`[S2]` tags, with a one-line prompt
> defaulting to `[S1]`.
> **Explicitly out of scope (V1):** sharing/publishing voice samples,
> voice-likeness consent flows, real-time/streaming synthesis, more than two
> speakers (`[S3]`+), and payments/quotas beyond existing rate limits.

---

## 1. Summary

Dia is an open-weights 1.6B text-to-**dialogue** model. Unlike our current
Riva-backed TTS (pick a named voice, get audio), Dia clones a voice from an
**audio prompt + its transcript**, and renders multi-speaker scripts with
`[S1]`/`[S2]` tags. That's a different enough shape that it gets its own
surface rather than being bolted onto `/v1/audio/speech`.

Three things ship together:

1. **A voice-sample library.** A private, per-user collection of speakers.
   Each speaker has exactly one **default** sample and zero or more
   **variation** samples. A sample is an audio clip + its transcript (Dia
   needs both to clone). Uploaded or mic-recorded; the transcript is
   auto-filled by our own STT service (`/v1/audio/transcriptions`) and is
   editable. Reviewing, renaming, re-transcribing, setting the default, and
   deleting all happen in the playground.

2. **`POST /v1/voice/generations`.** A dedicated endpoint (modeled on
   `MusicGenerationsView`) that takes a script, a speaker→sample mapping,
   and Dia's sampling controls, resolves the referenced samples to
   `(audio, transcript)` pairs, forwards a multipart request through the
   agent to Dia's `POST /generate`, stores the result as a public
   `OUTPUT_AUDIO`, and returns the bytes.

3. **The Dia service in the cluster.** The `dia` FastAPI server, now
   containerized (GPU image, configurable `HF_HOME`/model/port), pushed to
   `ghcr.io/inference-club/dia`, and deployed as a k8s service labeled
   `inference-club.com/type=tts`, `engine=other`,
   `features=voice-cloning,dialogue`. The agent discovers it and routes
   `/v1/voice/generations` to it.

The unifying primitive is the **`VoiceSample`** row: a user-owned audio
asset + transcript + speaker grouping. Everything else (visibility, stars,
collections, metering, the playground) reuses machinery that already exists.

---

## 2. Why a new endpoint, not `/v1/audio/speech`

`/v1/audio/speech` adapts the OpenAI shape (`model`, `input`, `voice`) to
Riva's `/audio/synthesize` (`text`, `voice`, `language`, `encoding`). Dia
shares none of that:

| | Riva TTS (`/audio/speech`) | Dia (`/voice/generations`) |
|---|---|---|
| voice selection | named `voice` string | reference **audio + transcript** |
| input | plain text | `[S1]`/`[S2]` script |
| request to engine | form fields | **multipart** (text + file) |
| controls | `response_format`, `sample_rate` | `cfg_scale`, `temperature`, `top_p`, `cfg_filter_top_k`, `speed_factor`, `seed`, `max_new_tokens` |
| speakers | one | one or two |

Overloading `/audio/speech` would force a `voice` string to sometimes mean
"a Riva voice name" and sometimes "a VoiceSample id," and would smuggle a
file upload into a JSON endpoint. A dedicated endpoint keeps both clean.
Precedent: `/v1/music/generations`, `/v1/videos/generations`, and
`/v1/3d/generations` are all non-OpenAI endpoints routed by `service_type`.

Dia is still a `tts` **service type** (text in, audio out). We distinguish
its capability with service **features**: `voice-cloning` and `dialogue`.
The catalog/model `supported_features` surfaces these so the frontend shows
the right playground.

---

## 3. Data model

### 3.1 `VoiceSample` (new)

```
VoiceSample(BaseModel)
  user            FK CustomUser                      # owner
  speaker_name    CharField(120)                     # "Brian", "Narrator"
  label           CharField(120, blank)              # variation label, "" for default
  is_default      BooleanField(default=False)        # one default per (user, speaker_name)
  audio           FK MediaAsset (INPUT_AUDIO, private)
  transcript      TextField                          # required for cloning
  transcript_source CharField(stt|manual|edited)     # provenance of the text
  language        CharField(16, blank)
  duration_seconds FloatField(null)                  # denormalized from asset
  metadata        JSONField(default=dict)

  Meta:
    constraints:
      UniqueConstraint(user, speaker_name, is_default, condition=is_default,
                       name="one_default_sample_per_speaker")
    indexes: [(user, speaker_name, created_on)]
```

Notes:
- A "speaker" is not its own table — it's the set of `VoiceSample` rows
  sharing `(user, speaker_name)`. The library groups by `speaker_name`.
- The audio reuses **`MediaAsset` with `kind=INPUT_AUDIO`** (already private
  by default — not in `PUBLIC_KINDS`). No new storage path.
- `is_default` is enforced one-per-speaker by a partial unique constraint;
  setting a new default clears the old one in the same transaction.
- Samples are **private**. No `visibility` field in V1 (decision above).

### 3.2 Generated output

A voice generation is a normal `InferenceRequest` with a new
`inference_type="VOICE"` and a public `OUTPUT_AUDIO` `MediaAsset`, exactly
like TTS/music. The `payload` records the script, the resolved speaker map
(sample ids, not bytes), and the sampling controls so a run is replayable.

---

## 4. API

### 4.1 Voice-sample library — `apps/inference` REST

DRF viewset under the existing dashboard API (session-auth, owner-scoped):

| Method & path | Purpose |
|---|---|
| `GET /api/inference/voice-samples/` | list mine, grouped client-side by `speaker_name` |
| `POST /api/inference/voice-samples/` | multipart: `audio` file, `speaker_name`, optional `label`, `transcript`, `is_default`, `language`. If `transcript` omitted, kick off STT. |
| `GET /api/inference/voice-samples/{id}/` | detail |
| `PATCH /api/inference/voice-samples/{id}/` | edit transcript/label/speaker_name; `is_default=true` promotes (clears sibling) |
| `DELETE /api/inference/voice-samples/{id}/` | delete (and its MediaAsset) |
| `POST /api/inference/voice-samples/{id}/transcribe/` | (re)run STT, fill `transcript` |

**Auto-transcription.** On create-without-transcript (and on the
`transcribe` action), the server calls the **existing** STT path with the
uploaded audio, against the user's available `stt` provider. Synchronous and
best-effort: if no STT provider is online, the sample is saved with an empty
transcript and the UI nudges the user to type one (Dia can't clone without
it). `transcript_source` records `stt` vs `manual` vs `edited`.

### 4.2 `POST /v1/voice/generations`

Request (JSON; `application/json`):

```jsonc
{
  "model": "dia-1.6b",                 // optional; first online voice model otherwise
  "input": "Hey, welcome to the show.",// raw script; may contain [S1]/[S2]
  "speakers": {                        // optional speaker -> voice-sample id
    "S1": "<voice_sample_id>",
    "S2": "<voice_sample_id>"
  },
  // sampling controls (all optional, clamped server-side)
  "cfg_scale": 3.0, "temperature": 1.8, "top_p": 0.95,
  "cfg_filter_top_k": 45, "speed_factor": 1.0,
  "max_new_tokens": 3072, "seed": -1,
  // sharing (existing params)
  "visibility": "public", "collection": "My voices"
}
```

**Script normalization (`[S1]`/`[S2]`).** Server-side, before forwarding:
- If `input` contains no `[S` tag at all → treat the whole thing as one
  line and prefix `[S1] ` (the single-speaker default the user asked for).
- If it already has tags → pass through, but validate it starts with `[S1]`
  and only uses `[S1]`/`[S2]` (reject `[S3]+` in V1 with a clear 400).
- A `speakers` map may reference `S1` and/or `S2`. Only speakers that appear
  in the (normalized) script need a sample; extras are ignored.

**Voice cloning assembly.** Dia clones from **one** concatenated audio
prompt + its transcript, prepended to the script (per the dia server's
contract: `audio_prompt_text + "\n" + text`). With one speaker that's just
the chosen sample. With two speakers we build a two-line prompt transcript
(`[S1] <s1 transcript>\n[S2] <s2 transcript>`) and concatenate the two audio
clips into a single WAV, in S1→S2 order, so the prompt audio and prompt
transcript line up. (Concatenation happens server-side with `soundfile`/
`wave`; clips are resampled to a common rate.) If no `speakers` are given,
Dia generates in its own default voice (no audio prompt) — still useful.

**Forwarding.** The view resolves samples → `(audio_bytes, transcript)`,
assembles the prompt, then POSTs **multipart** to the agent at
`{provider.tailnet_base_url}/voice/generations`:

```
text                = "[S1] ...\n[S2] ..."         # script (normalized)
audio_prompt_text   = "[S1] ...\n[S2] ..."         # prompt transcript (omitted if no samples)
audio_prompt        = <concatenated wav>           # file (omitted if no samples)
max_new_tokens, cfg_scale, temperature, top_p, cfg_filter_top_k, speed_factor, seed
```

The agent rewrites this to Dia's `POST /generate` (§6). Response is
`audio/wav` with `x-seed` / `x-sample-rate` / `x-duration-seconds` headers;
the view stores it as `OUTPUT_AUDIO`, meters `audio_seconds`, records the
real `seed` returned, and streams the bytes back (like TTS/music).

`GET /v1/audio/voices` is **not** used for Dia (voices are user samples, not
a server enum). `/v1/models` exposes the Dia model with
`supported_features: ["voice-cloning","dialogue"]` so the frontend routes to
the voice-cloning playground instead of the TTS one.

---

## 5. The Dia service (containerization + new repo)

The current `~/git/hn.fm/services/dia` is a single `server.py` FastAPI app
with no Dockerfile and two hardcodes that block cluster use:

- `HF_HOME` is pinned to `/mnt/e/a3data/huggingface` (a WSL path).
- the model id `nari-labs/Dia-1.6B-0626` and the bind port are literals.

**Changes (kept minimal, no behavior change to `/generate`):**
- `HF_HOME` only forced if unset (respect the env when the pod sets it).
- Model id from `DIA_MODEL` (default `nari-labs/Dia-1.6B-0626`).
- Port already from `PORT` (default 8491) — keep.
- New **`Dockerfile`** on a CUDA base (`nvidia/cuda:12.6.x-runtime` +
  Python, or `pytorch/pytorch:2.6.0-cuda12.6` ) installing the pinned
  `torch==2.6.0`/`torchaudio==2.6.0` cu126 wheels and `nari-tts` from git.
  `HEALTHCHECK` on `/health`. Exposes `PORT`.
- `.dockerignore`, a short `README` deploy section, and a GitHub Actions
  **build-and-push** workflow → `ghcr.io/inference-club/dia:{latest,sha-…}`
  (mirrors inference.club's existing workflow).

**New repo.** The service moves to its own repo under `inference-club`
(working name `inference-club/dia`). We keep the source under
`~/git/hn.fm/services/dia` for now and push a copy to the new repo, or
relocate it — TBD at push time (outward-facing; confirm before creating the
remote).

**Hardware.** 1.6B params, fp16 on CUDA ≈ ~3 GB weights + headroom; budget
~10 GB VRAM. Needs an NVIDIA node (a1/a2/a3). HF cache on a host path so the
model isn't re-downloaded across restarts.

---

## 6. Agent routing (`inference-club-agent`)

Today the router maps `/v1/audio/synthesize` → first `tts` backend
verbatim. Dia's surface (`POST /generate`, multipart) differs, so it gets a
dedicated handler like the mesh/music/video ones:

- Add a case in `router.ServeHTTP` for `POST /v1/voice/generations`.
- `serveVoice` selects the backend that is `type=tts` **and** advertises the
  `voice-cloning` feature (so a plain Riva `tts` service isn't picked), then
  forwards the inbound multipart body to `{backend}/generate`, streaming the
  `audio/wav` response and passing through `x-seed`/`x-sample-rate`/
  `x-duration-seconds`. A generous timeout (Dia generation is seconds-to-a-
  minute, like video/music).
- `serviceURL` for Dia has **no `/v1` base-path** (its endpoint is
  `/generate` at the root), matching how TRELLIS is wired.

This keeps the existing `tts` route (Riva) untouched.

---

## 7. Frontend — voice-cloning playground + sample library

New page `pages/dashboard/playground/voice-cloning.vue`, nav entry
`dashboard.items.voiceCloning`, composable `useVoiceCloning.ts`.

**Layout (two columns, matching the other playgrounds):**
- **Left — script + run.** A textarea for the script. A speaker toggle:
  *Single speaker* (default; we send one line, server prefixes `[S1]`) or
  *Two speakers* (reveals an `[S1]`/`[S2]` helper that inserts tags and a
  second speaker picker). Sharing picker + Run/Stop + elapsed timer.
- **Right — voices + controls.** A **speaker picker** per active speaker:
  choose a speaker from the library, then (optionally) which sample/variation
  (default selected). "No voice (Dia default)" is allowed. Below, an
  **Advanced** disclosure with the Dia sliders (`cfg_scale`, `temperature`,
  `top_p`, `cfg_filter_top_k`, `speed_factor`, `seed`, `max_new_tokens`) at
  Dia's defaults.
- **Below — `RecentGenerations` (type `VOICE`)**, reusing the existing card.

**Voice sample library.** A dedicated panel/route
(`/dashboard/playground/voice-cloning` has a "Manage voices" dialog, or a
sibling `/dashboard/voices` page):
- Grouped by speaker. Each speaker shows its **default** sample (inline
  `<audio controls>`, transcript snippet) and a count of variations.
- Add a sample: drag-drop / browse / **record** (reuse `useAudioRecorder`
  and the transcribe.vue dropzone), enter speaker name + optional label,
  transcript auto-fills via STT and is editable. Pick from existing audio
  via the existing `AudioSourcePicker`.
- Per sample: play, edit transcript, set as default, re-transcribe, delete.

**i18n.** Add `dashboard.items.voiceCloning` and a `voiceCloning.*` block to
`en.json` (and the other six locales, English-fallback as elsewhere).

---

## 8. Metering, visibility, moderation

- Metered like TTS: `inference_type="VOICE"`, `audio_seconds` on the
  request, output counted toward the user's usage.
- Generated audio is `OUTPUT_AUDIO` (public-by-URL, same as TTS) and gets
  the normal visibility/stars/collections treatment.
- **Voice samples themselves are private** and never served publicly; their
  `MediaAsset` is `INPUT_AUDIO` (owner-gated). This is the consent-safety
  posture for V1 — you can clone voices you've recorded/own, but you can't
  publish someone's voice print.

---

## 9. Milestones

- **A — Dia service ships.** Dockerfile + config-ize + GHCR image + new
  repo. Verified: image runs, `/health` ok on a GPU node, `/generate`
  returns audio for a text-only and a cloned request.
- **B — Cluster + agent.** `home-cluster/services/dia/dia.yaml` applied to
  a1/a2/a3; `serveVoice` in the agent; `/v1/models` shows the Dia model with
  `voice-cloning`.
- **C — Backend.** `VoiceSample` model + migration + library API + STT
  auto-transcription; `/v1/voice/generations` view + URL + manifest features.
  Tests: script normalization (`[S1]` default, two-speaker assembly,
  `[S3]` reject), sample default-uniqueness, end-to-end forward (mocked
  upstream).
- **D — Frontend.** `useVoiceCloning`, the playground page, the sample
  library UI, nav + i18n.

## 10. Open questions / risks

- **Two-speaker audio concatenation** quality: Dia clones best from a single
  coherent prompt. Concatenating two clips is a pragmatic first cut; we may
  later switch to Dia's per-speaker prompting if the model/API exposes it.
- **STT availability** gates auto-transcription; the manual-transcript
  fallback keeps the feature usable when STT is offline.
- **Latency**: cold model load (5–15 s) on first request after a pod
  restart; the dia server loads on startup, so the readiness probe should
  gate traffic until the model is in.
- **Node placement / VRAM**: which of a1/a2/a3 has room may require stopping
  another GPU service; decided at deploy.
