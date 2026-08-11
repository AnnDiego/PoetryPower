#!/usr/bin/env python3
"""
poem_madlib.py — Turn your cosmic verses into a launchpad of blanks and giggles.

Run:
    python scripts/poem_madlib.py

What it does:
- Accepts the exact same input as poem_analyzer (paste or .md/.txt path, voice-memo friendly)
- Intelligently blanks nouns, verbs, adjectives, adverbs + any word dripping with
  cosmic or SpaceX flavor
- Keeps every line break, stanza, and most punctuation so the rhythm stays visible
- Gives each blank a silly, sassy, or rocket-nerd prompt ("a tower-catching noun",
  "a verb that sounds like it just hot-fired")
- Prints the playable template + one gloriously unhinged filled-in example
- Saves both as *_madlib_template.md and *_madlib_example.md next to the original

Pure stdlib. Maximum chaos. Zero gatekeeping. In the Chief Poet tech-poetess voice.
"""

import re
import sys
import random
from pathlib import Path
from datetime import datetime


# =============================================================================
# VOICE & BANNER (same family as poem_analyzer, same soul)
# =============================================================================

BANNER = r"""
   /\
  /  \
 /____\   poem_madlib.py
 |    |   (snarky poet friend + madlib mode: ARMED)
 |    |
 |____|
  ||||
  ||||   "Fill the blanks. Ignite the giggles. Tower catch optional."
"""

INTRO = (
    "Alright, word-weaver. Hand over the poem. We’re about to turn it into a "
    "glorious, slightly unhinged game of launch-day Mad Libs.\n"
)

# =============================================================================
# REUSABLE INPUT + CLEANING (kept in sync with poem_analyzer on purpose)
# =============================================================================

FILLER_WORDS = {
    "um", "uh", "er", "ah", "like", "you know", "so", "basically",
    "kinda", "sort of", "i mean", "well", "just", "really", "very"
}


