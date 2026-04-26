---
title: Hello, inference.club
description: Why we're building a community-run inference network.
publishedAt: 2026-04-26
author: Brian Caffey
tags: [announcements]
---

The premise is simple: a lot of us have GPUs sitting idle, and a lot of us want to run inference on models we trust without sending traffic to a hyperscaler. inference.club is a community-run network that lets you do both in one move.

You sign up, generate an API key, and you immediately have an OpenAI-compatible endpoint at `api.inference.club/v1`. Anything that speaks the OpenAI API — Open WebUI, the Python SDK, Cursor, your own agent harness — works without modification.

If you also have hardware to share with your own clients, you run the [`inference-club-agent`](/docs/providers/run-an-agent) on the same network as your LLM server. The agent heartbeats into inference.club every 30 seconds with the model list it's serving, and your inference requests get routed back to your own machine.

The MVP is intentionally small: one user, one key, one provider per request. No billing, no rate limits, no complicated routing. Read the [docs](/docs) to dig in, or skip straight to the [quickstart](/docs/quickstart) and try it.
