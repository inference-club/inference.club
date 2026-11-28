---
title: "Say it, and it happens: one set of tools for the web app, MCP clients and a CLI"
description: "inference.club now has a single layer of 33 account tools — generate, search, rename, share, collect, change settings, play — reachable three ways: an Assistant panel in the web app, an MCP server at /mcp, and a skill with a small CLI. This is how it is built, how it was tested with five different models driving it, and what is not done yet."
publishedAt: "2026-11-28"
author: briancaffey
tags: [agents, mcp, architecture, engineering]
image: /showcase/night-market.webp
image_prompt: "Cinematic photograph of a rainy night market alley, paper lanterns reflected in puddles, a food stall with rising steam, one person under a transparent umbrella seen from behind, 35mm film, shallow depth of field, teal and amber"
---

After a year of shipping modalities, inference.club had a lot of pages. A playground per modality, a library, collections, a queue, settings, a music player. Each one works. The problem is what happens when you want something that crosses three of them.

"Make my newest song public and put it in the Favourites collection" is one sentence. In the web app it was: open the library, find the song, open its page, change the visibility, open the collection picker, pick the collection. Six clicks for a thought that took two seconds to have. And an agent that wanted to do the same thing had it worse, because the only way in was the raw HTTP API and a lot of reading.

The naive fix is the one most projects reach for first: put a chatbot in the corner and give it a handful of functions written specially for it. That gets you a second implementation of every rule the app already has. Who may change visibility, what a collection name must look like, what happens when a GPU is busy: all of it written once in the views the UI calls, and then again, slightly differently, in the chatbot's functions. The two drift. Then you add an MCP server for outside agents and write the rules a third time.