def clean_transcript(text: str) -> str:
    """Same gentle voice-memo scrubber as the analyzer."""
    t = text.lower()
    for filler in sorted(FILLER_WORDS, key=len, reverse=True):
        t = re.sub(rf"\b{re.escape(filler)}\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r" +", " ", t).strip()
    return t


def get_input_interactive():
    """Interactive prompt. Paste or file. Identical UX contract as poem_analyzer."""
    print(BANNER)
    print(INTRO)

    choice = input("[P]aste poem or voice-memo transcript   /   [F]ile path (.md/.txt)  ?  (p/f): ").strip().lower()

    source_path = None

    if choice.startswith("f"):
        raw = input("Path to file: ").strip().strip("\"'")
        p = Path(raw)
        if not p.exists():
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
            print("No poem detected. Exiting with dignity (and a grid fin tucked under one arm).")
            sys.exit(0)

        if text.count("\n") < 3 and len(text) > 120:
            print("(Detected possible voice-memo blob — cleaned the ums for you, babe.)\n")

    return text, source_path


def guess_title(lines):
    """Same tolerant title sniffer the analyzer uses."""
    prose_hints = ("a poem", "inspired by", "join the cosmic", "for starship", "check out my")
    for l in lines[:8]:
        cl = l.strip()
        if not cl or len(cl) > 70:
            continue
        cl_clean = cl.lstrip("#*_ ").strip().rstrip(".,;:!? ")
        cl_lower = cl_clean.lower()
        if any(cl_lower.startswith(h) for h in prose_hints):
            continue
        if 4 < len(cl_clean) < 55 and not cl_lower.startswith(("the haiku", "haiku series")):
            return cl_clean
    return "Untitled Launch"


# =============================================================================
# THE MADNESS ENGINE — pure stdlib, lovingly over-engineered for vibes
# =============================================================================

# --- Word lists & cosmic flavor (curated, not exhaustive, very on-brand) ---

SPACEX_KEYWORDS = {
    "falcon", "falcon9", "starship", "superheavy", "booster", "boosters",
    "countdown", "maxq", "liftoff", "lift-off", "stage", "fairing", "fairings",
    "reentry", "re-entry", "tiles", "tower", "catch", "gridfin", "grid-fins",
    "thrust", "orbit", "mars", "launch", "rocket", "rockets", "engine", "engines",
    "ignition", "hotfire", "hot-fire", "sep", "separation", "dragon", "crew",
    "landing", "landed", "octaweb", "telemetry", "staticfire", "grid", "fins",
}

COSMIC_KEYWORDS = {
    "cosmic", "cosmos", "universe", "galaxy", "star", "stars", "moon", "sun",
    "planet", "mars", "sky", "night", "constellation", "nebula", "void",
    "infinite", "eternal", "ignite", "blaze", "soar", "arc", "flame", "fire",
    "spark", "dream", "dare", "heavens", "celestial", "velvet", "plume",
    "roar", "pulse", "crater", "glow", "dark", "bright", "shadow",
}

# Things we almost never blank (glue words + a few sentiment carriers we want to keep)
SKIP_WORDS = {
    "the", "a", "an", "to", "of", "in", "on", "at", "by", "for", "with", "and",
    "or", "but", "if", "as", "into", "about", "from", "up", "down", "over", "under",
    "is", "are", "was", "were", "be", "been", "being", "it", "this", "that",
    "these", "those", "i", "you", "we", "they", "he", "she", "my", "your", "our",
    "his", "her", "their", "its", "me", "us", "them", "am", "do", "does", "did",
    "will", "would", "could", "should", "can", "may", "might", "must", "shall",
    "no", "not", "nor", "yet", "so", "than", "too", "very", "just", "now", "then",
    "here", "there", "where", "when", "why", "how", "all", "any", "some", "each",
    "few", "more", "most", "other", "such", "only", "own", "same", "so", "than",
}

# Strong content-word seeds (we lean on these + rules + the cosmic lists above)
NOUN_SEEDS = {
    "heart", "night", "sky", "stars", "moon", "sun", "earth", "world", "hand",
    "hands", "eyes", "face", "arms", "ground", "dream", "dreams", "flame", "flames",
    "fire", "smoke", "plume", "arc", "trail", "booster", "rocket", "engine",
    "engines", "tower", "countdown", "pulse", "beat", "roar", "cheer", "cheers",
    "neighbor", "neighbors", "stranger", "strangers", "friend", "friends",
    "crater", "craters", "footprint", "footprints", "flag", "relic", "relics",
    "shadow", "glow", "kiss", "love", "wonder", "awe", "joy", "spark", "sparks",
    "child", "children", "song", "sound", "silence", "static", "air", "wind",
    "heat", "cold", "dust", "dirt", "clay", "surface", "horizon", "heavens",
    "constellation", "nebula", "galaxy", "void", "planet", "mars", "falcon",
    "starship", "dragon", "crew", "grid", "fin", "fins", "tile", "tiles",
    "launchpad", "launch", "liftoff", "stage", "fairing", "fairings", "orbit",
    "reentry", "landing", "highfive", "highfives", "party", "field", "crowd",
}

VERB_SEEDS = {
    "pierce", "pierces", "blaze", "blazes", "gallop", "gallops", "crane", "cranes",
    "race", "races", "pulse", "pulses", "split", "shed", "sheds", "hang", "hangs",
    "reflect", "reflects", "drift", "drifts", "bind", "binds", "weave", "weaves",
    "yearn", "yearns", "erupt", "erupts", "billow", "billows", "soar", "soars",
    "dare", "dares", "kiss", "kisses", "gaze", "gazes", "lift", "lifts", "spread",
    "spreads", "bow", "bows", "peek", "peeks", "miss", "misses", "question",
    "questions", "long", "longs", "visit", "visits", "stand", "stands", "linger",
    "lingers", "catch", "catches", "land", "lands", "launch", "launches", "ignite",
    "ignites", "thrust", "thrusts", "orbit", "orbits", "reenter", "reenters",
    "burn", "burns", "shake", "shakes", "tremble", "trembles", "squeeze", "squeezes",
    "wrap", "wraps", "chase", "chases", "jostle", "jostles", "erupt", "erupts",
    "glide", "glides", "hover", "hovers", "plummet", "plummets", "cleave", "cleaves",
    "point", "points", "release", "releases", "guard", "guards", "cast", "casts",
    "reach", "reaches", "write", "writes", "dream", "dreams", "feel", "feels",
    "hear", "hears", "see", "sees", "touch", "touches", "taste", "tastes",
}

ADJ_SEEDS = {
    "velvet", "clear", "white", "black", "red", "crimson", "blue", "orange",
    "silver", "bronze", "full", "sweet", "raw", "trembling", "steady", "static",
    "technical", "true", "cosmic", "celestial", "infinite", "eternal", "wild",
    "childlike", "enchanted", "soft", "rare", "electric", "warm", "cold", "acrid",
    "fiery", "bright", "dark", "inky", "curved", "curly", "lone", "lonely",
    "distant", "sterile", "harsh", "rugged", "cold", "fine", "stark", "patient",
    "unforgiving", "stoic", "ardent", "sleek", "bold", "unyielding", "precise",
    "fierce", "familiar", "fragile", "free", "alive", "giddy", "thrilling",
    "questionable", "glorious", "unhinged", "sassy", "thicc", "zero-g",
}

ADV_SEEDS = {
    "wildly", "gently", "slowly", "quickly", "softly", "loudly", "quietly",
    "steadily", "freely", "barely", "hardly", "nearly", "really", "truly",
    "deeply", "brightly", "darkly", "sweetly", "rawly", "fiercely", "boldly",
    "patiently", "precisely", "exactly", "finally", "endlessly", "eternally",
    "sassy", "sassily", "gloriously", "unhinged", "recklessly", "carefully",
    "deliberately", "childishly", "wonderfully", "awfully", "terribly",
}


def _normalize(w: str) -> str:
    return re.sub(r"[^a-z']", "", w.lower())


def get_word_category(word: str) -> str | None:
    """
    Returns one of: 'noun', 'verb', 'adj', 'adv', 'cosmic_noun', 'cosmic_verb',
    'cosmic_adj', 'cosmic_adv'  — or None if we shouldn't blank it.
    Pure heuristic + lists. No NLTK, no tears.
    """
    w = _normalize(word)
    if not w or len(w) < 2:
        return None
    if w in SKIP_WORDS:
        return None

    # Cosmic / SpaceX priority — these get the fun prompts even if the POS is fuzzy
    is_cosmic = w in COSMIC_KEYWORDS or w in SPACEX_KEYWORDS or any(k in w for k in ("star", "moon", "mars", "cosmo", "orbit", "thrust", "roar"))
    is_spacex = w in SPACEX_KEYWORDS or any(k in w for k in ("falcon", "starship", "booster", "grid", "tower", "launch", "countdown", "fairing", "tile"))

    # Rough POS via seeds + cheap rules
    if w in ADV_SEEDS or (w.endswith("ly") and len(w) > 4 and w not in {"only", "really"}):
        pos = "adv"
    elif w in VERB_SEEDS or w.endswith(("ing", "ed")) or w.endswith("s") and w[:-1] in VERB_SEEDS:
        pos = "verb"
    elif w in NOUN_SEEDS or w.endswith(("s", "es")) and w[:-1] in NOUN_SEEDS or w.endswith(("s", "es")) and w[:-2] in NOUN_SEEDS:
        pos = "noun"
    elif w in ADJ_SEEDS or w.endswith(("ous", "ful", "less", "ive", "al", "ic", "ish", "ed")):
        pos = "adj"
    else:
        # fallback heuristics for poetry
        if w.endswith("ly"):
            pos = "adv"
        elif w.endswith(("ing", "ed")):
            pos = "verb"
        elif w.endswith("s") and len(w) > 3:
            pos = "noun"
        else:
            pos = None

    if not pos:
        # last-ditch: if it's a strong cosmic word we still want to blank it
        if is_cosmic or is_spacex:
            pos = "noun"
        else:
            return None

    if is_spacex or is_cosmic:
        return f"cosmic_{pos}"
    return pos


# Prompt flavors — sassy, cosmic, tech-poetess approved
PROMPT_BANK = {
    "noun": [
        "a fiery celestial noun",
        "a sassy rocket noun",
        "your favorite cosmic noun",
        "a launch-day noun (the kind that makes strangers high-five)",
        "a plume-shaped noun",
    ],
    "verb": [
        "a sassy verb (past tense preferred)",
        "an action that feels like ignition",
        "a verb that belongs in a launch commentary",
        "a verb so spicy it needs a grid fin",
        "a verb that ends in thrust",
    ],
    "adj": [
        "a velvet cosmic adjective",
        "an adjective that smells like smoke and wonder",
        "a slightly illegal adjective",
        "a color that only exists at 3 a.m. during a launch",
        "an adjective that would make a booster blush",
    ],
    "adv": [
        "an adverb that sounds like it just hot-fired",
        "a launchpad adverb",
        "an adverb with too much thrust",
        "an adverb that belongs in a love letter to a rocket",
        "a sassy adverb (the kind you yell during Max Q)",
    ],
    "cosmic_noun": [
        "a tower-catching noun",
        "a Mars-bound noun with trust issues",
        "Elon’s favorite noun (don’t tell the others)",
        "a celestial noun that kissed the void",
        "a noun that just did a boostback burn",
    ],
    "cosmic_verb": [
        "a verb that just performed a tower catch",
        "a verb that sounds like a RUD but in a sexy way",
        "an orbital verb",
        "a verb that makes the whole crowd gasp",
        "a verb you would only say at 3 a.m. while the sky is on fire",
    ],
    "cosmic_adj": [
        "a starship-certified adjective",
        "an adjective that survived reentry",
        "a zero-g adjective with a drinking problem",
        "a velvet adjective that has seen things",
        "an adjective currently on fire (in a good way)",
    ],
    "cosmic_adv": [
        "an adverb that just cleared the tower",
        "a boostback adverb",
        "an adverb that lands like a kiss",
        "a suspiciously orbital adverb",
        "an adverb that makes the engineers cheer",
    ],
}


def choose_prompt(word: str, category: str) -> str:
    """Pick a flavorful prompt. Slight determinism per word so the same poem feels coherent."""
    bank = PROMPT_BANK.get(category, PROMPT_BANK["noun"])
    # stable-but-fun choice
    idx = hash(word + category) % len(bank)
    return bank[idx]


# The unhinged funny replacement lists (tech-poetess chaos edition)
FUNNY_NOUNS = [
    "booster", "grid fin", "plasma taco", "sassy raccoon", "launch tower",
    "Elon’s left eyebrow", "cosmic donut", "falcon plume", "Mars dirt",
    "velvet void", "starlink raccoon", "hot-fire kiss", "tower arm",
    "octaweb of feelings", "reentry tile", "countdown clock", "Max Q moment",
    "boostback burn", "drone ship", "orbital hug", "celestial high-five",
    "glittery crater", "plasma donut", "RUD of the heart", "Starship butt",
]

FUNNY_VERBS = [
    "yeeted", "thrust-vectored", "RUDed", "hot-fired", "kissed with fire",
    "catapulted", "orbited sassily", "landed with a wink", "boostbacked",
    "grid-finned", "tower-caught", "stage-separated", "fairing-shed",
    "reentered dramatically", "plumed majestically", "cratered cutely",
    "gazed longingly", "squeezed like a launch button", "erupted in glitter",
    "whispered 'Max Q'", "high-fived the sky",
]

FUNNY_ADJS = [
    "thicc", "extra-spicy", "zero-g", "questionably legal", "starship-certified",
    "velvet", "smoky", "slightly on fire", "tower-caught", "boostback",
    "grid-fin adjacent", "Max-Q emotional", "reentry-scorched", "orbital",
    "suspiciously cosmic", "childlike but make it rocket", "glitter-drunk",
    "dangerously romantic", "one (1) whole vibe",
]

FUNNY_ADVS = [
    "thrustily", "sassily", "orbitally", "grid-finnedly", "with too much plume",
    "like a booster that just got complimented", "zero-g style", "during Max Q",
    "while the tower was watching", "in a way that made the engineers cry",
    "like it had something to prove to Mars", "with main character reentry energy",
    "as if the void was flirting back", "recklessly but in a cute way",
]


def choose_funny_replacement(category: str, original_word: str) -> str:
    """Return a silly, on-brand replacement. Keeps length vibe-ish for rhythm."""
    if "noun" in category:
        pool = FUNNY_NOUNS
    elif "verb" in category:
        pool = FUNNY_VERBS
    elif "adj" in category:
        pool = FUNNY_ADJS
    elif "adv" in category:
        pool = FUNNY_ADVS
    else:
        pool = FUNNY_NOUNS

    choice = random.choice(pool)
    # occasionally make it a tiny phrase for extra chaos
    if random.random() < 0.12 and " " not in choice:
        extras = [" of doom", " with feelings", " (certified)", " at 3am", " in lipstick"]
        choice += random.choice(extras)
    return choice


def process_poem(text: str, mode: str = "template") -> str:
    """
    Core engine. mode="template" → [prompt] blanks
               mode="example"  → gloriously silly filled version
    Preserves line breaks, stanzas, and most attached punctuation.
    For the template we are slightly nicer to pure header/title lines.
    """
    lines = text.splitlines(keepends=True)
    out_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Be a little gentle on the very first 1-2 obvious header lines in template mode
        is_headerish = (i < 3 and (stripped.startswith(("#", "##", "_", "*"))
                                   or (len(stripped) < 28 and stripped)))
        if mode == "template" and is_headerish:
            out_lines.append(line)
            continue

        def replacer(match):
            word = match.group(1)
            trailing = match.group(2) or ""
            cat = get_word_category(word)
            if not cat:
                return match.group(0)

            if mode == "template":
                prompt = choose_prompt(word, cat)
                return f"[{prompt}]{trailing}"
            else:
                repl = choose_funny_replacement(cat, word)
                if word and word[0].isupper() and repl:
                    repl = repl[0].upper() + repl[1:]
                return repl + trailing

        new_line = re.sub(r"([A-Za-z']+)([^A-Za-z'\s]*)", replacer, line)
        out_lines.append(new_line)
    return "".join(out_lines)


def make_madlib_template(text: str) -> str:
    return process_poem(text, "template")


def make_filled_example(text: str) -> str:
    # fresh chaos every time
    random.seed()  # explicit, in case someone set one earlier
    return process_poem(text, "example")


# =============================================================================
# TERMINAL THEATER (snarky but encouraging)
# =============================================================================

def print_madlib_output(original_text: str, template: str, example: str, title: str):
    print("\n" + "=" * 64)
    print(f"  MAD LIBS: {title.upper()}")
    print("=" * 64 + "\n")

    print("THE TEMPLATE (print this, grab your crew, go feral)")
    print("-" * 64)
    print(template)
    print()

    print("ONE UNHINGED EXAMPLE THE COSMOS WROTE AT 3 A.M.")
    print("(run the script again for a completely different fever dream)")
    print("-" * 64)
    print(example)
    print()

    print("You’re already lighting the fuse. These are just the giggles.")
    print("=" * 64 + "\n")


# =============================================================================
# SAVING — two files, same directory contract as the analyzer
# =============================================================================

def save_madlib_files(original_text: str, template: str, example: str,
                      source_path: Path | None, title: str) -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y-%m-%d")

    if source_path:
        stem = source_path.stem
        template_path = source_path.parent / f"{stem}_madlib_template.md"
        example_path = source_path.parent / f"{stem}_madlib_example.md"
    else:
        safe = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:30]
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        template_path = Path(f"poem_madlib_template_{ts}.md")
        example_path = Path(f"poem_madlib_example_{ts}.md")

    header = f"""# {title} — Mad Libs Edition

*Generated by poem_madlib.py on {stamp}*  
*Voice: Chief Poet tech-poetess edition — snarky, loving, rocket-obsessed, slightly unhinged*

> Fill the blanks with your launch crew (or let the machine do it and laugh until you snort).

## Original Poem (for reference)

```
{original_text.rstrip()}
```

## The Mad Libs Template
*Print this. Play it loud. High-fives mandatory.*

```
{template}
```

## One Gloriously Unhinged Filled-In Example
*(the cosmos was feeling spicy)*

```
{example}
```

---

*Remember: you’re not just filling blanks. You’re building a new launch manifest of pure chaos.*  
*Go make it roar.* 🚀

*— Your friendly neighborhood Chief Poet aspirant (currently covered in glitter and pride)*
"""

    template_md = header
    template_path.write_text(template_md, encoding="utf-8")

    # Also write a tiny standalone example file that’s just the fun version + context
    example_md = f"""# {title} — Mad Libs Example (the spicy one)

*Generated alongside the template on {stamp}*

This is one random filled-in version. Run the script again for a different disaster.

## The Poem, Now With Feelings

```
{example}
```

*If this one made you cackle, the template is in the sibling file. Go play it with humans.*  
🚀😉
"""
    example_path.write_text(example_md, encoding="utf-8")

    return template_path, example_path


# =============================================================================
# MAIN
# =============================================================================

def main():
    text, source_path = get_input_interactive()

    cleaned = clean_transcript(text)
    raw_lines, _ = [], []  # we only need for title
    # quick title from original (before too much cleaning)
    title = guess_title(text.splitlines())

    template = make_madlib_template(text)
    example = make_filled_example(text)

    print_madlib_output(text, template, example, title)

    t_path, e_path = save_madlib_files(text, template, example, source_path, title)
    print(f"Saved:")
    print(f"  Template → {t_path.resolve()}")
    print(f"  Example  → {e_path.resolve()}")
    print("Now go fill it with your favorite chaos gremlins.\n")


if __name__ == "__main__":
    main()
