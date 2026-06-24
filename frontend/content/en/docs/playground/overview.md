---
title: The playground
description: A browser home for every modality — chat, agents, images, video, music, voice, and the tools to build pipelines.
category: Playground
order: 1
---

# The playground

The playground is the human side of inference.club: a set of dashboard tools that exercise every modality without writing a line of code. Everything here is the same API the rest of these docs describe — the playground just gives it a face. Sign in and find it under **Dashboard → Playground**.

## Language

::doc-cards
  :::doc-card{title="Chat" to="/dashboard/playground" icon="sparkles"}
  Streaming chat with a model picker, system prompt, sampling controls, a thinking toggle, image/audio/video attachments for multimodal models, and inline speech playback.
  :::

  :::doc-card{title="Per-token logprobs" to="/dashboard/playground" icon="gauge"}
  Turn on the logprobs viewer to see each token's probability — useful for debugging refusals, confidence, and sampling.
  :::

  :::doc-card{title="Chat threads" to="/dashboard/chats" icon="book"}
  Conversations persist with AI-generated titles, so you can pick up where you left off. Browse them under Dashboard → Chats.
  :::
::

## Agents

::doc-cards
  :::doc-card{title="Agent" to="/dashboard/playground/agent" icon="bot"}
  A server-side tool-calling chatbot. It can search the web, scrape pages, browse, and generate images, video, music, and voice — picking tools and skills on its own.
  :::

  :::doc-card{title="Voice agent" to="/dashboard/playground/voice" icon="mic"}
  Hands-free: your microphone streams to speech-to-text, into the streaming agent, and back out as speech — a spoken conversation with tools.
  :::
::

The agent can also use **your own** third-party keys (Brave, ElevenLabs, OpenAI…) when a tool needs one — managed under [Settings → API keys](/dashboard/settings/api-keys) and stored encrypted.

## Audio & voice

::doc-cards
  :::doc-card{title="Transcription" to="/dashboard/playground/transcribe" icon="waves"}
  Record or upload audio and get a transcript, with timestamps when the model supports them.
  :::

  :::doc-card{title="Text to speech" to="/dashboard/playground/speech" icon="mic"}
  Synthesize speech from text with a selectable voice.
  :::

  :::doc-card{title="Voice cloning" to="/dashboard/playground/voice-cloning" icon="mic"}
  Manage a private library of voice samples, then generate multi-speaker dialogue in those voices.
  :::

  :::doc-card{title="Music" to="/dashboard/playground/music" icon="music"}
  Turn a description and optional lyrics into a finished track — with cover art.
  :::

  :::doc-card{title="Audio enhance" to="/dashboard/playground/enhance" icon="waves"}
  Denoise and clean up a noisy recording.
  :::
::

## Vision & 3D

::doc-cards
  :::doc-card{title="Images" to="/dashboard/playground/images" icon="image"}
  Text-to-image and image editing.
  :::

  :::doc-card{title="Video" to="/dashboard/playground/videos" icon="video"}
  Generate clips from a prompt, or animate a still with image-to-video.
  :::

  :::doc-card{title="Image to 3D" to="/dashboard/playground/model3d" icon="boxes"}
  Turn a single image into a downloadable 3D mesh.
  :::

  :::doc-card{title="Scrape" to="/dashboard/playground/scrape" icon="code"}
  Fetch any URL as clean Markdown.
  :::
::

## Build: queue, workflows & studio

Beyond one-shot generation, the playground is where you compose and orchestrate.

::doc-cards
  :::doc-card{title="Queue" to="/dashboard/queue" icon="workflow"}
  Watch async jobs and workflow runs execute live, including an SVG-rendered DAG of each run.
  :::

  :::doc-card{title="Workflow Studio" to="/dashboard/workflows" icon="git"}
  A visual builder for multi-step pipelines — drag nodes, wire outputs to inputs, run, fork, and rerun a single step.
  :::

  :::doc-card{title="Narration Studio" to="/dashboard/studio" icon="layers"}
  Assemble multi-segment narrated episodes from text — generate, retrim, reorder, and regenerate each segment.
  :::
::

<h2 id="workflows">From playground to API</h2>

Nothing in the playground is a dead end. Every generation can be made [public, unlisted, or private](/docs/sharing) and dropped into a [collection](/docs/sharing#collections); workflows you build visually run through the same [workflows API](/docs/api/workflows) an automated caller would use; and every tool here maps to an [endpoint](/docs/api/overview) you can script. The playground is the fastest way to find the model and parameters you want — then you take them to the API.