This post is about doing it once. The code is in the open-source [`inference.club`](https://github.com/inference-club/inference.club) repo, mostly in `backend/apps/inference/control_tools.py` and `mcp_server.py`, with a how-to in `docs/assistant.md`.

## The five-second version

```
 Assistant panel (web app, typed or spoken) ─┐
 ic.py do "…"  (skill for shell agents) ─────┼─▶ POST /v1/agent  skill: "assistant" ─┐
                                             │      (an LLM picks the tools)         │
 Claude, Cursor, Hermes … over MCP ──────────┴─▶ POST /mcp  tools/call ──────────────┼─▶ 33 tools ─▶ the app's own HTTP views
 ic.py tool NAME …                                                                   │               (same permissions as the UI)
```

One list of 33 tools. Three ways to reach it. Every tool calls the same view the web app calls, as the person who asked, so there is no second copy of any rule.

## What a tool is

A tool is a JSON schema plus a handler with the signature `(request, args) -> dict`. The handler does not touch the database. It builds an internal request to the view the UI would have called, in-process, carrying the caller's own credentials, and returns what came back. If you cannot do something by clicking, the tool cannot do it for you either.

The returned dict has a small fixed shape:

- `summary`: one past-tense sentence saying what happened. "Renamed 'untitled' to 'Urban Rainfall' and made it public." The assistant repeats it, the web panel prints it on the step's card, and the CLI returns it in a `did` list.
- `media`, `job_id` or `jobs`: results, or work that is still running on somebody's GPU.
- `client_action`: optionally `{type: "navigate", path}` or `{type: "play", tracks}`. The web app carries these out. Other clients get URLs and do what they like with them.

That `summary` field turned out to matter more than I expected. Small models are not good at reading a 40-line JSON response and reporting accurately on it. They are fine at repeating a sentence. Putting the sentence in the tool result means the report is written by code that knows what happened, not inferred by a model that is guessing.

The 33 tools fall into rough groups:

| Group | Tools |
| --- | --- |
| Generate | `generate_image`, `generate_video`, `generate_music`, `generate_speech`, `chat`, `scrape_url` |
| Jobs and capacity | `list_models`, `get_capacity`, `get_job`, `list_jobs`, `cancel_job` |
| Workflows | `list_workflow_templates`, `run_workflow`, `get_workflow_run` |
| Library | `search_library`, `get_item`, `update_item`, `set_visibility_many`, `delete_item`, `cover_art` |
| Collections | `list_collections`, `get_collection`, `save_collection`, `collection_items`, `delete_collection` |
| Account | `get_settings`, `update_settings`, `services` |
| Playback and navigation | `play_music`, `open_page` |
| Composite | `make_song` |
| Escape hatch | `find_api`, `api_request` |

Adding a 34th is four steps: write the handler, add an entry to `CONTROL_TOOLS`, add a label in each locale file, add a test. It then exists over MCP, in the panel and in the CLI with no other change. That was the point of the exercise.

## Three ways in

### The Assistant panel

Press Cmd+J (Ctrl+J elsewhere) anywhere in the web app and a panel opens. Type or speak. The request goes to `/v1/agent` with the `assistant` skill, a model picks tools, and each step shows up as a card with its summary sentence. Generations that are still running show as jobs, and the panel follows them until the picture or the song lands in the card. Replies can be read aloud.

Which model drives it is a setting. More on that in the testing section, because it is the interesting part.

### The MCP server

`/mcp` on the API host speaks Model Context Protocol over Streamable HTTP. It is stateless: every JSON-RPC request is answered in the POST response, no session, no event stream. It authenticates with the same bearer token as the rest of the API, so adding it to an MCP client is one line:

```bash
claude mcp add --transport http inference-club https://api.inference.club/mcp \
    --header "Authorization: Bearer $INFERENCE_CLUB_API_KEY"
```

Cursor, Hermes and other MCP clients take the same URL and header. Here the outside agent's own model picks the tools. inference.club is only the hands.

One design decision worth naming: generation tools never return inline base64. They return URLs. A 1024×1024 PNG as base64 is over a megabyte of text, and an agent that receives it has just spent its context window on noise. A generation tool also waits a bounded time for the GPU (45 seconds for MCP clients by default, 20 inside the assistant) and then hands back a job id rather than holding the connection. A single home GPU does one job at a time, so "queued" is a normal answer, not an error.

### The skill and `ic.py`

For agents that live in a shell, there is a skill: a `SKILL.md` and one Python file, `ic.py`, standard library only. It has three levels, from least effort to most control:

```bash
# 1. Say it. The account's own assistant picks the tools.
ic.py do "make my newest song public and add it to the Favourites collection"

# 2. Call one tool yourself.
ic.py tool update_item id=1115 title="Urban Rainfall" visibility=PUBLIC

# 3. The raw API.
ic.py api GET /v1/capacity
```

Every command prints one JSON object. `do` returns `did` (what was actually done, from the tools' summary sentences), `reply` (the assistant's wording) and `job_ids` for anything still running.

inference.club can be self-hosted, and I run more than one copy: the hosted one, one in the home cluster, one on a laptop for development. So the CLI keeps named instances:

```bash
ic.py instance add homelab --base-url https://club.example --default
ic.py -I homelab do "what's in my queue?"
```

An agent can be pointed at a specific deployment by name, which is what makes the next post's "generate the same thing on a different deployment" a one-flag change.

## One sentence, several GPUs

The tool I use most is `make_song`. "Make a 2 minute 30 second song about the ocean with pictures" is one action:

1. An LLM writes lyrics for the topic (unless you pass your own).
2. The song is started on the music model.
3. One image is started per picture prompt.
4. Everything is filed in one collection.

It returns the job ids straight away and the panel fills in as each GPU finishes. In the home cluster those three kinds of work land on different machines: the lyrics on whatever is serving the LLM, the song on a DGX Spark running ACE-Step, the pictures on an RTX 4090 running FLUX.

![A print of a desk by a window at night: a computer tower glowing beside a sleeping cat, the town's lit windows outside](/showcase/desk-by-the-window.webp)

*"The machine by the window". FLUX 3 Image Klein on an RTX 4090 in the home cluster, seed 77310, 8.4 seconds. One of the pieces in the homepage showcase.*

I could have left this to the model: it has `chat`, `generate_music`, `generate_image` and `save_collection`, and a capable model can chain them. But that is five or six tool calls with ids carried between them, and each extra step is another chance for a small model to drop one. A composite tool for the thing people actually ask for is cheaper than hoping.

## Deleting takes two turns

Three safety rules are built into the tool layer rather than left to the prompt.

**Tools act as the caller.** They go through the app's views, so they can do nothing the person could not do in the UI.

**Deleting is two calls.** `delete_item` and `delete_collection` called without `confirm` only describe what would be deleted. The second call, with `confirm: true`, deletes. Inside the assistant, that second call must come in a *later turn*, after the person has answered. A model cannot ask "shall I delete it?" and answer its own question in the same breath.

**The escape hatch has walls.** `api_request` can call any `/v1/*` or `/api/*` endpoint as the user, which is how the list stays at 33 instead of 200. But it cannot reach sign-in, token, registration, admin or node-agent endpoints, it cannot write external API keys, and token fields are hidden in what it returns.

::blog-note{type="note"}
The two-turn rule is enforced for the built-in assistant. An outside MCP client is running its own loop with its own model, so there the rule is a strong instruction in the tool description plus the two-call shape. If you connect an agent with your API key, it has your permissions. Treat the key accordingly.
::

## Does it work with a small model?

The whole thing is only useful if a model that fits on a home GPU can drive it. So the test was the same eight account requests (find something, rename it, change who can see it, file it in a collection, change a setting, and so on) given to several different models.

| Model driving the assistant | Where it ran | Result |
| --- | --- | --- |
| Nemotron 3.5 Lightning | The home cluster | 8 of 8, about 6 seconds each |
| Nemotron 3 Ultra | NVIDIA's hosted API | 8 of 8 |
| Nemotron Nano Omni | NVIDIA's hosted API | 8 of 8 |
| Nemotron Nano Omni (free) | OpenRouter | 8 of 8 |
| GPT-OSS 120B | Groq's free tier | 3 of 4 run |

The Groq row needs explaining, because the failure was not the model's. The tool list costs about 3.6k tokens per turn. A three-step request sends it three times, plus the growing conversation, and that went over the free tier's tokens-per-minute limit. The three requests that fit within the limit passed.

That number is the real constraint on this design. 3.6k tokens per turn is nothing to a large hosted model and a meaningful slice of a small model's context. It is why `api_request` and `find_api` exist instead of a tool per endpoint, and why I am now suspicious of every new tool: each one is paid for on every turn, by every model, forever.

From the other direction, Claude Code connected as an MCP client was asked to rename a song, change its sharing and file it in a collection. It did all three in 14 seconds.

::blog-note{type="disclaimer"}
Eight requests is a smoke test, not a benchmark. It tells me the tool descriptions are clear enough for these models to pick the right one on straightforward account tasks. It says nothing about long, ambiguous or adversarial requests, and I have not measured those.
::

## What is not done

- **Voice on a real phone.** The spoken path was tested with a synthesized microphone feed. It has not been tested with a person talking to an actual phone in an actual room, which is where voice interfaces usually fall over.
- **Hermes, end to end.** The skill installs in the Hermes agent, but a full run from Hermes through to a finished result has not completed yet.
- **The panel is a modal sheet.** It covers the page while it is open. What I want is a docked side panel that sits beside whatever you were looking at, so you can watch the library change as you ask.

## What is next

Two things, both about making this easy to pick up.

**Agent setup in one command.** Today, pointing an agent at inference.club means getting an API key, then either adding the MCP server or installing the skill and saving an instance. Each step is small. Together they are enough friction that someone will not bother. It should be one command.

**Keeping the tool list small.** The Groq result was a useful warning. The target is for the tool list to stay comfortable for small-context models, the kind people in this community actually run at home, rather than quietly becoming something only a large hosted model can afford to read.

The next post covers the other half of this week's work: [a homepage showcase generated by the club itself, and seeds that make every piece reproducible](/blog/made-here-and-makeable-again).
