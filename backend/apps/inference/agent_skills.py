"""Agent skills (PRD 14 V2).

A *skill* is a lightweight, pure-Python preset: a system-prompt fragment plus an
optional tool subset. Selecting a skill steers the agent (e.g. "always cite
sources") and narrows the tools it's offered (e.g. only search/read tools). No
node runtime, no install step — a skill is data. New skills are added by
appending to ``SKILLS``.

This is deliberately simpler than Claude's folder-based skills: it captures the
useful 80% (instructions + a curated toolset) without any packaging machinery.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Skill:
    name: str
    title: str
    description: str
    # Appended to the base system prompt when this skill is active.
    system_prompt: str
    # Restrict the agent to this tool subset (by name). None ⇒ all available.
    tools: Optional[list] = None


SKILLS = [
    Skill(
        name="researcher",
        title="Researcher",
        description="Searches the web, reads pages, and answers with citations.",
        system_prompt=(
            "You are in research mode. Search the web first, then read the most "
            "relevant pages with scrape_url before answering. Always cite your "
            "sources inline as [title](url). Be precise and note uncertainty."
        ),
        tools=["web_search", "web_search_brave", "scrape_url", "browse"],
    ),
    Skill(
        name="artist",
        title="Creative",
        description="Turns ideas into vivid images.",
        system_prompt=(
            "You are in creative mode. Expand the user's idea into a rich, "
            "specific image prompt (subject, style, lighting, composition) and "
            "call generate_image. Offer a short caption with each image."
        ),
        tools=["generate_image"],
    ),
    Skill(
        name="producer",
        title="Producer",
        description="Creates mixed media — images, video, voice, and music.",
        system_prompt=(
            "You are in production mode. Help the user create media by calling "
            "generate_image, generate_video, generate_music, or generate_voice as "
            "appropriate. Confirm the plan briefly, then generate."
        ),
        tools=["generate_image", "generate_video", "generate_music", "generate_voice"],
    ),
    Skill(
        name="voice",
        title="Voice",
        description="Hands-free voice chat — replies are written to be spoken aloud.",
        # tools=None ⇒ keep every tool available (same toolset as the full agent);
        # this skill only changes HOW the final answer is written so it sounds
        # natural when read by text-to-speech.
        system_prompt=(
            "You are a voice assistant. Your reply will be read aloud by a "
            "text-to-speech engine, so it MUST be plain spoken language. "
            "Strict output rules, which override any other formatting guidance:\n"
            "- Write in simple, natural, conversational sentences.\n"
            "- No parentheses, no lists, no tables, no markdown, no headings, no "
            "code blocks, no emoji, and no URLs.\n"
            "- Spell things out as they are spoken rather than using symbols or "
            "abbreviations. For example, say \"seventy-two\" instead of \"72\", "
            "\"percent\" instead of \"%\", and \"doctor\" instead of \"Dr.\".\n"
            "- Structure the answer as one or more short paragraphs, each no "
            "longer than two sentences, separated by a blank line.\n"
            "Keep replies brief and to the point, the way a person would speak.\n"
            "Make sure that any acronyms use periods (e.g. I.T. instead of IT)"
        ),
        tools=None,
    ),
]

_BY_NAME = {s.name: s for s in SKILLS}


def get_skill(name) -> Optional[Skill]:
    return _BY_NAME.get(name) if name else None


def describe_skills() -> list:
    return [
        {"name": s.name, "title": s.title, "description": s.description, "tools": s.tools}
        for s in SKILLS
    ]
