# Narrate

Paste a link or some text; get it read aloud in your cloned voice as one
recording. The page is `/dashboard/narrate`, the API is `POST /v1/narrations`,
and over MCP the tool is `narrate`.

```
link or text
   │  read      article.py     the article behind the link: title, author, date, main text
   │                           (the club's scrape service first, a direct fetch as fallback;
   │                            a Hacker News discussion link is followed to the story)
   │  plan      narrate.py     an opening line, then the text in pieces of whole sentences;
   │                           a pronunciation list for acronyms and odd terms
   │  voice     narration.py   per piece: take (Dia, cloned voice) → clean-up (Studio Voice)
   │                           → trim silence → word check (ASR + judge) → retake if poor
   │  mix       narrate.py     chosen takes joined into one MP3, with where each piece starts
   ▼  cover     narrate.py     a title image, queued alongside
Episode  (audio, cover_request, source, production)
```

A narration is an ordinary Studio `Episode`, so everything the Studio can do
(waveform editing, auditions, saving a voice) works on it. The narrate page is
the short path: progress, a player, and per-piece fixes.

## Following a run

Read `GET /v1/episodes/{id}`. The `narration` object has:

| Field | Meaning |
| --- | --- |
| `stage` | `reading`, `planning`, `voicing`, `mixing`, `done`, `error`, `stopped` |
| `fraction` | 0 to 1 across the whole run |
| `counts` | pieces `total`, `ready`, `flagged`, `error`, `working`, `waiting` |
| `models` | which model does each job: `voice`, `clean`, `check`, `judge`, `cover`, `read` |
| `events` | the last few log lines, timestamped |
| `mix.offsets` | start and end of each piece in the joined file |
| `mix_current` | false when takes changed since the file was built |

`audio_url` is the joined recording, `cover_image_url` the title image and
`source` what was found about the article. The page polls every two seconds
while anything is running.

## Fixing a piece

- `POST /v1/segments/{id}/produce` voices it again.
- `PATCH /v1/segments/{id}` with `text`, then produce, rewords it.
- `POST /v1/segments/{id}/feedback` with a `note` ("say SQL as sequel") has a
  model turn the note into new wording or a pronunciation entry, then
  re-voices. On the page a note can be spoken: it is transcribed first.
- `POST /v1/segments/{id}/variants/{vid}/select` switches to another take.
- `POST /v1/episodes/{id}/mix` rebuilds the joined file (the page does this by
  itself when the pieces settle).

## Notes for whoever works on this next

- Pieces are voiced one after another. The voice model sits behind a
  per-device lock, so several narrations share it fairly but do not run in
  parallel; a second voice instance is not used yet.
- The word check compares what was meant with what speech recognition heard.
  `_normalize_for_similarity` makes digits and words, spaced and unspaced
  acronyms, and ordinals compare equal, and the judge is told the same.
  Proper names still score a little low.
- Narrations accept a take at 8 of 10; the Studio default is 8.5.
- With no voice sample, the first accepted take is saved as the voice and
  cloned for the rest, so the narrator does not change mid-piece.
- Direct fetches refuse private addresses (`article._check_public`).
- Playback speed (0.5× to 3×, pitch kept) is one shared setting,
  `usePlaybackRate`, used by the narration player, `AudioClip` and the global
  player.
