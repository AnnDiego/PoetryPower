#!/usr/bin/env python3
"""
poem_analyzer.py — Your snarky, cosmic, tech-poetess best friend for poem feedback.

Run:
    python scripts/poem_analyzer.py

What it does:
- Accepts pasted poem OR path to .md/.txt (or a voice-memo transcript)
- Analyzes meter/syllables, rhyme scheme, sensory imagery, and that signature
  cosmic/sassy/SpaceX vibe
- Delivers structured feedback + 3-5 playful, encouraging, slightly savage
  improvement suggestions in the Chief Poet voice
- Saves a full markdown report next to the original (or a sensible default)

Keep it simple. Pure stdlib. Maximum starlight, minimum gatekeeping.
"""

import re
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import random


# =============================================================================
# VOICE & CONSTANTS (tech-poetess edition)
# =============================================================================

BANNER = r"""
   /\
  /  \
 /____\   poem_analyzer.py
 |    |   (snarky poet friend mode: ON)
 |    |
 |____|
  ||||
  ||||   "Let's make this thing land clean."
"""

INTRO = (
    "Alright, word-weaver. Time to tear the verses apart and glue them back "
    "together stronger than a tower-caught booster.\n"
)

FILLER_WORDS = {
    "um", "uh", "er", "ah", "like", "you know", "so", "basically",
    "kinda", "sort of", "i mean", "well", "just", "really", "very"
}

# Sensory & imagery seeds (curated, not exhaustive — we keep it light)
SENSORY = {
    "visual": {
        "star", "stars", "dark", "night", "light", "glow", "gleam", "blaze",
        "flame", "fire", "red", "crimson", "blue", "velvet", "sky", "arc",
        "plume", "smoke", "crater", "shadow", "bright", "glide", "gleaming",
        "shimmer", "flash", "orange", "silver", "white", "black", "marble"
    },
    "auditory": {
        "roar", "rumble", "pulse", "beat", "hush", "cheer", "boom", "whisper",
        "song", "static", "hum", "tick", "sound", "crack", "thunder", "silence",
        "voice", "call", "shout", "scream", "echo", "quiet"
    },
    "tactile": {
        "quake", "tremble", "vibration", "burn", "bite", "warm", "cold", "squeeze",
        "touch", "ground", "shake", "soft", "raw", "trembling", "shaking",
        "pressure", "weight", "grit", "dust", "heat", "chill", "grip"
    },
    "olfactory": {"acrid", "smoke", "burn", "ash", "scent", "smell", "ozone"},
    "taste": {"bitter", "sweet", "ash", "metal", "salt"},
}

SPACEX_KEYWORDS = {
    "falcon", "falcon 9", "starship", "super heavy", "booster", "boosters",
    "countdown", "max q", "liftoff", "lift-off", "stage", "fairing", "fairings",
    "reentry", "re-entry", "tiles", "tower", "catch", "grid fin", "grid fins",
    "thrust", "orbit", "mars", "launch", "rocket", "rockets", "engine", "engines",
    "ignition", "hotfire", "hot fire", "sep", "separation", "dragon", "crew",
    "landing", "landed", "octaweb", "rudd", "rud", "telemetry", "static fire"
}

COSMIC_KEYWORDS = {
    "cosmic", "cosmos", "universe", "galaxy", "star", "stars", "moon", "sun",
    "planet", "mars", "sky", "night", "constellation", "nebula", "void",
    "infinite", "eternal", "ignite", "blaze", "soar", "arc", "flame", "fire",
    "spark", "dream", "dare", "constellations", "heavens", "celestial"
}

JOY_SPARK_WORDS = {
    "heart", "joy", "spark", "bubbling", "laugh", "grin", "wink", "cheek",
    "kiss", "squeeze", "wild", "childlike", "enchanted", "wonder", "awe",
    "high-five", "high fives", "giddy", "thrill", "alive"
}


# =============================================================================
# TEXT UTILITIES
# =============================================================================

def clean_transcript(text: str) -> str:
    """Lightly sanitize voice-memo style input (remove fillers, collapse junk)."""
    t = text.lower()
    for filler in sorted(FILLER_WORDS, key=len, reverse=True):
        t = re.sub(rf"\b{re.escape(filler)}\b", "", t, flags=re.IGNORECASE)
    # collapse repeated spaces/newlines but keep paragraph breaks
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r" +", " ", t).strip()
    return t


