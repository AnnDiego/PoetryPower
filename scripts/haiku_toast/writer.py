"""
xAI chat/completions writer for one short three-line haiku.

Reuses the visualizer's .env / XAI_API_KEY loading. Does not call
poem_analyzer or poem_fortune. One chat call; no syllable retry.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from .prompts import VOICE_BRIEF, writer_user_prompt
from .syllables import haiku_counts, parse_haiku

# Same host family as Imagine. Chat model is overridable.
DEFAULT_CHAT_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_CHAT_MODEL = "grok-4.6"


@dataclass
class WriteResult:
    haiku: str
    lines: List[str]
    counts: List[int]
    model: str = ""
    error: Optional[str] = None
    raw_replies: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.haiku) and self.error is None


def resolve_api_key() -> str:
    """
    Same key as Imagine: process env wins, then the visualizer .env search.

    Importing _load_dotenv_if_present keeps one resolution story.
    """
    from scripts.poem_visualizer.imagine_client import _load_dotenv_if_present

    _load_dotenv_if_present()
    return os.environ.get("XAI_API_KEY", "").strip()


def chat_model() -> str:
    return os.environ.get("XAI_CHAT_MODEL", DEFAULT_CHAT_MODEL).strip() or (
        DEFAULT_CHAT_MODEL
    )


def _chat_complete(
    *,
    api_key: str,
    user_text: str,
    timeout: float = 90.0,
) -> str:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "The 'requests' package is required for the writer. "
            "Install with: pip install requests"
        ) from exc

    payload = {
        "model": chat_model(),
        "messages": [
            {"role": "system", "content": VOICE_BRIEF.strip()},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.8,
    }
    resp = requests.post(
        DEFAULT_CHAT_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Chat API HTTP {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Chat API returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Chat API returned an empty message.")
    return content


def write_haiku(
    *,
    date_line: str,
    weekday_vibe: str,
    weather_seed: str,
    api_key: Optional[str] = None,
) -> WriteResult:
    """One chat/completions call. Keep the first parsed three lines."""
    key = (api_key if api_key is not None else resolve_api_key()).strip()
    if not key:
        return WriteResult(
            haiku="",
            lines=[],
            counts=[],
            error="no XAI_API_KEY",
        )

    user_text = writer_user_prompt(
        date_line=date_line,
        weekday_vibe=weekday_vibe,
        weather_seed=weather_seed,
    )
    model = chat_model()

    try:
        first = _chat_complete(api_key=key, user_text=user_text)
    except Exception as exc:  # noqa: BLE001 — CLI should keep going
        return WriteResult(
            haiku="",
            lines=[],
            counts=[],
            model=model,
            error=str(exc),
        )

    lines, haiku = parse_haiku(first)
    return WriteResult(
        haiku=haiku,
        lines=lines,
        counts=haiku_counts(lines),
        model=model,
        raw_replies=[first],
    )
