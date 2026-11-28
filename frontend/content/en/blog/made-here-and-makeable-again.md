---
title: "Made here, and makeable again: a self-generated showcase and seeds you can replay"
description: "The inference.club homepage now shows work the club generated on its own GPUs: twelve pictures, three songs with covers, a spoken welcome and a four-line poem. Every piece comes from a manifest of model, prompt and seed, because every generation now gets a concrete seed that is stored with the request. What has been verified about reproducibility, what has not, the redesigned request and share pages, and what is next."
publishedAt: "2026-11-28T12:00:00Z"
author: briancaffey
tags: [reproducibility, image-generation, music, engineering]
image: /showcase/couriers.webp
image_prompt: "Stop-motion claymation still, three small round clay robots carrying glowing parcels along a miniature street between cardboard houses, visible fingerprints in the clay, soft studio lighting, shallow depth of field, cheerful"
---

For most of its life the inference.club homepage described what the network does and showed none of it. That is a strange way to introduce a place whose whole purpose is making pictures, songs and speech on GPUs in people's houses. The obvious fix was a gallery. The obvious way to build a gallery is to scroll through the library, pick the ten best-looking results anyone ever made, and paste them in.

I did not want to do that, for a reason that took me a while to put into words: a hand-picked gallery is a claim nobody can check. You see a nice picture and a caption that says a home GPU made it in eight seconds. Maybe. Which model? What prompt? Was it the first try or the fortieth? Could you get the same picture if you asked?

