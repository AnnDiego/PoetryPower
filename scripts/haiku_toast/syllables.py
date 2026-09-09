"""
Cheap English syllable heuristic — optional report metadata only.

Independent of poem_analyzer. Does not gate, retry, or fail a run.
Not a scansion product.
"""

from __future__ import annotations

import re
from typing import List, Sequence, Tuple

TARGETS = (5, 7, 5)
# Off by more than this on any line (or not three lines) → "way off".
WAY_OFF_DELTA = 2


def count_syllables(word: str) -> int:
    """Vowel-group counter with a few silent-e / -le tweaks."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0

    # A few words the vowel-group rule consistently misses.
    exceptions = {
        "people": 2,
        "every": 2,
        "poem": 2,
        "poems": 2,
        "quiet": 2,
        "write": 1,
        "writes": 1,
        "seventeen": 3,
        "syllables": 3,
        "fire": 1,
        "hour": 1,
        "our": 1,
        "starship": 2,
        "ramen": 2,
        "padres": 2,
    }
    if w in exceptions:
        return exceptions[w]

    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for char in w:
        is_vowel = char in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel

    if w.endswith("e") and count > 1 and not w.endswith("le"):
        count -= 1
    if w.endswith("le") and len(w) > 2 and w[-3] not in vowels:
        count += 1

    return max(1, count)


def line_syllables(line: str) -> int:
    words = re.findall(r"[A-Za-z']+", line)
    return sum(count_syllables(w) for w in words)


def haiku_counts(lines: Sequence[str]) -> List[int]:
    return [line_syllables(line) for line in lines]


def counts_label(counts: Sequence[int]) -> str:
    return "-".join(str(c) for c in counts) if counts else "n/a"


def is_way_off(lines: Sequence[str]) -> bool:
    """True when the poem is not three lines or a line is far from 5-7-5."""
    if len(lines) != 3:
        return True
    counts = haiku_counts(lines)
    return any(abs(c - t) > WAY_OFF_DELTA for c, t in zip(counts, TARGETS))


def split_haiku_lines(text: str) -> List[str]:
    """
    Pull three poem lines out of a model reply.

    Strips common wrappers (quotes, markdown fences, leading bullets).
    """
    cleaned = text.replace("\r\n", "\n").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    lines: List[str] = []
    for raw in cleaned.splitlines():
        line = raw.strip().strip("\"'`")
        line = re.sub(r"^[-*]\s+", "", line)
        if not line:
            continue
        # Skip obvious chatter
        low = line.lower()
        if low.startswith(("here", "haiku:", "sure", "of course")):
            continue
        lines.append(line)
        if len(lines) == 3:
            break
    return lines


def format_haiku(lines: Sequence[str]) -> str:
    return "\n".join(line.strip() for line in lines if line.strip())


def parse_haiku(text: str) -> Tuple[List[str], str]:
    """Return (three-or-fewer lines, joined text)."""
    lines = split_haiku_lines(text)
    return lines, format_haiku(lines)