def get_lines(text: str):
    """Return non-empty-stripped lines + original lines list."""
    raw_lines = text.splitlines()
    stripped = [l.strip() for l in raw_lines]
    return raw_lines, stripped


def get_last_word(line: str) -> str:
    """Extract the last word-ish token from a line (letters + apostrophes)."""
    tokens = re.findall(r"[A-Za-z']+", line)
    return tokens[-1] if tokens else ""


def get_rhyme_key(word: str) -> str:
    """Crude but effective rhyme tail: from last vowel cluster onward."""
    w = re.sub(r"[^a-z']", "", word.lower())
    if not w:
        return ""
    # strip common inflections so "lights" and "light" group
    w = re.sub(r"(?:'s|s|es|ed|ing|ly|ier|iest)$", "", w)
    vowels = set("aeiouy")
    for i in range(len(w) - 1, -1, -1):
        if w[i] in vowels:
            return w[i:]
    return w[-2:] if len(w) >= 2 else w


def keys_are_similar(k1: str, k2: str) -> bool:
    if not k1 or not k2:
        return False
    if k1 == k2:
        return True
    if len(k1) >= 2 and len(k2) >= 2 and k1[-2:] == k2[-2:]:
        return True
    if k1 in k2 or k2 in k1:
        return True
    return False


