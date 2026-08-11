"""
Suggest the best-fit style for a poem via keyword + vibe matching.

Phase 1: deliberately simple, transparent scoring — no LLM required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .style_loader import Style
from .utils import collapse_whitespace


# ---------------------------------------------------------------------------
# Keyword bags per style (lowercased; multi-word phrases allowed)
# ---------------------------------------------------------------------------
#
# Philosophy — tuned to this repo's poetic voice (tech-poetess / Chief Poet):
#   Intimate human moments braided with rockets, desert nights, star charts,
#   truck-bed picnics, Cybertruck gleam, cockpits, hobby flares, and the soft
#   physics of shared sweatshirts. Matching should reward *cosmic + closeness*
#   together, not only bare "star" or bare "love".
#
#   Multi-word phrases (score +2 in _count_keyword_hits) capture signature
#   scenes: "truck bed", "star chart", "hobby flare", "stainless steel", etc.
#
#   romantic_anime + charcoal_sketch are weighted for quiet desert/night
#   intimacy. anime_cyberpunk picks up modern tech + romance (touchscreen,
#   Cybertruck, neon, stainless). moody_comic keeps bittersweet noir. collage
#   stays transformation / verse-as-material.
# ---------------------------------------------------------------------------

STYLE_KEYWORDS: Dict[str, set] = {
    "charcoal_sketch": {
        # Medium / hand-drawn quality
        "charcoal", "sketch", "pencil", "paper", "smudge", "smudged",
        "hand-drawn", "hand drawn", "drawing", "grayscale", "gray", "grey",
        # Quiet, delicate atmosphere
        "soft", "delicate", "gentle", "quiet", "hush", "hushed",
        "whisper", "whispered", "whispers", "silence", "silent", "stillness",
        "faint", "fragile", "tender", "reflective", "intimate",
        "memory", "memories", "remember", "alone", "solitude",
        "shadow", "shadows", "light", "dim", "faint glow",
        # Nature / weather (soft outdoor scenes)
        "nature", "tree", "trees", "leaf", "leaves", "branch", "branches",
        "puddle", "rain", "mist", "fog", "dawn", "dusk", "morning", "twilight",
        # Desert night / stargazing — quiet charcoal-friendly cosmos
        "desert", "deserts", "dune", "dunes", "sand", "earth", "rim",
        "wide and bare", "rugged earth", "star", "stars", "starry", "starlit",
        "night sky", "night", "sky", "moon", "moonlight", "constellation",
        "constellations", "stargazing", "stargaze", "gems across the sky",
        # Soft intimacy without loud romance machinery
        "arms", "hand", "hands", "eyes", "gaze", "breath", "cheek",
        "blanket", "blankets", "shared", "close", "warmth", "chill",
        "picnic", "truck bed", "truck's bed", "truck’s bed",
        # Gentle human-scale rocket moments (sketch, not neon launch hype)
        "flare", "smoke", "arc", "arcs", "trail", "plume",
        "hobby flare", "hobby rocket", "private launch",
    },
    "artistic_collage": {
        "collage", "paper", "pages", "words", "word", "verse", "verses",
        "poem", "poetry", "handwritten", "letters", "thread", "threads",
        "string", "strings", "fabric", "layer", "layers", "layered",
        "become", "becoming", "transform", "transformation", "reinvent",
        "reinvention", "identity", "piece", "pieces", "fragment",
        "fragments", "patchwork", "woven", "weave", "bind", "bound",
        "hope", "hopeful", "rise", "rising", "phoenix", "rebuild",
        "rebuilds", "scrap", "scraps", "cut", "paste",
        # Verse-as-body / becoming (this voice's reinvention poems)
        "silhouette", "corporate", "poet", "poetess", "full-time",
        "words and verses", "handwritten poetry", "flowing",
    },
    "moody_comic": {
        "moody", "mood", "dark", "darkness", "noir", "night", "midnight",
        "bittersweet", "bitter", "comic", "panel", "dramatic", "tension",
        "shadow", "shadows", "lonely", "loneliness", "phone", "screen",
        "alone", "empty", "void", "ache", "aching", "regret", "silence",
        "silent", "cold", "stark", "harsh", "contrast", "spotlight",
        "cinematic", "frame", "framed", "black", "ink", "heavy",
        "storm", "thunder", "rain", "grief", "loss", "gone",
        # Bittersweet night / distance / charged quiet
        "distance", "miss", "missing", "almost", "almost touch",
        "starry background", "starry", "noir-inspired", "emotional tension",
        "looking at a phone", "in the dark", "bed in the dark",
    },
    "romantic_anime": {
        # Core romance / tenderness
        "love", "lover", "lovers", "romance", "romantic", "kiss", "kisses",
        "heart", "hearts", "heart ignites", "my heart", "blush",
        "soft", "tender", "tenderness", "warm", "warmth", "heat",
        "intimate", "intimacy", "embrace", "hold", "held", "wrap", "wraps",
        "wrapped", "hand", "hands", "palm", "arms", "your arms",
        "eyes", "gaze", "in our eyes", "breath", "lips", "cheek",
        "giggle", "whisper", "whispers", "whispered", "low whisper",
        "longing", "yearn", "yearning", "gentle", "sweet", "darling",
        "beloved", "together", "us", "you and i", "you & i", "shared",
        "close", "close and warm", "cozy", "seeking heat",
        # Classic anime-soft palette
        "sakura", "cherry blossom", "cherry blossoms", "petal", "petals",
        "anime", "moonlight", "garden", "bloom", "blooming", "spring",
        "ramen", "tea",
        # Desert night + stargazing intimacy (signature voice)
        "desert", "deserts", "dune", "dunes", "sand", "earth", "rim",
        "star", "stars", "starry", "starlit", "starlit cockpit",
        "night sky", "night", "sky", "moon", "constellation", "constellations",
        "stargazing", "stargaze", "gems", "gems across the sky",
        "star chart", "star chart's map", "star chart’s map",
        # Truck bed picnic / cabin warmth
        "picnic", "truck", "truck bed", "truck's bed", "truck’s bed",
        "truck's wide bed", "truck’s wide bed", "wide bed",
        "blanket", "blankets", "sweatshirt", "loose sweatshirt",
        "shared sweatshirt", "cab", "cockpit", "our world",
        "cheese", "feast", "crumbs", "crumbles",
        # Soft rocket romance (not cyber neon — human-scale wonder)
        "rocket", "flare", "hobby flare", "hobby rocket", "private launch",
        "launch", "launches", "leap", "arcs high", "smoke glows",
        "starry light", "ignite", "ignites", "my heart ignites",
        # Warmth vs chill (body-close contrast)
        "chill", "chill bites", "cold", "too thin to warm", "seeking heat",
        "touchscreen", "soft touchscreen", "dim", "light dim",
        "clumsy rhyme", "recite", "pursed lips",
    },
    "anime_cyberpunk": {
        # Classic cyber / neon night
        "neon", "cyberpunk", "cyber", "city", "cities", "urban", "street",
        "streets", "alley", "market", "night", "nightlife", "rain",
        "rainy", "haze", "glow", "glowing", "electric", "voltage",
        "tokyo", "skyline", "skyscraper", "skyscrapers",
        "pixel", "digital", "wire", "wires", "circuit", "chrome",
        "metal", "steel", "stainless", "stainless steel", "stainless silver",
        "pulse", "pulsing", "beat", "bass", "club",
        "whisky", "whiskey", "sake", "bar", "passionate", "edge",
        "edgy", "modern", "future", "futuristic", "hologram", "led",
        # Modern tech + romance (this voice's Cybertruck / cockpit / UI glow)
        "cybertruck", "cyber truck", "touchscreen", "soft touchscreen",
        "screen", "screens", "ui", "interface", "red glow", "faint red glow",
        "star chart", "map", "modern muse", "hums", "truck hums",
        "silver gleam", "gleam", "reflected", "stainless silver gleam",
        # Night intimacy with edge
        "embrace", "kiss", "passionate", "desire", "eyes", "gaze",
        "whisper", "heart", "lover", "lovers", "together",
        "cockpit", "cab", "alley energy", "neon-lit", "neon lit",
        "sakura petals", "rain streaks", "wet pavement",
        # Launch / flare as electric night energy
        "rocket", "flare", "launch", "plume", "engine", "engines",
        "hobby flare", "private launch", "arc", "smoke",
    },
}

# ---------------------------------------------------------------------------
# Soft vibe boosts (+0.5 each hit in score_styles)
#
# Short "atmosphere words" that tip a close race when the poem already leans
# a certain way — not a substitute for STYLE_KEYWORDS scene coverage.
# romantic_anime / charcoal_sketch: quiet warmth, desert hush, starlit closeness.
# anime_cyberpunk: modern glow, tech-romance, urban night charge.
# ---------------------------------------------------------------------------

VIBE_BOOSTS: Dict[str, set] = {
    "charcoal_sketch": {
        "soft", "delicate", "dreamy", "atmospheric", "light",
        "quiet", "gentle", "faint", "still", "hushed", "tender",
        "desert", "starlit", "starry", "misty", "paper", "sketch",
    },
    "artistic_collage": {
        "colorful", "symbolic", "hopeful", "layered", "artful",
        "becoming", "woven", "fragmented", "reinvented",
    },
    "moody_comic": {
        "dark", "dramatic", "noir", "tense", "cinematic",
        "bittersweet", "stark", "lonely", "heavy", "shadowed",
    },
    "romantic_anime": {
        "romantic", "tender", "warm", "intimate", "gentle",
        "soft", "cozy", "sweet", "close", "shared", "starlit",
        "moonlit", "dreamy", "whispered", "heartfelt",
        "desert", "night", "cosmic",  # cosmic-but-close nights land here
    },
    "anime_cyberpunk": {
        "neon", "urban", "night", "electric", "modern",
        "glowing", "chrome", "futuristic", "edgy", "charged",
        "tech", "digital", "sleek", "passionate",
    },
}


@dataclass
class MatchResult:
    """Scored recommendation for one style."""

    style: Style
    score: float
    hits: List[str]  # keywords that matched

    @property
    def name(self) -> str:
        return self.style.name


def _count_keyword_hits(text_lower: str, keywords: set) -> Tuple[float, List[str]]:
    """
    Score keyword presence. Multi-word phrases count extra.
    Returns (score, list of hit keywords).
    """
    score = 0.0
    hits: List[str] = []
    for kw in keywords:
        if " " in kw:
            if kw in text_lower:
                score += 2.0
                hits.append(kw)
        else:
            # Word-boundary match for single tokens
            if re.search(rf"\b{re.escape(kw)}\b", text_lower):
                score += 1.0
                hits.append(kw)
    return score, hits


# ---------------------------------------------------------------------------
# Visual / mood lexicons (offline helpers for summarize_poem + analyze_mood)
# ---------------------------------------------------------------------------

# Concrete scene material — objects, places, bodies, light, motion, sensory.
# Multi-word phrases score higher when present in a line.
_IMAGERY_PHRASES = {
    "truck bed", "truck's bed", "truck’s bed", "star chart", "hobby rocket",
    "hobby flare", "desert stars", "starry light", "velvet night", "stainless silver",
    "loose sweatshirt", "shared sweatshirt", "soft touchscreen", "private launch",
    "white plume", "grid fin", "max q", "launch pad", "launchpad",
    "martini glass", "cybertruck", "falcon 9", "stainless steel",
}

_IMAGERY_WORDS = {
    # Setting / place
    "desert", "truck", "bed", "cab", "cockpit", "picnic", "blanket", "blankets",
    "sky", "night", "stars", "star", "moon", "moonlight", "earth", "rim",
    "alley", "street", "city", "garden", "room", "bed", "pad", "tower",
    "horizon", "dunes", "field", "window", "orbit", "mars", "cosmos",
    # Objects / tech-prop
    "rocket", "flare", "chart", "map", "touchscreen", "sweatshirt", "cheese",
    "plume", "engine", "engines", "booster", "fairing", "flame", "flames",
    "smoke", "trail", "arc", "gems", "silver", "gleam", "screen", "phone",
    "bottle", "tea", "ramen", "petals", "sakura", "thread", "paper",
    "cybertruck", "starship", "martini", "martinis", "gin", "brine", "glass",
    "glasses", "drink", "drinks",
    # Body / intimacy (strong for scene + people)
    "arms", "hand", "hands", "eyes", "lips", "cheek", "heart", "hearts",
    "breath", "palm", "fingers", "gaze", "embrace", "kiss", "kisses",
    # Action verbs that paint a frame
    "wrap", "wraps", "leap", "leaps", "launch", "launches", "climb", "climbs",
    "spill", "spills", "ignite", "ignites", "glow", "glows", "hum", "hums",
    "whisper", "whispers", "recite", "hold", "held", "squeeze", "squeezing",
    "blaze", "soar", "arc", "arcs", "drift", "shimmer", "quiver",
    "sip", "sips", "shake", "shaken", "stirred", "glisten",
    # Sensory / atmosphere
    "chill", "warm", "warmth", "heat", "soft", "glow", "red", "faint",
    "wind", "rain", "mist", "cold", "bite", "bites", "hush", "quiet",
    "neon", "dark", "light", "dim", "starlit", "starry", "cosmic",
}

# Categories used to diversify which visual beats we keep in the summary.
_SETTING_WORDS = {
    # Places & scene furniture (not fleeting props)
    "desert", "truck", "bed", "cab", "cockpit", "picnic", "sky", "night",
    "moon", "earth", "alley", "street", "city", "garden", "orbit", "mars",
    "horizon", "dunes", "pad", "tower", "window", "rim", "stars", "star",
}
_INTIMACY_WORDS = {
    "arms", "hand", "hands", "eyes", "lips", "cheek", "heart", "hearts",
    "breath", "embrace", "kiss", "kisses", "wrap", "wraps", "hold", "held",
    "whisper", "whispers", "sweatshirt", "warm", "warmth", "soft", "tender",
    "love", "lover", "gaze", "giggle", "shared", "close", "intimate",
}
# Dynamic motion / ignition / flight — keep props that *do something*
_ACTION_PROP_WORDS = {
    "rocket", "flare", "launch", "launches", "leap", "leaps", "climb", "climbs",
    "plume", "flame", "flames", "smoke", "arc", "arcs", "ignite", "ignites",
    "engine", "engines", "spill", "spills", "blaze", "soar", "hum", "hums",
    "swirl", "swirls", "erupt", "erupting", "gallop", "gallops",
}


def _clean_poem_lines(poem_text: str) -> List[str]:
    """Strip markdown noise; keep only substantive verse lines."""
    lines: List[str] = []
    prose_prefixes = (
        "a poem", "inspired by", "join the cosmic", "for starship",
        "check out my", "by ann", "crafted as", "part of my",
    )
    for raw in poem_text.splitlines():
        line = raw.strip().lstrip("#*_> ").strip()
        if not line or line.startswith("---"):
            continue
        # Drop italic/markdown-only leftovers and pure metadata
        bare = line.strip("*_ ").lower()
        if any(bare.startswith(p) for p in prose_prefixes):
            continue
        # Drop epigraph / attribution lines (e.g. "… — Elon Musk")
        if re.search(r"—\s*\w+", line) and len(line) < 80:
            continue
        if len(line) < 4:
            continue
        lines.append(line)
    return lines


def _line_imagery_score(line: str) -> float:
    """
    How strongly a line paints a visual scene.

    Rewards concrete setting/object/body/sensory tokens and multi-word
    image phrases. Mildly prefers mid-length lines (not titles, not essays).
    """
    lower = line.lower()
    score = 0.0

    for phrase in _IMAGERY_PHRASES:
        if phrase in lower:
            score += 3.0

    for word in _IMAGERY_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", lower):
            score += 1.0

    # Light length preference: imageable lyric lines tend to sit ~25–95 chars
    n = len(line)
    if 25 <= n <= 95:
        score += 0.8
    elif n < 18:
        # Title-ish stubs are weak — unless they pack a hard prop ("We sip martinis")
        if score < 2.0:
            score -= 1.0
    elif n > 120:
        score -= 0.5

    return score


def _category_score(line: str, words: set) -> float:
    """How strongly a line hits a category bag (setting / intimacy / action)."""
    lower = line.lower()
    score = 0.0
    for w in words:
        if " " in w:
            if w in lower:
                score += 2.0
        elif re.search(rf"\b{re.escape(w)}\b", lower):
            score += 1.0
    return score


# High-value scene anchors — used when filling so we cover distinct props/places.
# Prefer concrete props/places over decorative glitter ("silver gleam").
_SIGNATURE_ANCHORS = {
    "picnic", "truck", "desert", "cockpit", "cab", "bed", "sweatshirt",
    "flare", "rocket", "chart", "map", "touchscreen", "arms", "eyes",
    "whisper", "moon", "neon", "sakura", "plume", "flame", "engine",
    "rain", "alley", "kiss", "embrace", "heart", "giggle",
    "martini", "martinis", "gin", "cybertruck", "starship",
}
# Mild anchors: half-weight novelty (common atmosphere / decorative words).
# Note: deliberately omit bare "star"/"stars" — they collide with "star chart"
# and flood every cosmic love poem, drowning picnic/cockpit/flare coverage.
_MILD_ANCHORS = {
    "night", "light", "dark", "sky", "silver", "gleam",
    "cheese", "wind", "soft", "blanket", "blankets", "chill",
    "lips", "drink", "glass",
}


def _anchor_tokens(line: str) -> set:
    """Signature imagery tokens present in a line (strong + mild)."""
    lower = line.lower()
    strong = {
        a for a in _SIGNATURE_ANCHORS
        if re.search(rf"\b{re.escape(a)}\b", lower)
    }
    mild = {
        a for a in _MILD_ANCHORS
        if re.search(rf"\b{re.escape(a)}\b", lower)
    }
    return strong | mild


# Scene-defining places get a little extra novelty weight when still uncovered
_PRIORITY_PLACES = {
    "desert", "cockpit", "picnic", "alley", "neon", "cab", "orbit", "mars",
}


def _novelty_score(line: str, covered: set) -> Tuple[float, float]:
    """
    How many *new* scene anchors a line would add.

    Returns (strong_novelty, mild_novelty) so fill ranking can require real
    props (picnic, cockpit, flare…) to beat decorative atmosphere lines.
    Priority places (desert, cockpit, …) get a small bonus when uncovered.
    """
    lower = line.lower()
    strong_new = 0.0
    mild_new = 0.0
    for a in _SIGNATURE_ANCHORS:
        if a in covered:
            continue
        if re.search(rf"\b{re.escape(a)}\b", lower):
            strong_new += 1.5 if a in _PRIORITY_PLACES else 1.0
    for a in _MILD_ANCHORS:
        if a in covered:
            continue
        if re.search(rf"\b{re.escape(a)}\b", lower):
            mild_new += 0.5
    return strong_new, mild_new


def _pick_visual_lines(lines: List[str], max_lines: int = 4) -> List[str]:
    """
    Choose a diverse set of high-imagery lines in poem order.

    Strategy:
      1. Score every line for overall visual density.
      2. Take the *best line in each category* (setting / intimacy / action)
         so a real place-line beats a line that only says "stars".
      3. Fill remaining slots with lines that add *new* signature anchors
         (picnic, cockpit, flare, …) — coverage-aware, not pure score.
      4. Skip title-like stubs (very short, low imagery).
    """
    if not lines:
        return []

    # Drop title stubs early (e.g. "Starlit Cockpit" alone) — but keep short
    # prop-dense lines ("We sip martinis,") that still paint a real object.
    candidates = [
        (i, line)
        for i, line in enumerate(lines)
        if not (
            len(line) < 22
            and _line_imagery_score(line) < 2.5
            and not any(_line_mentions_label(line, lab) for lab, _ in _KEY_VISUAL_CATALOG)
        )
    ]
    if not candidates:
        candidates = list(enumerate(lines))

    scored = [
        (i, line, _line_imagery_score(line)) for i, line in candidates
    ]
    vivid = [t for t in scored if t[2] >= 2.0]
    pool = vivid if vivid else scored
    pool_sorted = sorted(pool, key=lambda t: (-t[2], t[0]))

    chosen_idx: List[int] = []
    used: set = set()

    def _take_best_in_category(word_set: set, min_cat_score: float = 1.0) -> None:
        """Pick the line with the highest *category* score, not overall score."""
        best = None  # (cat_score, strong_anchors, overall_score, index)
        for i, line, overall in pool:
            if i in used:
                continue
            cat = _category_score(line, word_set)
            if cat < min_cat_score:
                continue
            # Prefer lines dense with concrete props when category scores tie
            strong_anchors = sum(
                1 for a in _SIGNATURE_ANCHORS
                if re.search(rf"\b{re.escape(a)}\b", line.lower())
            )
            key = (cat, strong_anchors, overall)
            if best is None or key > (best[0], best[1], best[2]):
                best = (cat, strong_anchors, overall, i)
        if best is not None:
            used.add(best[3])
            chosen_idx.append(best[3])

    # Diversity passes: true best setting / intimacy / action beats
    if max_lines >= 1:
        _take_best_in_category(_SETTING_WORDS, min_cat_score=1.0)
    if max_lines >= 2:
        _take_best_in_category(_INTIMACY_WORDS, min_cat_score=1.0)
    if max_lines >= 3:
        _take_best_in_category(_ACTION_PROP_WORDS, min_cat_score=1.0)

    # Coverage-aware fill: prefer lines that introduce new signature anchors
    covered: set = set()
    for i in chosen_idx:
        covered |= _anchor_tokens(lines[i])

    while len(chosen_idx) < max_lines:
        # Rank by strong novelty first, then mild, then overall imagery
        best = None  # (strong, mild, overall, index)
        for i, line, overall in pool:
            if i in used:
                continue
            strong_n, mild_n = _novelty_score(line, covered)
            key = (strong_n, mild_n, overall)
            if best is None or key > (best[0], best[1], best[2]):
                best = (strong_n, mild_n, overall, i)
        if best is None:
            break
        i = best[3]
        used.add(i)
        chosen_idx.append(i)
        covered |= _anchor_tokens(lines[i])
        # Stop padding once strong novelty dries up and we already have a scene
        if best[0] <= 0 and len(chosen_idx) >= 3:
            break

    # Restore poem order so the summary reads like a scene unfolding
    chosen_idx.sort()
    return [lines[i] for i in chosen_idx]


def _tidy_fragment(line: str) -> str:
    """Normalize a verse line into a summary fragment (no trailing punct)."""
    frag = collapse_whitespace(line)
    # Strip trailing clause punctuation — we join fragments with "; "
    frag = frag.strip(" \t,;:.—–-!?")
    return frag


def _weighted_signal_score(text_lower: str, weights: Dict[str, float]) -> float:
    """
    Sum weights for each signal word/phrase found in text.
    Multi-word keys match as substrings; single tokens use word boundaries.
    """
    total = 0.0
    for term, weight in weights.items():
        if " " in term:
            if term in text_lower:
                total += weight
        else:
            if re.search(rf"\b{re.escape(term)}\b", text_lower):
                total += weight
    return total


def analyze_mood(poem_text: str) -> str:
    """
    Label the dominant emotional mood for prompt filling.

    Weighted signal bags (not raw hit counts) so warm/romantic language can
    outrank sparse cosmic nouns — e.g. a desert picnic under stars with a
    shared sweatshirt should read "tender and intimate", not merely "cosmic".

    Pure Python, fast, no LLM.
    """
    t = poem_text.lower()

    # Weights: intimate/relational terms are boosted; bare space props are
    # kept real but not allowed to steamroll closeness language.
    signals: Dict[str, Dict[str, float]] = {
        "tender and intimate": {
            # Core romance / closeness (strong)
            "love": 2.0, "lover": 2.0, "lovers": 2.0, "kiss": 2.2, "kisses": 2.2,
            "embrace": 2.2, "tender": 2.0, "tenderness": 2.0, "intimate": 2.2,
            "intimacy": 2.2, "whisper": 2.0, "whispers": 2.0, "whispered": 2.0,
            "soft": 1.2, "gentle": 1.5, "warm": 1.6, "warmth": 2.0,
            "hold": 1.5, "held": 1.5, "wrap": 1.6, "wraps": 1.6, "wrapped": 1.6,
            "arms": 1.6, "hand": 1.2, "hands": 1.2, "palm": 1.2,
            "eyes": 1.4, "gaze": 1.5, "heart": 1.5, "hearts": 1.5,
            "breath": 1.3, "lips": 1.6, "cheek": 1.5, "giggle": 1.4,
            "shared": 1.5, "close": 1.4, "cozy": 1.6, "together": 1.5,
            "sweatshirt": 1.6, "blanket": 1.0, "blankets": 1.0,
            "cockpit": 1.2, "touch": 1.5, "darling": 1.8, "beloved": 1.8,
            "you and i": 2.0, "your arms": 2.2, "our eyes": 2.0,
            "close and warm": 2.5, "in our eyes": 2.2,
            "longing": 1.5, "yearn": 1.4, "yearning": 1.4,
        },
        "bittersweet and reflective": {
            "bittersweet": 2.5, "memory": 1.6, "memories": 1.6, "remember": 1.4,
            "gone": 1.5, "miss": 1.6, "missing": 1.5, "regret": 1.8,
            "ache": 1.7, "aching": 1.7, "loss": 1.6, "grief": 1.8,
            "almost": 1.2, "still": 0.8, "echo": 1.3, "faded": 1.4,
            "yesterday": 1.2, "goodbye": 1.8, "farewell": 1.7,
            "tears": 1.5, "lonely": 1.3, "distance": 1.4,
        },
        "fiery and passionate": {
            "fire": 1.5, "flame": 1.5, "flames": 1.5, "burn": 1.5, "burning": 1.5,
            "passion": 2.2, "passionate": 2.2, "desire": 2.0, "blaze": 1.5,
            "ignite": 1.8, "ignites": 1.8, "ignited": 1.8, "heat": 1.3,
            "roar": 1.3, "wild": 1.2, "electric": 1.4, "pulse": 1.2,
            "thrust": 1.2, "erupt": 1.4, "hungry": 1.5, "fierce": 1.5,
        },
        "lonely and nocturnal": {
            "alone": 2.0, "lonely": 2.2, "loneliness": 2.2, "solitude": 1.8,
            "empty": 1.6, "emptiness": 1.6, "silence": 1.5, "silent": 1.5,
            "midnight": 1.5, "darkness": 1.4, "void": 1.6, "shadow": 1.1,
            "shadows": 1.1, "cold": 1.3, "chill": 1.2, "isolation": 1.8,
            "night": 0.9, "dark": 0.9,  # common; keep mild unless stacked
        },
        "hopeful and ascending": {
            "hope": 2.0, "hopeful": 2.0, "rise": 1.5, "rising": 1.5,
            "become": 1.6, "becoming": 1.8, "dream": 1.3, "dreams": 1.3,
            "soar": 1.5, "future": 1.4, "reinvent": 1.8, "reinvention": 1.8,
            "ascend": 1.6, "launch": 1.0, "dawn": 1.3, "begin": 1.2,
            "alive": 1.3, "wonder": 1.3, "dare": 1.2,
        },
        "cosmic and awe-struck": {
            # Present but softer — stars/rocket alone should not beat intimacy
            "star": 0.7, "stars": 0.7, "starry": 0.9, "starlit": 0.9,
            "orbit": 1.2, "cosmos": 1.6, "cosmic": 1.5, "galaxy": 1.5,
            "mars": 1.1, "nebula": 1.4, "constellation": 1.3,
            "rocket": 0.7, "booster": 0.9, "falcon": 1.0, "starship": 1.0,
            "universe": 1.4, "celestial": 1.4, "awe": 1.6, "wonder": 1.0,
            "infinite": 1.2, "void": 0.8, "space": 0.9,
        },
    }

    best_label = "contemplative and emotionally resonant"
    best_score = 0.0

    for label, weights in signals.items():
        score = _weighted_signal_score(t, weights)
        # Tiny tie-break: prefer tender when scores are nearly equal and
        # closeness language is present (stops cosmic from winning 4.2 vs 4.0).
        if label == "tender and intimate" and score > 0:
            score += 0.35
        if score > best_score:
            best_score = score
            best_label = label

    return best_label


# ---------------------------------------------------------------------------
# High-value proper nouns & distinctive objects
#
# Matched case-insensitively in the poem; returned in a stable display form
# so Imagine prompts keep "Cybertruck" / "Falcon 9" instead of generic trucks
# or rockets. Multi-word patterns are checked first (longest first).
# ---------------------------------------------------------------------------

# (display_label, match_patterns_lowercased)
# Longer / more specific patterns win via sort + span claiming in extract_key_visuals.
_KEY_VISUAL_CATALOG: List[Tuple[str, Tuple[str, ...]]] = [
    # Craft / brands / proper nouns
    ("Tesla Cybertruck", ("tesla cybertruck", "tesla cyber truck")),
    ("Cybertruck", ("cybertruck", "cyber truck")),
    ("Falcon 9", ("falcon 9", "falcon-9", "falcon nine")),
    ("Falcon Heavy", ("falcon heavy",)),
    ("Starship", ("starship",)),
    ("Super Heavy", ("super heavy",)),
    ("Dragon", ("crew dragon", "dragon capsule")),  # avoid bare "dragon" noise
    ("Raptor", ("raptor engine", "raptor engines", "raptors")),
    # Signature scene objects (this poetic voice)
    ("star chart", ("star chart", "star chart's", "star chart’s")),
    ("hobby flare", ("hobby flare",)),
    ("hobby rocket", ("hobby rocket",)),
    ("truck bed", ("truck bed", "truck's wide bed", "truck’s wide bed", "truck's bed", "truck’s bed")),
    ("stainless steel", ("stainless steel", "stainless silver gleam", "stainless silver", "stainless")),
    ("cockpit", ("cockpit", "starlit cockpit")),
    ("touchscreen", ("touchscreen", "touch screen", "soft touchscreen")),
    ("shared sweatshirt", ("shared sweatshirt", "loose sweatshirt", "sweatshirt")),
    ("picnic", ("picnic",)),
    ("desert", ("desert", "deserts")),
    ("booster", ("booster", "boosters")),
    ("grid fins", ("grid fin", "grid fins")),
    ("launchpad", ("launchpad", "launch pad")),
    # Drinks / intimate props (e.g. Martinis poem — must not become generic glasses)
    ("martini glass", ("martini glass", "martini glasses", "martinis", "martini")),
    ("gin", ("gin",)),
]


# Brands / craft names get priority when we must trim the key-visual list
_PRIORITY_KEY_VISUALS = {
    "tesla cybertruck", "cybertruck", "falcon 9", "falcon heavy",
    "starship", "super heavy", "martini glass", "star chart",
    "hobby flare", "hobby rocket", "stainless steel",
}


def _label_needles(label: str) -> List[str]:
    """
    Substrings used to test whether a summary line already 'covers' a key visual.

    "martini glass" also matches poem lines that only say "martinis".
    """
    lower = label.lower()
    needles = [lower]
    # Also try catalog patterns for this display label
    for display, patterns in _KEY_VISUAL_CATALOG:
        if display.lower() == lower:
            needles.extend(patterns)
            break
    # Light stemming: drop trailing 's' on last word for plural coverage
    if lower.endswith("s") and " " not in lower:
        needles.append(lower[:-1])
    # "martini glass" ↔ "martini" / "martinis"
    first = lower.split()[0] if lower else ""
    if first and first not in needles:
        needles.append(first)
        needles.append(first + "s")
    # unique, longest first (more specific wins in scans)
    uniq: List[str] = []
    for n in sorted(set(needles), key=len, reverse=True):
        if n:
            uniq.append(n)
    return uniq


def _line_mentions_label(line: str, label: str) -> bool:
    """True if *line* contains any needle for *label*."""
    lower = line.lower()
    for needle in _label_needles(label):
        if " " in needle or "-" in needle:
            if needle in lower:
                return True
        elif re.search(rf"\b{re.escape(needle)}\b", lower):
            return True
    return False


def extract_key_visuals(poem_text: str, *, max_items: int = 10) -> List[str]:
    """
    Detect high-value proper nouns and distinctive objects in the poem.

    Returns canonical display labels in poem order (first occurrence),
    e.g. ["Cybertruck", "star chart", "hobby flare", "cockpit", "martini glass"].
    Pure Python — no LLM. Used by summarize_poem and prompt builders.

    When more than *max_items* match, brand/signature props are preferred so
    Cybertruck / Falcon 9 are not dropped behind milder scene words.
    """
    if not poem_text or not poem_text.strip():
        return []

    text_lower = poem_text.lower()
    # Sort patterns by length so "tesla cybertruck" / "falcon 9" win over shorter hits
    catalog = sorted(
        _KEY_VISUAL_CATALOG,
        key=lambda item: -max(len(p) for p in item[1]),
    )

    found: List[Tuple[int, str]] = []  # (start_index, display_label)
    claimed_spans: List[Tuple[int, int]] = []

    def _overlaps(start: int, end: int) -> bool:
        for a, b in claimed_spans:
            if start < b and end > a:
                return True
        return False

    for display, patterns in catalog:
        best_pos = None
        best_span = None
        for pat in patterns:
            # Word-ish boundaries for single tokens; substring for phrases
            if " " in pat or "-" in pat:
                idx = text_lower.find(pat)
                if idx < 0:
                    continue
                span = (idx, idx + len(pat))
            else:
                m = re.search(rf"\b{re.escape(pat)}\b", text_lower)
                if not m:
                    continue
                span = (m.start(), m.end())
                idx = m.start()
            if best_pos is None or idx < best_pos:
                best_pos = idx
                best_span = span
        if best_pos is None or best_span is None:
            continue
        if _overlaps(best_span[0], best_span[1]):
            continue
        claimed_spans.append(best_span)
        found.append((best_pos, display))

    found.sort(key=lambda t: t[0])
    # Dedupe labels while preserving order (prefer first / more-specific hit)
    ordered: List[str] = []
    seen = set()
    for _pos, label in found:
        key = label.lower()
        # Collapse "Tesla Cybertruck" vs bare "Cybertruck" if both somehow appear
        if key == "cybertruck" and "tesla cybertruck" in seen:
            continue
        if key == "tesla cybertruck":
            seen.discard("cybertruck")
            ordered = [x for x in ordered if x.lower() != "cybertruck"]
        if key in seen:
            continue
        seen.add(key)
        ordered.append(label)

    if len(ordered) <= max_items:
        return ordered

    # Prefer brand/signature props, then fill remaining slots in poem order
    priority = [x for x in ordered if x.lower() in _PRIORITY_KEY_VISUALS]
    rest = [x for x in ordered if x.lower() not in _PRIORITY_KEY_VISUALS]
    chosen = (priority + rest)[:max_items]
    # Restore poem order for the chosen set
    rank = {label: i for i, label in enumerate(ordered)}
    chosen.sort(key=lambda L: rank[L])
    return chosen


# ---------------------------------------------------------------------------
# Couple / figure defaults
#
# When a poem is clearly about two people and never specifies gender (or only
# uses second-person address), we gently default to a romantic man + woman.
# Special direction from the CLI can override this entirely.
# ---------------------------------------------------------------------------

# Romantic / dual-presence signals (two people in a shared scene)
_COUPLE_SIGNALS: Dict[str, float] = {
    "we": 1.5, "us": 1.5, "our": 1.2, "ours": 1.2,
    "you and i": 2.5, "you & i": 2.5, "you and me": 2.2,
    "lover": 2.0, "lovers": 2.2, "couple": 2.0, "together": 1.4,
    "your arms": 2.0, "your eyes": 1.8, "your lips": 2.0, "your hand": 1.6,
    "your hands": 1.6, "your smile": 1.5, "your heart": 1.5,
    "kiss": 1.4, "kisses": 1.4, "embrace": 1.6, "shared": 1.3,
    "both of us": 2.2, "the two of us": 2.5, "side by side": 1.5,
    "hold me": 1.8, "wrap me": 1.8, "my love": 1.6, "darling": 1.4,
    "yours neat": 1.2, "mine dirty": 1.2,  # dual drinks / dual figures
}

# Explicit gender / orientation cues that *cancel* the default assumption
_GENDER_OVERRIDE_TERMS = {
    # Same-gender / non-default pairings
    "two women", "two men", "two girls", "two guys", "two boys",
    "both women", "both men", "both female", "both male",
    "gay", "lesbian", "wlw", "mlm", "sapphic", "queer couple",
    "same-sex", "same sex", "nonbinary", "non-binary", "non binary",
    "genderfluid", "trans man", "trans woman", "transgender",
    "they/them", "he/him", "she/her",  # explicit pronoun sets often mean override
    # Solo / multi already specified
    "solo", "alone figure", "single figure", "one person", "three people",
    # Explicit hetero already stated — still ok to reinforce, but these count
    # as "specified" so we can skip *re*-assuming if desired; we treat them
    # as "already clear" and still allow the gentle default line (harmless).
}

# Pronouns that suggest a specific gendered third person (not pure "you/I")
_MASC_PRONOUNS = re.compile(r"\b(he|him|his)\b", re.I)
_FEM_PRONOUNS = re.compile(r"\b(she|her|hers)\b", re.I)
_THEY_PRONOUNS = re.compile(r"\b(they|them|their|theirs)\b", re.I)

# Default figure line injected into Imagine prompts when appropriate
DEFAULT_COUPLE_INSTRUCTION = (
    "Figures: a romantic male/female couple (a man and a woman), "
    "unless the special direction says otherwise."
)


def _has_gender_override_language(text: str) -> bool:
    """True if the poem (or special direction) already specifies casting/gender."""
    lower = text.lower()
    for term in _GENDER_OVERRIDE_TERMS:
        if term in lower:
            return True
    # Explicit pairings spelled out
    if re.search(r"\b(two|both)\s+(women|men|girls|guys|boys)\b", lower):
        return True
    if re.search(
        r"\b(man and (a )?woman|woman and (a )?man|"
        r"male and female|female and male|"
        r"heterosexual|straight couple)\b",
        lower,
    ):
        # Already specified — treat as override so we don't double-stack wording
        # when the poet already said it; prompts.py still may reinforce via special dir.
        return True
    return False


def poem_suggests_couple(poem_text: str) -> bool:
    """
    Heuristic: is this verse clearly about two people in a shared intimate scene?

    Uses weighted dual-presence signals (we/us/our, your arms, lovers, …).
    Pure Python — no LLM.
    """
    if not poem_text or not poem_text.strip():
        return False
    score = _weighted_signal_score(poem_text.lower(), _COUPLE_SIGNALS)
    return score >= 3.0


def poem_has_explicit_gender_cues(poem_text: str) -> bool:
    """
    True when the poem already signals gender/orientation we should not override.

    - Explicit override phrases (two women, gay, nonbinary, …)
    - Mixed or one-sided third-person pronouns that already cast the pair
    - they/them used as people pronouns (not weather/objects — best-effort)
    """
    if not poem_text or not poem_text.strip():
        return False
    if _has_gender_override_language(poem_text):
        return True

    # Third-person gender pronouns: if present, the poet already cast someone
    has_m = bool(_MASC_PRONOUNS.search(poem_text))
    has_f = bool(_FEM_PRONOUNS.search(poem_text))
    if has_m or has_f:
        return True

    # they/them as people is ambiguous; only treat as cue when stacked with
    # couple language and no second-person intimacy (you/I poems often say "they"
    # for objects — "they glisten"). Require "they are" / "them both" style.
    if re.search(
        r"\b(they are|they're|them both|their eyes|their hands|their lips)\b",
        poem_text,
        re.I,
    ):
        return True

    return False


def infer_default_couple_instruction(
    poem_text: str,
    *,
    special_direction: str = "",
) -> str:
    """
    Return a gentle couple instruction when appropriate, else "".

    Rules:
      1. Special direction always wins — if it mentions casting/gender/solo,
         return "" (the special direction itself is injected elsewhere).
      2. Poem must look like two people (we/us/your arms/lovers…).
      3. Poem must not already specify gender/orientation via pronouns/phrases.
      4. Otherwise: default romantic male/female couple.
    """
    direction = (special_direction or "").strip()
    if direction and (
        _has_gender_override_language(direction)
        or re.search(
            r"\b(solo|single|alone|one person|figure|couple|man|woman|"
            r"men|women|male|female|gay|lesbian|non[- ]?binary)\b",
            direction,
            re.I,
        )
    ):
        # Poet is steering figures — do not pile on the default
        return ""

    if not poem_suggests_couple(poem_text):
        return ""
    if poem_has_explicit_gender_cues(poem_text):
        return ""
    return DEFAULT_COUPLE_INSTRUCTION


def summarize_poem(poem_text: str, max_sentences: int = 3, max_chars: int = 420) -> str:
    """
    Build a short, *visual / scene-oriented* summary from the poem.

    Offline (no LLM). Logic:
      1. Clean verse lines (drop markdown / prose notes).
      2. Score each line for concrete imagery (objects, setting, bodies,
         sensory detail, action).
      3. Pick a diverse handful of high-scoring lines (setting + intimacy +
         action/prop when possible) so one motif cannot dominate.
      4. Join them as a compact scene montage for {poem_summary} prompts.
      5. Boost distinctive proper nouns / key objects so they are not lost
         (Cybertruck, Falcon 9, star chart, hobby flare, cockpit, …).

    Aim: 1–3 strong beats / under ~400 characters — e.g. for "Starlit Cockpit"
    capture truck-bed picnic under desert stars, hobby rocket flare, star-chart
    glow, shared sweatshirt, intimate cockpit warmth.
    """
    lines = _clean_poem_lines(poem_text)
    if not lines:
        return "An evocative poetic scene drawn from verse."

    # Distinctive objects — prefer lines that carry them when filling beats
    key_visuals = extract_key_visuals(poem_text)

    # How many visual beats to keep.
    # Default max_sentences=3 → up to 5 beats so a scene can hold setting +
    # intimacy + action + a couple of signature props (flare, star chart, etc.).
    max_beats = max(3, min(max_sentences + 2, 5))
    visual = _pick_visual_lines(lines, max_lines=max_beats)

    # Soft boost: if a key visual is missing from chosen lines, try to swap in
    # one vivid line that names it (keeps summary faithful to the poem's props).
    # Uses flexible needles so "martini glass" matches a line that only says "martinis".
    if key_visuals and visual:
        for label in key_visuals:
            if any(_line_mentions_label(L, label) for L in visual):
                continue
            # Find a candidate line that mentions this object
            for line in lines:
                if line in visual:
                    continue
                if _line_mentions_label(line, label) and _line_imagery_score(line) >= 1.0:
                    # Replace the lowest-imagery chosen line to free a slot
                    weakest_i = min(
                        range(len(visual)),
                        key=lambda i: _line_imagery_score(visual[i]),
                    )
                    if _line_imagery_score(visual[weakest_i]) <= _line_imagery_score(line) + 2.0:
                        visual[weakest_i] = line
                    break
        # Restore poem order after any swaps
        order = {line: i for i, line in enumerate(lines)}
        visual = sorted(visual, key=lambda L: order.get(L, 10_000))

    if not visual:
        # Fallback: first non-title mid-length lines
        visual = [L for L in lines if 20 <= len(L) <= 100][:max_sentences] or lines[:2]

    fragments = [_tidy_fragment(L) for L in visual if _tidy_fragment(L)]
    # Semicolon montage reads well inside image prompts
    summary = "; ".join(fragments)
    summary = collapse_whitespace(summary)

    # If still weak (sparse imagery poem), fall back to longest mid lines joined
    if _line_imagery_score(summary) < 2.0 and len(lines) >= 2:
        mid = sorted(
            lines,
            key=lambda L: (-_line_imagery_score(L), abs(50 - len(L))),
        )[:max_sentences]
        mid_ordered = [L for L in lines if L in set(mid)]
        summary = "; ".join(_tidy_fragment(L) for L in mid_ordered)

    # Explicit key-visual tagline so proper nouns survive style packing
    if key_visuals:
        missing = [
            k for k in key_visuals
            if not _line_mentions_label(summary, k)
        ]
        # Always surface the full short list when space allows (reinforces hits too)
        tag_items = key_visuals[:6]
        sep = "" if summary.endswith((".", "!", "?", "…")) else "."
        tag = f"{sep} Key visuals: " + ", ".join(tag_items) + "."
        if len(summary) + len(tag) <= max_chars:
            summary = summary + tag
        elif missing:
            # Fit only what is still absent
            short = f"{sep} Key visuals: " + ", ".join(missing[:4]) + "."
            if len(summary) + len(short) <= max_chars:
                summary = summary + short

    if len(summary) > max_chars:
        # Hard cap: cut on a semicolon or word boundary (prefer keeping key tag)
        clipped = summary[: max_chars - 1]
        if ";" in clipped:
            clipped = clipped.rsplit(";", 1)[0].rstrip()
        else:
            clipped = clipped.rsplit(" ", 1)[0]
        summary = clipped + "…"

    return summary


def score_styles(
    poem_text: str,
    styles: Dict[str, Style],
) -> List[MatchResult]:
    """
    Score every loaded style against the poem. Higher is better.
    Unknown styles (no keyword bag) get a tiny baseline from vibe word overlap.
    """
    text_lower = poem_text.lower()
    results: List[MatchResult] = []

    for name, style in styles.items():
        keywords = STYLE_KEYWORDS.get(name, set())
        score, hits = _count_keyword_hits(text_lower, keywords)

        # Vibe boosts from style.vibe + notes + catalog vibe words
        boost_words = VIBE_BOOSTS.get(name, set())
        vibe_blob = f"{style.vibe} {style.notes}".lower()
        for w in boost_words:
            if re.search(rf"\b{re.escape(w)}\b", text_lower):
                score += 0.5
                if w not in hits:
                    hits.append(f"+{w}")

        # Tiny affinity if poem echoes words already in the style description
        for token in re.findall(r"[a-z]{5,}", vibe_blob):
            if token in {"style", "atmosphere", "characters", "quality"}:
                continue
            if re.search(rf"\b{re.escape(token)}\b", text_lower):
                score += 0.15

        # Soft baseline so empty poems still rank something
        if score == 0:
            score = 0.01

        results.append(MatchResult(style=style, score=score, hits=hits[:12]))

    results.sort(key=lambda r: (-r.score, r.style.name))
    return results


def suggest_style(
    poem_text: str,
    styles: Dict[str, Style],
) -> MatchResult:
    """Return the top-scoring style match."""
    ranked = score_styles(poem_text, styles)
    return ranked[0]