When I went to answer that last question for my own library, the answer was no, and the reason was a bug-shaped design decision that had been sitting in the code since the first modality shipped. This post is about the showcase, and about the seed problem that building it honestly forced me to fix. The code is in the open-source [`inference.club`](https://github.com/inference-club/inference.club) repo.

## The five-second version

```
scripts/showcase/showcase.json          the manifest: model + prompt + seed per piece
          │
          ▼
scripts/showcase/generate.py  ──  --instance <name>  ──▶  any inference.club deployment
          │                                                   │
          │                                    each request stores its concrete seed
          ▼                                                   │
frontend/public/showcase/               ◀── outputs + index.json (model, prompt, seed,
  (what the homepage shows)                 GPU, seconds, SHA-256 of the raw output)
```

The homepage shows what the manifest made. The manifest can be run again, here or on another deployment, and the recorded hashes say whether the result is the same bytes.

## What is on the homepage

Twenty pieces, all generated through the club's own API on home hardware. The index file records the model, prompt, seed, GPU and wall-clock seconds for each.

**Twelve pictures**, FLUX 3 Image Klein (`flux-3-image-klein-fp8`) on an RTX 4090 in the home cluster:

| Title | Seed | Seconds |
| --- | --- | --- |
| Cathedral of compute | 27015 | 6.2 |
| Couriers | 8842 | 8.5 |
| Rush hour on the motherboard | 41201 | 8.4 |
| Koi crossing | 61078 | 8.1 |
| The rig in the garage | 18310 | 8.1 |
| Still life with graphics card | 77310 | 8.3 |
| Rooftop, 16 bits | 5512 | 7.8 |
| Stitched fox | 90417 | 8.2 |
| Plans for a teapot automaton | 3344 | 5.4 |
| Neon jellyfish | 20261 | 5.7 |
| Paper forest | 12031 | 8.5 |
| Infrared orchard | 64007 | 7.9 |

This is the third set. The first was a mixed bag. The second, made later the same day, put every picture in one print style so the gallery would match the animated scenes on the homepage, and I changed my mind about that: a gallery is a better place to show range than restraint. So the set above goes the other way: twelve pictures in twelve different media, from stained glass and claymation to pixel art, embroidery and infrared film, with nothing shared between the prompts. The table is the current set, and the manifest no longer appends a style to anything.

The picture at the top of this post is the second row. Here is the first, with its whole recipe:

![A tall gothic stained glass window in a dim chapel, showing a haloed figure standing on a server rack, with coloured light on the stone floor](/showcase/cathedral-of-compute.webp)

*"Cathedral of compute". Prompt: "A tall gothic stained glass window depicting a server rack as a saintly figure, rays of coloured light falling across a stone floor, deep cobalt, ruby and amber glass with thick lead lines, photographed from inside a dim chapel". 768×1024, seed 27015, 6.2 seconds.*

**Three songs with covers**, ACE-Step 1.5 Turbo (`acestep-v15-turbo`) on a DGX Spark. The covers are three more FLUX images (seeds 12021, 12022 and 12023, between 7.9 and 8.6 seconds each), each in its own medium: marbled paper, a low-poly render and a linocut.

| Title | Style prompt | Seed | Length | Seconds to make |
| --- | --- | --- | --- | --- |
| First Light | ambient neoclassical, felt piano, slow warm strings, soft tape hiss, hopeful, 70 bpm, instrumental | 31001 | 60 s | 14.8 |
| Tailnet Drive | synthwave, driving analog bass, gated drums, bright arpeggiated synth lead, night drive, 110 bpm, instrumental | 31002 | 60 s | 15.1 |
| Porch Light | indie folk, fingerpicked acoustic guitar, soft brushed drums, warm female vocal, close harmonies, intimate, 92 bpm | 31003 | 75 s | 17.3 |

"Porch Light" is the one with a vocal. Seventy-five seconds of music in 17.3 seconds, about four times faster than it plays:

![Album cover: a two-colour linocut in mustard and green of a hanging porch lamp with moths around it and a guitar leaning on a chair](/showcase/cover-porch-sm.webp)

<audio controls preload="none" src="/showcase/song-porch.mp3"></audio>

And "Tailnet Drive", for anyone who read [the Tailscale post](/blog/tailscale-and-tsnet) and wondered what the tailnet sounds like:

<audio controls preload="none" src="/showcase/song-tailnet.mp3"></audio>

**A spoken welcome**, Magpie TTS (`magpie-tts-multilingual`) on an RTX 5090 laptop GPU. 7.7 seconds of speech in 1.8 seconds:

<audio controls preload="none" src="/showcase/speech-welcome.mp3"></audio>

**A four-line poem** from Nemotron 3.5 Lightning on the DGX Spark, 0.6 seconds, seed 7. The prompt was "Write a four-line poem about a porch light left on for a neighbour. No title." It wrote:

> A steady glow against the night,<br>
> A quiet watch from wood and paint.<br>
> It signals safety, soft and bright,<br>
> For neighbours walking home late.

The last line does not scan. I left it in. A showcase that only keeps the takes that flatter the model is the hand-picked gallery again.

::blog-note{type="disclaimer"}
There is no video in the showcase yet, and no 3D piece in the manifest. The manifest has two five-second LTX 2.5 clips written and seeded, but the video and 3D services were offline on the home cluster when the set was made. They will be added when those services are back, not faked in the meantime. The two 3D models that turn on the homepage are real, but older: TRELLIS.2 results from the library, made on a DGX Spark in June, each about half a million triangles, drawn on the page as 16,000 sampled points.
::

## The seed problem

Here is what used to happen when you asked for a song and did not pick a seed. The backend sent the model server `seed: -1` and `use_random_seed: true`. The model server drew a random number, used it, and made your song. The request row in the database recorded what the backend had sent: `-1`.

So the one number that determined the result was known for a few seconds by a Python process on somebody's GPU and then lost. Open the request page a week later and the settings say seed −1, which is a polite way of saying "we don't know". Voice cloning did the same with `-1`. Video stored `None`. 3D passed along a `randomize_seed` flag. Images forwarded whatever the caller sent, which was usually nothing.

A sentinel like −1 is a reasonable API for a model server. It is the wrong thing to *store*, because it records the question and not the answer.

The fix is small enough to quote in full. `backend/apps/inference/seeds.py`:

```python
SEED_MAX = 2**31 - 1


def pick_seed(value=None) -> int:
    """``value`` when it is a usable seed (an integer >= 0), else a fresh
    random one in [1, 2^31 - 1]."""
    if isinstance(value, bool):
        value = None
    try:
        seed = int(value)
    except (TypeError, ValueError):
        seed = -1
    return seed if seed >= 0 else random.randint(1, SEED_MAX)
```

The club draws the seed, not the model server. If you send a real seed, it is used. If you leave it out, send −1, or tick "randomize", a concrete number is chosen in the backend, sent upstream as an explicit seed with randomization turned off, and stored with the request. "Reproduce" then means the same call with the same number.

Where it applies:

- **Images**, for models whose deployment declares the `seed` feature in its manifest. The seed is drawn once per request and the same value goes into both the stored payload and the forwarded body, so a live call and a later replay send the same thing.
- **Music.** "Randomize" now means the backend picks. Songs queued before this change still carry −1 in their row; when one of those is run, a seed is settled at that point and written back, so the finished song records the number that made it.
- **Video and 3D.** Same treatment: always a concrete seed in the stored options.
- **Voice cloning.** Dia takes a seed, and a fixed one keeps a voice consistent across sections of a long narration.

Where it does not:

- **Chat** seeds stay opt-in. Sending a seed to an LLM server changes sampling behaviour that callers may not expect, and most chat use does not want replay. The showcase poem passes `seed: 7` explicitly.
- **Magpie speech** has no seed control, so the welcome clip's seed is recorded as `null`. That is the honest value.

## What "reproducible" has and has not been shown to mean

This is the part to read carefully, because it is easy to overclaim.

**Verified:** the same image request with the same seed, sent twice to the same deployment, produced a byte-identical file both times. Same model, same GPU, same driver, same container.

**Not yet verified:** reproducing the set on the production deployment. That is the next step. The generator takes an instance name, so it is one flag:

```bash
scripts/showcase/generate.py --instance local --static
scripts/showcase/generate.py --instance production          # same seeds
```

The generator records a SHA-256 of each raw output in the index, and a later run reports whether its output matches the recorded hash. So the comparison will be exact: the same bytes or not, per piece, with no squinting at two pictures side by side.

**Not guaranteed, and I do not expect it everywhere:** identical output across different GPUs or driver versions. A seed fixes the starting noise. It does not fix the order of floating-point operations, and different GPU architectures, CUDA and cuDNN versions, and kernel-selection heuristics can all produce results that differ in the low bits and then diverge over a diffusion run. An RTX 4090 and a DGX Spark are not obliged to agree with each other. Whether two deployments of the same model on similar cards produce the same bytes, a visually identical picture with a different hash, or a visibly different one is exactly what the production run is going to tell me, and I will write up whichever it is.

**Update, the same day.** The manifest has now been run against the production deployment. All thirteen images of the first set (ten pictures and three covers) came back byte-identical to the local run: same SHA-256, piece for piece. Both deployments route to the same RTX 4090s, so this confirms the seed travels intact through a second control plane; it does not yet say anything about different hardware. The current set of twelve pictures has since had the same check: made again on production and on the home-lab deployment, all twelve came back byte-identical to the local files.

The songs did not match, and a follow-up test showed why that is not a deployment difference: two songs made on the *same* deployment with the same seed are different songs. The seed is stored and sent, but the music model has a second source of randomness that it does not cover. Until that is fixed, a song's seed is a record, not a replay button. The spoken clip has no seed to set, and the poem differed too, which is expected for chat without stricter sampling settings.

What the seed work guarantees today is narrower and still worth having: no generation's seed is ever unknown again. Whatever the cross-hardware answer turns out to be, the experiment can now be run.

::blog-note{type="note"}
The showcase and the seed change are landing together with this post. If you self-host and are on an older build, requests made before you update keep whatever seed value they stored at the time, including −1.
::

## Request pages and share pages

The other change this week is to the page you land on when someone sends you a link.

The old request page led with metadata: ids, status, timestamps, a parameters table, and eventually the picture. That is the right order for debugging and the wrong order for everyone else. The redesigned page is:

1. **The result first.** The image, the player, the video, the text.
2. **A compact strip**: which machine, which GPU, which model, how long it took.
3. **The prompt and the settings**, including the seed, which is now always a real number.

That strip is the club's whole argument in one line. A named GPU in somebody's house made this, in this many seconds.

**Collections can now be shared by link.** A collection has an unguessable link you can hand to someone without making the collection public. The rule for what they see is deliberately strict: a shared collection only shows items that are themselves public or shared by link. Putting a private picture into a shared collection does not leak it. The collection link is a way to group things you have already decided to share, not a way to widen who can see them.

## What is next

**New open models, as they come out.** The network is only as interesting as what it serves. The plan is to keep adding the latest open models as they are released and make them available over the network, and to grow the showcase manifest alongside, so each new model arrives with pieces anyone can regenerate.

**Easy for agents to adopt.** [The previous post](/blog/say-it-and-it-happens) covers the API, the MCP server and the CLI. The aim is that an agent can go from nothing to generating on the club quickly, by whichever of the three fits it.

**A proper home for albums.** Three songs with covers are currently a collection with a naming convention. Albums deserve their own page.

**A lightbox and one player everywhere.** Click a picture, see it large with its recipe. Start a song on the homepage and have it keep playing as you move through the app, in the same player the music pages use.

And, before any of that: making songs replay from their seed the way pictures already do.