def count_syllables(word: str) -> int:
    """Heuristic syllable counter. Good enough for poetry feedback. No NLTK."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0

    # Hand-tuned common poetry/rocket words
    exceptions = {
        "people": 2, "business": 2, "different": 3, "probably": 3,
        "interesting": 4, "every": 2, "family": 3, "camera": 3,
        "poem": 2, "poems": 2, "rocket": 2, "rockets": 2,
        "booster": 2, "boosters": 2, "countdown": 2, "falcon": 2,
        "starship": 2, "fairing": 2, "fairings": 2, "ignition": 3,
        "separation": 4, "reentry": 3, "re-entry": 3, "landing": 2,
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

    # Silent e at end (rough)
    if w.endswith("e") and count > 1 and not w.endswith("le"):
        count -= 1
    # -le after consonant usually adds a syllable (table, tremble)
    if w.endswith("le") and len(w) > 2 and w[-3] not in vowels:
        count += 1

    return max(1, count)


def line_syllables(line: str) -> int:
    words = re.findall(r"[A-Za-z']+", line)
    return sum(count_syllables(w) for w in words)


# =============================================================================
# THE ACTUAL ANALYSIS
# =============================================================================

def analyze_poem(text: str):
    """Return a big dict of everything we can say about this poem."""
    original_text = text
    cleaned = clean_transcript(text)  # harmless if not a transcript

    raw_lines, stripped_lines = get_lines(text)
    all_poetic_lines = [l for l in stripped_lines if l]

    # Filter to actual verse lines (skip long prose, markdown headers, file intro text, separators)
    # This makes stats meaningful even when user points at a full .md with frontmatter + About
    verse_lines = []
    prose_hints = ("a poem ", "inspired by ", "join the cosmic", "for starship", "check out my", "see my full")
    for l in all_poetic_lines:
        cl = l.strip()
        if not cl:
            continue
        if len(cl) > 95:
            continue
        # must contain at least one letter to count as verse
        if not re.search(r"[A-Za-z]", cl):
            continue
        cl_l = cl.lower().lstrip("#*_ ")
        if cl.startswith(("#", "##", "_")):
            continue
        if any(cl_l.startswith(h) for h in prose_hints):
            continue
        verse_lines.append(cl)

    poetic_lines = verse_lines if verse_lines else all_poetic_lines

    # Basic stats (words from full cleaned text, line stats from verse)
    total_lines = len(poetic_lines)
    total_words = len(re.findall(r"[A-Za-z']+", cleaned))

    # Syllables & meter (only on verse)
    syl_counts = [line_syllables(l) for l in poetic_lines]
    avg_syl = sum(syl_counts) / len(syl_counts) if syl_counts else 0
    min_syl = min(syl_counts) if syl_counts else 0
    max_syl = max(syl_counts) if syl_counts else 0
    variation = max_syl - min_syl
    total_syllables = sum(syl_counts)

    # Rhyme scheme (only on verse)
    scheme_letters = []
    rhyme_map = {}
    letter = ord("A")
    for line in poetic_lines:
        lw = get_last_word(line)
        if not lw:
            scheme_letters.append(" ")
            continue
        key = get_rhyme_key(lw)
        assigned = None
        for ek, let in rhyme_map.items():
            if keys_are_similar(key, ek):
                assigned = let
                break
        if assigned is None:
            assigned = chr(letter)
            rhyme_map[key] = assigned
            letter += 1
            if letter > ord("Z"):
                letter = ord("A")
        scheme_letters.append(assigned)

    rhyme_scheme_str = "".join(scheme_letters)
    # Rough consistency: % of lines that belong to a rhyme sound used more than once.
    # This naturally gives higher scores to poems that actually repeat end-sounds.
    freq = defaultdict(int)
    for let in scheme_letters:
        if let.strip():
            freq[let] += 1
    repeated_lines = sum(v for v in freq.values() if v > 1)
    total_rhyme_lines = sum(freq.values())
    rhyme_consistency = round(repeated_lines / max(1, total_rhyme_lines), 2)

    # Sensory / imagery
    lower_text = cleaned.lower()
    sensory_hits = {}
    for sense, words in SENSORY.items():
        hits = [w for w in words if w in lower_text]
        sensory_hits[sense] = len(hits)

    sensory_score = sum(sensory_hits.values())
    dominant_sense = max(sensory_hits, key=sensory_hits.get) if sensory_hits else "none"

    # Cosmic + SpaceX + sass/joy vibe
    spacex_hits = sum(1 for kw in SPACEX_KEYWORDS if kw in lower_text)
    cosmic_hits = sum(1 for kw in COSMIC_KEYWORDS if kw in lower_text)
    joy_hits = sum(1 for kw in JOY_SPARK_WORDS if kw in lower_text)
    exclamation_count = original_text.count("!") + original_text.count("!!")

    vibe_score = (spacex_hits * 2) + cosmic_hits + (joy_hits * 0.7) + (exclamation_count * 0.5)
    vibe_score = min(10, max(0, int(vibe_score)))

    # Stanza detection (blank-line separated)
    stanzas = 0
    in_stanza = False
    for l in stripped_lines:
        if l:
            if not in_stanza:
                stanzas += 1
                in_stanza = True
        else:
            in_stanza = False

    # Title guess — prefer clean short human title, tolerate markdown headers
    title = "Untitled Launch"
    prose_hints = ("a poem", "inspired by", "join the cosmic", "for starship", "check out my")
    for l in all_poetic_lines[:8]:   # look in the unfiltered list too for nice headers
        cl = l.strip()
        if not cl or len(cl) > 70:
            continue
        cl_clean = cl.lstrip("#*_ ").strip().rstrip(".,;:!? ")
        cl_lower = cl_clean.lower()
        if any(cl_lower.startswith(h) for h in prose_hints):
            continue
        if 4 < len(cl_clean) < 55 and not cl_lower.startswith(("the haiku", "haiku series")):
            title = cl_clean
            break

    return {
        "title": title,
        "original_text": original_text,
        "cleaned_text": cleaned,
        "poetic_lines": poetic_lines,
        "total_lines": total_lines,
        "total_words": total_words,
        "total_syllables": total_syllables,
        "syl_counts": syl_counts,
        "avg_syllables_per_line": round(avg_syl, 1),
        "syllable_range": (min_syl, max_syl),
        "syllable_variation": variation,
        "stanzas": stanzas,
        "rhyme_scheme": rhyme_scheme_str,
        "rhyme_letters": scheme_letters,
        "rhyme_consistency": round(rhyme_consistency, 2),
        "sensory_hits": sensory_hits,
        "sensory_score": sensory_score,
        "dominant_sense": dominant_sense,
        "spacex_hits": spacex_hits,
        "cosmic_hits": cosmic_hits,
        "joy_hits": joy_hits,
        "vibe_score": vibe_score,
        "exclamation_count": exclamation_count,
    }


# =============================================================================
# SASSY FEEDBACK (the fun part)
# =============================================================================

def vibe_label(score: int) -> str:
    if score >= 9:
        return "Starship on final approach — pure controlled fire"
    if score >= 7:
        return "Falcon 9 level thrust — this thing has legs"
    if score >= 5:
        return "Solid suborbital vibes — we felt the rumble"
    if score >= 3:
        return "A little grid fin wobble, but the spark is there"
    return "Still on the pad, but the tanks are pressurized"


def meter_comment(avg: float, variation: int) -> str:
    if variation <= 2:
        return "Tight, almost metered. Feels deliberate and confident — like a well-timed boostback."
    if variation <= 4:
        return "Mostly steady with a few breathing lines. Human and lovely."
    return "Wild ride. Some lines are hauling serious payload. Great energy, but watch for whiplash."


def rhyme_comment(scheme: str, consistency: float) -> str:
    unique = len(set(c for c in scheme if c.strip()))
    if consistency > 0.72:
        return "Rhymes are locked in formation. Tower catch achieved."
    if consistency > 0.45:
        return "Good bones. A few end-sounds drifted, but the scheme still sings."
    if unique > len(scheme) * 0.7:
        return "Very free verse. Almost no repeated end-sounds. Bold choice — just make sure the sonic echoes you *do* have are intentional and delicious."
    return "The end-sounds are roaming free. Great if that's the point; if you were going for more music, reel two or three of them back in."


def generate_suggestions(a: dict) -> list[str]:
    """3-5 playful, encouraging, slightly savage suggestions in the Chief Poet voice."""
    suggestions = []
    lines = a["poetic_lines"]
    avg = a["avg_syllables_per_line"]
    var = a["syllable_variation"]
    consistency = a["rhyme_consistency"]
    sensory = a["sensory_score"]
    vibe = a["vibe_score"]
    scheme = a["rhyme_scheme"]

    # Meter / length issues
    if avg > 11 or var > 5:
        suggestions.append(
            "Honey, a couple of these lines are dragging a full Super Heavy stack uphill. "
            "Trim 2-4 syllables and the whole stanza will breathe like a clean stage sep."
        )
    elif avg < 5 and a["total_lines"] > 8:
        suggestions.append(
            "These lines are short and punchy — I love the snap. Just make sure the short ones "
            "aren't accidentally starving the reader of the image. Give us one more sensory detail on the thin ones."
        )

    # Rhyme (only nag if it looks like the writer was *trying* for rhyme)
    if consistency < 0.38 and len(scheme) > 8:
        suggestions.append(
            "A few of the end-sounds feel like they ghosted each other mid-stanza. Pick two or three "
            "and make them actually land together — your reader will feel the booster catch."
        )

    # Sensory hunger
    if sensory < 5:
        suggestions.append(
            "I want to taste the smoke and feel the rumble in my sternum. Right now it's all head. "
            "Add at least two more body-level details (the heat on your face, the way the ground grabs your shoes). "
            "Your audience is standing in a field at 3am — make them feel it."
        )
    elif sensory >= 8:
        suggestions.append(
            "The sensory layer is already giving launch-viewing-party goosebumps. "
            "Lean even harder into one sense (the tactile is criminally good in your work) and it will go orbital."
        )

    # Vibe / SpaceX flavor
    if vibe < 4:
        suggestions.append(
            "Where's the hardware? The specific machine love? Throw in one concrete SpaceX thing "
            "(grid fin, octaweb, the way the tower arms reach) and watch the nerds in the room start crying."
        )
    elif vibe >= 7:
        suggestions.append(
            "The cosmic/SpaceX flavor is already chef's-kiss. You're speaking fluent engine. "
            "Just don't let the tech crowd out the human heartbeat — we still need the hand squeezing yours."
        )

    # Joy / spark check
    if a["joy_hits"] < 2 and a["exclamation_count"] < 1:
        suggestions.append(
            "You're allowed to sound excited, babe. A well-placed '!' or a childlike 'my heart' "
            "won't make it less cool. It will make it land in people's chests."
        )

    # General polish / one always-positive
    if len(suggestions) < 3:
        suggestions.append(
            "One image is carrying the whole stanza on its back. Give the others a little thrust vector control "
            "so the reader isn't just staring at the prettiest line."
        )

    if len(suggestions) < 3:
        suggestions.append(
            "The ending is almost there. Make the last line do more work — either a quiet gut-punch "
            "or a tiny lift that makes us want to cheer like the high-fives are already happening."
        )

    # Always end on encouragement (we're a supportive poet friend)
    random.shuffle(suggestions)
    final = suggestions[:5]

    # Guarantee at least one warm one if we got too savage
    has_warm = any("love" in s.lower() or "already" in s.lower() or "chef" in s.lower() for s in final)
    if not has_warm:
        final.append(
            "Listen — the spark is real. You're not writing pretty words; you're writing ignition. "
            "A little more throttle on the weak spots and this thing will light the sky."
        )

    return final[:5]


def format_syllable_pattern(syl_counts: list[int]) -> str:
    return "  ".join(str(n) for n in syl_counts)


# =============================================================================
# TERMINAL OUTPUT (snarky but kind)
# =============================================================================

def print_analysis(a: dict):
    print("\n" + "=" * 60)
    print(f"  ANALYSIS: {a['title'].upper()}")
    print("=" * 60 + "\n")

    # Stats block
    print("STATS")
    print("-" * 20)
    print(f"Lines: {a['total_lines']}   |   Stanzas: {a['stanzas']}   |   Words: {a['total_words']}   |   Syllables: {a['total_syllables']}")
    print(f"Avg syllables/line: {a['avg_syllables_per_line']}   |   Range: {a['syllable_range'][0]}–{a['syllable_range'][1]}")
    print(f"Syllable pattern: {format_syllable_pattern(a['syl_counts'])}")
    print()

    # Meter
    print("METER / RHYTHM")
    print("-" * 20)
    print(meter_comment(a['avg_syllables_per_line'], a['syllable_variation']))
    print()

    # Rhyme
    print("RHYME SCHEME")
    print("-" * 20)
    print(f"Detected scheme: {a['rhyme_scheme']}")
    print(rhyme_comment(a['rhyme_scheme'], a['rhyme_consistency']))
    print()

    # Imagery
    print("IMAGERY & SENSORY")
    print("-" * 20)
    print(f"Dominant sense: {a['dominant_sense'].upper()}   |   Total sensory hits: {a['sensory_score']}")
    for sense, count in sorted(a['sensory_hits'].items(), key=lambda x: -x[1]):
        if count:
            print(f"  {sense:10} {count}")
    print()

    # Vibe
    print("COSMIC / SASSY / SPACEX VIBE")
    print("-" * 20)
    print(f"Vibe score: {a['vibe_score']}/10  —  {vibe_label(a['vibe_score'])}")
    print(f"SpaceX hardware nods: {a['spacex_hits']}   |   Pure cosmic language: {a['cosmic_hits']}   |   Joy/sparks: {a['joy_hits']}")
    print()

    # The good stuff
    print("THE SASS & POLISH (3–5 notes from your favorite tech-poetess)")
    print("-" * 20)
    suggestions = generate_suggestions(a)
    for i, s in enumerate(suggestions, 1):
        print(f"{i}. {s}")
    print()

    print("You're already lighting the fuse. These are just the grid-fin tweaks.")
    print("=" * 60 + "\n")


# =============================================================================
# MARKDOWN SAVER
# =============================================================================

def save_analysis_markdown(a: dict, source_path: Path | None) -> Path:
    """Write a nice .md report next to the original (or a good default location)."""
    timestamp = datetime.now().strftime("%Y-%m-%d")

    if source_path:
        out_path = source_path.parent / f"{source_path.stem}_analysis.md"
    else:
        # Pasted input — timestamped + short slug so you can run it many times
        safe_title = re.sub(r"[^a-z0-9]+", "-", a["title"].lower()).strip("-")[:30]
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        out_path = Path(f"poem_analysis_{stamp}.md")

    suggestions = generate_suggestions(a)
    sug_md = "\n".join(f"{i}. {s}" for i, s in enumerate(suggestions, 1))

    md = f"""# {a['title']} — Poem Analysis

