---
name: inference-club
description: Operate an inference.club account by request — generate images, video, music, speech and text; make a song with matching pictures in one step; find, rename, share, hide, collect and delete things in the library; change account settings and who may use hosted services; play music; call any API endpoint. Use whenever the user says "inference club"/"inference.club" (or a self-hosted instance of it), asks to generate media with their own or community GPUs, or asks to change something in their inference.club account.
version: 2.0.0
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
  - name: INFERENCE_CLUB_INSTANCE
    prompt: "Saved inference.club instance name"
    help: "A name saved with `ic.py instance add` — picks that deployment's URL and key"
    required_for: "choosing between several deployments"
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

## Doing things to the account

Three ways, from least to most effort. All act as the key's owner, and every
result has a `summary` (or `did`) sentence — **tell the user that sentence**.

**1. Just say it.** Hand the request to the account's own assistant, which picks
the tools, acts, and reports. Best when the request is one sentence and you
don't need to control the details.

```bash
$IC do "make my newest song public and add it to the Favourites collection"
$IC do "make a 2 minute 30 second song about the ocean with 5 pictures"
$IC do "set my default visibility to private"
```

`did` lists what was actually done; `reply` is the assistant's wording;
`job_ids` are generations still running (`$IC job <id> --wait`).

**2. Call a tool yourself.** Same tools, you choose the arguments.
`$IC tools` lists them; `$IC tools NAME` shows one schema.

```bash
$IC tool search_library kind=song query=rain          # → items with ids
$IC tool update_item id=1115 title="Urban Rainfall" visibility=PUBLIC
$IC tool set_visibility_many visibility=PRIVATE kind=image query=portrait
$IC tool save_collection name="Road trip" visibility=UNLISTED
$IC tool collection_items collection="Road trip" item_ids='[1115,1105]'
$IC tool get_settings
$IC tool update_settings default_visibility=PRIVATE default_collection="Road trip"
$IC tool services                                      # hosted services + access
$IC tool make_song topic="first snow" duration_seconds=150 images=5
$IC tool play_music query=rain                         # returns audio URLs
```

| Tool | What it does |
| --- | --- |
| `search_library`, `get_item` | Find songs, images, videos, speech, chats; read one in full |
| `update_item` | Rename, set visibility, star, bookmark, set cover |
| `set_visibility_many` | One visibility for many items (ids or a search) |
| `delete_item`, `delete_collection` | Two calls: the first describes, the second (`confirm=true`) deletes. **Ask the user between them.** |
| `list_collections`, `get_collection`, `save_collection`, `collection_items` | Playlists and albums |
| `cover_art` | Count songs without covers; `generate=true` queues them |
| `get_settings`, `update_settings` | Default visibility and collection, fallback model, routing, public profile, alias |
| `services` | Hosted services and who may use them |
| `make_song` | Lyrics (written for you unless you pass `lyrics`), the song, and one image per `image_prompts` entry, all filed in one collection |
| `play_music`, `open_page` | Audio URLs / page URLs (the web app plays and navigates) |
| `find_api`, `api_request` | Look up and call anything else |

Visibility values: `PUBLIC` (listed), `UNLISTED` (anyone with the link),
`PRIVATE` (signed-in members), `SECRET` (owner only).

**3. The raw API.** `$IC api METHOD /path [--data JSON] [-q k=v]` reaches every
endpoint; `$IC tool find_api query="voice samples"` finds one.

### Which deployment

`$IC doctor` shows the instance in use. To keep several (hosted, home lab,
local dev) and pick by name:

```bash
INFERENCE_CLUB_API_KEY=… $IC instance add homelab --base-url https://club.example --default
$IC -I homelab do "what's in my queue?"
```

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

## MCP

The same tools are a remote MCP server at `$INFERENCE_CLUB_BASE_URL/mcp`
(Streamable HTTP, same Bearer key) for clients that prefer MCP over a shell:

```bash
claude mcp add --transport http inference-club "$INFERENCE_CLUB_BASE_URL/mcp" \
  --header "Authorization: Bearer $INFERENCE_CLUB_API_KEY"
```
