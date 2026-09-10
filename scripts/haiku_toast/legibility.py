"""
Burn-in legibility check for Daily Haiku Toast stills.

Imagine often emits a rare garbled still (wrong words / gibberish) next
to a correct-ish Maillard burn-in. This module scores extracted text
against the intended three-line haiku and picks a passer.

Text extraction (in this environment, no tesseract / no new deps):
  1. xAI vision via the same chat/completions stack as the writer
     (XAI_API_KEY already required for Imagine). Maillard letters are
     low-contrast; a vision read is more reliable than classic OCR.
  2. Optional local ``tesseract`` on PATH if vision is unavailable.

The scorer itself is stdlib-only (difflib + regex) so tests do not need
a key, an image library, or an OCR package.
"""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, List, Optional, Sequence

# Tuned against keeper-style misspellings (pass) vs 2026-09-10 garbled
# API draws (fail). See tests.test_haiku_toast.LegibilityTests.
MIN_COMPACT_RATIO = 0.58
MIN_WORD_RECALL = 0.50
STRONG_COMPACT_RATIO = 0.72
FUZZY_WORD_RATIO = 0.78

READ_BURN_IN_PROMPT = (
    "Read the English letters burned into the toast crumb "
    "(the browned Maillard text on the slice, not butter or background). "
    "Transcribe exactly what you see, three lines if they appear as three "
    "lines. If letters are misspelled or gibberish, copy them as they appear. "
    "Output ONLY the transcription, no commentary."
)


@dataclass
class BurnInScore:
    extracted: str
    compact_ratio: float
    word_recall: float
    passed: bool

    def summary(self) -> str:
        flag = "pass" if self.passed else "fail"
        return (
            f"{flag} (compact {self.compact_ratio:.2f} / "
            f"word recall {self.word_recall:.2f})"
        )


@dataclass
class ExtractResult:
    text: str
    method: str  # vision | tesseract | none | injected
    error: Optional[str] = None


@dataclass
class StillCandidate:
    index: int  # 1-based for reports
    url: str
    path: Optional[Path] = None


@dataclass
class ScoredStill:
    candidate: StillCandidate
    score: BurnInScore
    method: str
    error: Optional[str] = None


@dataclass
class PickResult:
    ok: bool
    tried: int
    kept: Optional[ScoredStill] = None
    scores: List[ScoredStill] = field(default_factory=list)
    note: str = ""

    @property
    def kept_index(self) -> Optional[int]:
        return self.kept.candidate.index if self.kept else None


def letters_only(text: str) -> str:
    return re.sub(r"[^a-z]", "", (text or "").lower())


def content_words(text: str) -> List[str]:
    """Alphabetic tokens of length >= 3 (drops 'of' / 'a')."""
    return re.findall(r"[a-z]{3,}", (text or "").lower())


def score_burn_in(extracted: str, intended: str) -> BurnInScore:
    """
    Compare OCR/vision text to the intended haiku.

    Compact ratio is SequenceMatcher on letters-only strings so mashed
    words (Crispslice, writeseventeen) still match. Word recall asks
    that most content words appear as a substring or a close fuzzy token.
    """
    intended = (intended or "").strip()
    extracted = (extracted or "").strip()
    a = letters_only(intended)
    b = letters_only(extracted)
    compact = SequenceMatcher(None, a, b).ratio() if a and b else 0.0

    wanted = content_words(intended)
    blob = b
    tokens = content_words(extracted)
    hits = 0
    for word in wanted:
        if word in blob or any(
            SequenceMatcher(None, word, token).ratio() >= FUZZY_WORD_RATIO
            for token in tokens
        ):
            hits += 1
    recall = hits / len(wanted) if wanted else 0.0
    passed = (compact >= MIN_COMPACT_RATIO and recall >= MIN_WORD_RECALL) or (
        compact >= STRONG_COMPACT_RATIO
    )
    return BurnInScore(
        extracted=extracted,
        compact_ratio=compact,
        word_recall=recall,
        passed=passed,
    )


ExtractFn = Callable[[StillCandidate], ExtractResult]