*Generated by poem_analyzer.py on {timestamp}*  
*Voice: Chief Poet tech-poetess edition — snarky, loving, rocket-obsessed*

## Original Poem

```
{a['original_text'].rstrip()}
```

## Quick Stats

| Metric                  | Value                  |
|-------------------------|------------------------|
| Lines                   | {a['total_lines']}                    |
| Stanzas                 | {a['stanzas']}                    |
| Words                   | {a['total_words']}                    |
| Total syllables         | {a['total_syllables']}                    |
| Avg syllables per line  | {a['avg_syllables_per_line']}                    |
| Syllable range          | {a['syllable_range'][0]}–{a['syllable_range'][1]}                    |
| Syllable pattern        | {format_syllable_pattern(a['syl_counts'])}                    |

## Meter & Rhythm

{meter_comment(a['avg_syllables_per_line'], a['syllable_variation'])}

## Rhyme Scheme

**Detected:** `{a['rhyme_scheme']}` (consistency ~{a['rhyme_consistency']})

{rhyme_comment(a['rhyme_scheme'], a['rhyme_consistency'])}

## Imagery & Sensory Details

- **Dominant sense:** {a['dominant_sense']}
- **Total sensory hits:** {a['sensory_score']}

| Sense     | Hits |
|-----------|------|
"""
    for sense, count in sorted(a['sensory_hits'].items(), key=lambda x: -x[1]):
        md += f"| {sense.capitalize():9} | {count:4} |\n"

    md += f"""

