---
name: inference-club
description: Generate images, video, music, speech, and text — or transcribe audio, scrape web pages, and run multi-step media workflows — with inference.club, a community network of self-hosted GPUs. Use whenever the user says "inference club"/"inference.club", or asks to generate/create/render media with their own or community GPUs.
version: 1.0.0
author: inference.club
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Images, Video, Music, TTS, LLM, Generation, Media]
    category: media
    prerequisites:
      commands: [python3]
required_environment_variables:
  - name: INFERENCE_CLUB_API_KEY
    prompt: "inference.club API key"
    help: "Dashboard → Settings → Token at https://inference.club/dashboard/settings/token"
    required_for: "every inference.club request"
  - name: INFERENCE_CLUB_BASE_URL
    prompt: "inference.club API base URL"
    help: "Default https://api.inference.club — only set for self-hosted / local dev (e.g. http://localhost:8101)"
    required_for: "non-default deployments"
    optional: true
---

# inference.club

inference.club serves open models (FLUX image, LTX video, ACE-Step music, Dia/Magpie
speech, Nemotron LLMs, ASR, 3D, web scrape) from **real home GPUs**. Each model usually
runs on ONE GPU that does one job at a time — be a polite client.

## The tool: `ic.py`

Everything goes through the bundled CLI. It lives next to this file at
`scripts/ic.py` (in Hermes: `${HERMES_SKILL_DIR}/scripts/ic.py`; in Claude Code: the
skill's base directory + `/scripts/ic.py`). If `inference-club` is on PATH (the
installer links it), use that instead. Python 3 stdlib only — nothing to install.

It needs `INFERENCE_CLUB_API_KEY` in the environment. Every command prints **one JSON
object** on stdout (`"ok": true|false`); progress lines go to stderr. You don't need to
read `ic.py` — the commands below are the whole interface.

**Never print the API key** (no `echo $INFERENCE_CLUB_API_KEY`). To check setup, run
`ic.py doctor` — it masks the key and reports whether auth works.

```bash
IC="python3 <skill-dir>/scripts/ic.py"          # or just: inference-club
$IC doctor                                       # setup check (key masked)
$IC models                                       # what's online (id + service_type)
$IC image "a watercolor fox in tall grass" -o fox.png
$IC image "neon city at dusk" --size 1344x768 --n 2 -o out/
$IC edit "make it night time" -i photo.png -o night.png
$IC video "slow dolly shot through a misty forest" -o forest.mp4      # slow: 1–5 min
$IC video "the fox turns its head" --image fox.png -o fox.mp4        # image-to-video
$IC music "lofi hip hop, mellow piano, vinyl crackle" --duration 60 -o song.mp3
$IC music "upbeat pop" --lyrics @lyrics.txt -o pop.mp3
$IC speech "Welcome to the show." -o hello.wav
$IC transcribe meeting.wav
$IC chat "Summarize this in 3 bullets: ..."      # LLM answer in "text"
$IC scrape https://example.com/article -o article.md
$IC capacity                                     # live GPU load per model
$IC job 123 --wait -o out/                       # resume waiting on a queued job
$IC jobs --active
$IC workflow templates
$IC workflow run illustrated-story --input topic="a robot learning to paint"
$IC workflow status 42
```

Common flags on generation commands: `-m/--model ID`, `-o/--output FILE|DIR` (downloads
the result), `--timeout SECONDS` (default 900), `--set key=value` (any extra
model-specific field, repeatable), `--visibility PUBLIC|UNLISTED|PRIVATE|SECRET`,
`--collection NAME`.

## How to work

1. **Pick the model by `service_type`** (`ic.py models --type image`). Omitting `-m`
   uses the first online model of that type — fine for most requests.
2. **Run one generation at a time per model.** For N images, prefer `--n` (max 4) or
   sequential calls. Never launch many video/music jobs in parallel: they queue
   behind each other on one GPU anyway, and you only make the queue longer.
3. **Queued is normal, not an error.** `ic.py` sends `async: "auto"`: if the GPU is
   busy (or its node is briefly offline) the request becomes a job and `ic.py` waits
   for it. If it times out you get `"status": "QUEUED"` + a `job_id` — later run
   `ic.py job <job_id> --wait`. **Do not resubmit** the same request.
4. **Results are URLs** in `media[].url` (plus `saved_to` when you passed `-o`). Give
   the user the URL or the saved path; don't paste file bytes or base64.
5. **Errors** come back as `{"ok": false, "error": "...", "type": "..."}`:
   - `no_provider` → that model isn't online; run `ic.py models` and pick another.
   - `at_capacity` → device busy; `ic.py` already waited and retried. Try later.
   - `missing_prompt`, `request_too_large`, … → fix the input.
   - 401 → the API key is missing/invalid.

## Model-specific tips

- **Images**: `--size WxH` (e.g. `1024x1024`, `1344x768`), `--seed` for
  reproducibility, `--background transparent` for cutouts (if the model lists the
  `transparent-background` feature). Edits accept up to ~8–10 `-i` reference images;
  refer to them as "image 1", "image 2" in the prompt.
- **Video**: write the prompt like a shot description (subject, motion, camera,
  lighting). Expect minutes. `--image` animates a first frame.
- **Music**: `prompt` = comma-separated style tags; lyrics use `[verse]`, `[chorus]`
  markers; default is instrumental. `--duration` in seconds.
- **Speech**: dialogue models (Dia) are driven automatically with `[S1]`/`[S2]`
  speaker tags — you can write `"[S1] Hi! [S2] Hello there."` for two voices.
- **Chat**: models may reason before answering; don't set a tiny `--max-tokens`
  (leave it unset or ≥ 1024).

## Raw HTTP (if you can't run Python)

OpenAI-compatible API at `$INFERENCE_CLUB_BASE_URL/v1` with
`Authorization: Bearer $INFERENCE_CLUB_API_KEY`. Add `"async": "auto"` to generation
bodies and `"delivery": "url"` to audio/video bodies to get JSON with URLs; a `202`
means poll `GET /v1/jobs/<id>` until `status` is `PROCESSED` and read `media[].url` /
`output_text`. Full spec: `$INFERENCE_CLUB_BASE_URL/openapi.json`. See
`references/api.md` for the cheat sheet.

There is also a remote MCP server at `$INFERENCE_CLUB_BASE_URL/mcp` (same Bearer key)
for clients that prefer MCP tools over a shell.