def pick_legible_still(
    intended_haiku: str,
    candidates: Sequence[StillCandidate],
    *,
    extract_fn: ExtractFn,
) -> PickResult:
    """
    Score every candidate and keep the passer with the best compact
    ratio (word recall as tie-break). If none pass, ok=False — callers
    must not ship a still.
    """
    scored: List[ScoredStill] = []
    for cand in candidates:
        extracted = extract_fn(cand)
        score = score_burn_in(extracted.text, intended_haiku)
        scored.append(
            ScoredStill(
                candidate=cand,
                score=score,
                method=extracted.method,
                error=extracted.error,
            )
        )

    tried = len(scored)
    if not scored:
        return PickResult(
            ok=False,
            tried=0,
            note="Imagine: no candidates to score — not shipping a still.",
        )

    passers = [row for row in scored if row.score.passed]
    unread = all((not row.score.extracted) for row in scored)
    if not passers:
        if unread:
            reasons = [row.error for row in scored if row.error]
            extra = f" ({reasons[0]})" if reasons else ""
            note = (
                f"Imagine: generated {tried} candidate(s) but the burn-in "
                f"check could not read any of them{extra} — not shipping."
            )
        else:
            note = (
                f"Imagine: all {tried} candidate(s) failed the burn-in check "
                f"(garbled / wrong words) — not shipping a still."
            )
        return PickResult(ok=False, tried=tried, scores=scored, note=note)

    kept = max(passers, key=lambda row: (row.score.compact_ratio, row.score.word_recall))
    note = (
        f"Imagine: ok — kept candidate #{kept.candidate.index} of {tried} "
        f"({kept.score.summary()}, {kept.method})."
    )
    return PickResult(ok=True, tried=tried, kept=kept, scores=scored, note=note)


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def extract_via_tesseract(path: Path) -> Optional[str]:
    if not tesseract_available():
        return None
    try:
        proc = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", "eng", "--psm", "6"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception:  # noqa: BLE001 — optional path
        return None
    text = (proc.stdout or "").strip()
    return text or None


def extract_via_vision(path: Path, *, api_key: str) -> str:
    """
    Transcribe burned letters with the same xAI chat model as the writer.

    Official image-understanding docs accept grok-4.6 with an image URL
    (public HTTPS or a data: URI). We send a data URI so temporary
    Imagine links do not have to stay fetchable.
    """
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "The 'requests' package is required for the burn-in check."
        ) from exc

    from .writer import DEFAULT_CHAT_URL, chat_model

    payload = {
        "model": chat_model(),
        "temperature": 0.0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": _file_data_uri(path),
                            "detail": "high",
                        },
                    },
                    {"type": "text", "text": READ_BURN_IN_PROMPT},
                ],
            }
        ],
    }
    resp = requests.post(
        DEFAULT_CHAT_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=90.0,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Vision API HTTP {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Vision API returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Vision API returned an empty transcription.")
    return content.strip()


def extract_burned_text(
    path: Path,
    *,
    api_key: Optional[str] = None,
) -> ExtractResult:
    """
    Prefer xAI vision (key already required for Imagine). Fall back to
    tesseract only when vision cannot run. Do not treat a tesseract
    gibberish read as final when a key is present — Maillard burn-in
    fools classic OCR.
    """
    key = (api_key or "").strip()
    if key:
        try:
            text = extract_via_vision(path, api_key=key)
            return ExtractResult(text=text, method="vision")
        except Exception as exc:  # noqa: BLE001
            tess = extract_via_tesseract(path)
            if tess:
                return ExtractResult(text=tess, method="tesseract")
            return ExtractResult(text="", method="vision", error=str(exc))

    tess = extract_via_tesseract(path)
    if tess:
        return ExtractResult(text=tess, method="tesseract")
    if tesseract_available():
        return ExtractResult(
            text="",
            method="tesseract",
            error="tesseract returned no text",
        )
    return ExtractResult(
        text="",
        method="none",
        error="no XAI_API_KEY and no tesseract on PATH — cannot read burn-in",
    )


def make_extract_fn(*, api_key: str) -> ExtractFn:
    def _extract(candidate: StillCandidate) -> ExtractResult:
        if candidate.path is None or not candidate.path.is_file():
            return ExtractResult(
                text="",
                method="none",
                error="candidate image was not downloaded",
            )
        return extract_burned_text(candidate.path, api_key=api_key)

    return _extract


def _file_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    mime = "image/png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"