## Cosmic / Sassy / SpaceX Vibe

**Vibe score: {a['vibe_score']}/10** — {vibe_label(a['vibe_score'])}

- SpaceX hardware nods: {a['spacex_hits']}
- Pure cosmic language: {a['cosmic_hits']}
- Joy / heart / spark moments: {a['joy_hits']}
- Exclamations: {a['exclamation_count']}

## The Sass & Polish — Improvement Suggestions

{sug_md}

---

*Remember: you're not polishing a trophy. You're tuning an engine for flight.*  
*Go make it roar.* 🚀

*— Your friendly neighborhood Chief Poet aspirant*
"""

    out_path.write_text(md, encoding="utf-8")
    return out_path


# =============================================================================
# INPUT HANDLING
# =============================================================================

def get_input_interactive():
    """Interactive prompt for paste or file. Supports voice-memo style pastes."""
    print(BANNER)
    print(INTRO)

    choice = input("[P]aste poem or voice-memo transcript   /   [F]ile path (.md/.txt)  ?  (p/f): ").strip().lower()

    source_path = None

    if choice.startswith("f"):
        raw = input("Path to file: ").strip().strip("\"'")
        p = Path(raw)
        if not p.exists():
            # Try relative to poems/ as a courtesy
            alt = Path("poems") / raw
            if alt.exists():
                p = alt
            else:
                print(f"Couldn't find {raw}. Trying as relative path anyway...")
        try:
            text = p.read_text(encoding="utf-8")
            source_path = p
            print(f"\nLoaded: {p}\n")
        except Exception as e:
            print(f"Failed to read file: {e}")
            sys.exit(1)
    else:
        print("\nPaste your poem (or raw voice-memo transcript).")
        print("Include internal blank lines for stanzas — they matter.")
        print("When you're finished, type END on its own line and hit return.\n")

        collected = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip().upper() == "END":
                break
            collected.append(line)
        text = "\n".join(collected).strip()

        if not text:
            print("No poem detected. Exiting with dignity.")
            sys.exit(0)

        # Gentle transcript hint
        if text.count("\n") < 3 and len(text) > 120:
            print("(Detected possible voice-memo blob — cleaned common fillers for analysis.)\n")

    return text, source_path


# =============================================================================
# MAIN
# =============================================================================

def main():
    text, source_path = get_input_interactive()

    analysis = analyze_poem(text)

    print_analysis(analysis)

    out_path = save_analysis_markdown(analysis, source_path)
    print(f"Saved full analysis → {out_path.resolve()}")
    print("Now go make it fly.\n")


if __name__ == "__main__":
    main()
