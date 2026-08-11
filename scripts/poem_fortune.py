#!/usr/bin/env python3
"""
poem_fortune.py — Crack open your poem. Get a Cosmic Poem Fortune Cookie.

Run:
    python scripts/poem_fortune.py

What it does:
- Accepts the same input as poem_analyzer / poem_madlib (paste or .md/.txt path)
- Reads the poem’s vibe and imagery and serves a short, sassy cosmic fortune
- Assigns a ridiculous SpaceX-style mission code name
- Adds a tiny mission-status prediction (playful, encouraging, a little snarky)
- Frames the whole reading in cute ASCII rocket / starry art
- Saves the full fortune as *_fortune.md next to the original poem

Pure stdlib. Maximum starlight. Voice: slightly unhinged tech-poetess who lives
for launches and poetry (and loves you enough to tease you about both).
"""

from __future__ import annotations

import hashlib
import random
import re
import sys
from datetime import datetime
from pathlib import Path


# =============================================================================
# VOICE & BANNER
# =============================================================================

BANNER = r"""
   /\
  /  \
 /____\   poem_fortune.py
 |    |   (cosmic fortune cookie mode: CRACKED OPEN)
 |    |
 |____|
  ||||
  ||||   "Your verses just got a mission code. Don't waste it."
"""

INTRO = (
    "Alright, word-weaver. Hand over the poem. We're cracking it like a fortune "
    "cookie written by a launch-obsessed poetess at T-minus giggles.\n"
)

FILLER_WORDS = {
    "um", "uh", "er", "ah", "like", "you know", "so", "basically",
    "kinda", "sort of", "i mean", "well", "just", "really", "very",
}


# =============================================================================
# REUSABLE INPUT + CLEANING (same UX contract as poem_analyzer / poem_madlib)
# =============================================================================

def clean_transcript(text: str) -> str:
    """Light voice-memo scrubber — keep line breaks, ditch the ums."""
    t = text
    for filler in sorted(FILLER_WORDS, key=len, reverse=True):
        t = re.sub(rf"\b{re.escape(filler)}\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r" +", " ", t).strip()
    return t


def get_input_interactive():
    """Interactive prompt. Paste or file. Identical UX contract as the other tools."""
    print(BANNER)
    print(INTRO)

    choice = input(
        "[P]aste poem or voice-memo transcript   /   [F]ile path (.md/.txt)  ?  (p/f): "
    ).strip().lower()

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
            print(
                "No poem detected. Exiting with dignity "
                "(and a grid fin tucked under one arm)."
            )
            sys.exit(0)

        if text.count("\n") < 3 and len(text) > 120:
            print("(Detected possible voice-memo blob — cleaned the ums for you, babe.)\n")

    return text, source_path


def guess_title(lines) -> str:
    """Tolerant title sniffer — same soul as the other tools."""
    prose_hints = (
        "a poem", "inspired by", "join the cosmic", "for starship", "check out my",
    )
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
# VIBE SNIFFER — light, fun, no gatekeeping
# =============================================================================

SPACEX_KEYWORDS = {
    "falcon", "starship", "super heavy", "booster", "boosters", "countdown",
    "max q", "liftoff", "lift-off", "stage", "fairing", "fairings", "reentry",
    "re-entry", "tiles", "tower", "catch", "grid fin", "grid fins", "thrust",
    "orbit", "mars", "launch", "rocket", "rockets", "engine", "engines",
    "ignition", "hotfire", "hot fire", "separation", "dragon", "crew",
    "landing", "landed", "telemetry", "static fire", "raptor", "plume",
}

COSMIC_KEYWORDS = {
    "cosmic", "cosmos", "universe", "galaxy", "star", "stars", "moon", "sun",
    "planet", "sky", "night", "constellation", "nebula", "void", "infinite",
    "eternal", "ignite", "blaze", "soar", "arc", "flame", "fire", "spark",
    "dream", "dare", "celestial", "heavens", "orbit", "velvet", "ember",
    "embers", "ash", "shadow", "light", "glow", "gleam",
}

HEART_KEYWORDS = {
    "heart", "love", "kiss", "hand", "hands", "squeeze", "cheek", "eyes",
    "joy", "wonder", "awe", "dream", "dreams", "dare", "hope", "alive",
    "spark", "giddy", "thrill", "embrace", "touch", "soft", "tender",
}

FIRE_KEYWORDS = {
    "fire", "flame", "flames", "blaze", "burn", "ignite", "ignition", "roar",
    "thrust", "plume", "smoke", "heat", "ember", "embers", "ash", "spark",
    "explode", "boom", "hot", "acrid",
}

# Imagery words we may pull into the fortune for personalization
IMAGE_WORDS = (
    SPACEX_KEYWORDS | COSMIC_KEYWORDS | HEART_KEYWORDS | FIRE_KEYWORDS
    | {
        "velvet", "steel", "steel frame", "wings", "fins", "tower", "booster",
        "countdown", "stars", "night", "sky", "arc", "trail", "plume",
        "ground", "quake", "vibration", "cheers", "high-five", "high fives",
        "marble", "shadow", "glow", "gleam", "shimmer", "catch", "landing",
        "orbit", "mars", "fairing", "raptor", "engine", "engines",
    }
)


def _count_hits(text_lower: str, keywords: set) -> int:
    hits = 0
    for kw in keywords:
        if " " in kw:
            hits += text_lower.count(kw)
        else:
            hits += len(re.findall(rf"\b{re.escape(kw)}\b", text_lower))
    return hits


def extract_image_words(text: str, limit: int = 8) -> list[str]:
    """Pull vivid tokens from the poem (preserve first-seen order)."""
    lower = text.lower()
    found = []
    seen = set()
    # Multi-word first so "grid fin" beats "grid"
    multi = sorted((k for k in IMAGE_WORDS if " " in k), key=len, reverse=True)
    singles = sorted((k for k in IMAGE_WORDS if " " not in k), key=len, reverse=True)

    for kw in multi + singles:
        if kw in seen:
            continue
        if " " in kw:
            if kw in lower:
                found.append(kw)
                seen.add(kw)
        else:
            if re.search(rf"\b{re.escape(kw)}\b", lower):
                found.append(kw)
                seen.add(kw)
        if len(found) >= limit:
            break
    return found


def sniff_vibe(text: str) -> dict:
    """Score the poem’s flavors so the fortune can lean into them."""
    lower = text.lower()
    spacex = _count_hits(lower, SPACEX_KEYWORDS)
    cosmic = _count_hits(lower, COSMIC_KEYWORDS)
    heart = _count_hits(lower, HEART_KEYWORDS)
    fire = _count_hits(lower, FIRE_KEYWORDS)
    images = extract_image_words(text)

    scores = {
        "spacex": spacex,
        "cosmic": cosmic,
        "heart": heart,
        "fire": fire,
    }
    dominant = max(scores, key=scores.get)
    if scores[dominant] == 0:
        dominant = "cosmic"  # default: everything is cosmic if you squint

    return {
        "scores": scores,
        "dominant": dominant,
        "images": images,
        "exclamations": text.count("!"),
        "word_count": len(re.findall(r"[A-Za-z']+", text)),
    }


# =============================================================================
# MISSION CODE NAMES — ridiculous, SpaceX-flavored, delightful
# =============================================================================

MISSION_PREFIXES = [
    "FALCON", "STARSHIP", "RAPTOR", "DRAGON", "BOOSTER", "GRIDFIN",
    "TOWER", "OCTAWEB", "SUPERHEAVY", "CREW", "NOMAD", "ORBIT",
    "IGNITION", "TELEMETRY", "FAIRING", "MAXQ", "MARSBOUND",
]

MISSION_MIDDLES = [
    "EMBERS", "SASSY", "VELVET", "SPARK", "GIGGLE", "ROAR", "PLUME",
    "WHISPER", "BLAZE", "GLITTER", "CHAOS", "DARING", "TENDER", "WILD",
    "HEARTBEAT", "STARLIGHT", "SNARK", "MIRTH", "THRUST", "ECHO",
    "ASH", "AWE", "FIZZ", "COSMIC", "RECKLESS", "GLOW", "KISS",
    "THUNDER", "DARE", "SONNET", "ORBIT", "STATIC", "PRIDE",
]


def mission_code_name(seed: str, vibe: dict) -> str:
    """Build e.g. FALCON-EMBERS-7 or STARSHIP-SASSY-42. Deterministic per poem+salt."""
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    n = int(h[:8], 16)

    # Bias prefix by dominant vibe a little
    prefixes = list(MISSION_PREFIXES)
    if vibe["dominant"] == "spacex":
        prefixes = ["FALCON", "STARSHIP", "RAPTOR", "BOOSTER", "TOWER"] + prefixes
    elif vibe["dominant"] == "heart":
        prefixes = ["DRAGON", "CREW", "NOMAD", "ORBIT"] + prefixes
    elif vibe["dominant"] == "fire":
        prefixes = ["IGNITION", "RAPTOR", "MAXQ", "SUPERHEAVY"] + prefixes

    middles = list(MISSION_MIDDLES)
    # Fold poem imagery into the middle word if we can
    for img in vibe.get("images", []):
        token = re.sub(r"[^a-z]", "", img.lower())
        if len(token) >= 3:
            middles.insert(0, token.upper())

    prefix = prefixes[n % len(prefixes)]
    middle = middles[(n // 7) % len(middles)]
    if middle == prefix:
        middle = middles[(n // 11 + 3) % len(middles)]
    number = (n % 90) + 1  # 1–90, fortune-cookie cute
    return f"{prefix}-{middle}-{number}"


# =============================================================================
# FORTUNE + MISSION STATUS TEMPLATES
# =============================================================================

# {img} = a vivid word from the poem (or a fallback)
# {title} = poem title
# Tone: sassy, loving, cosmic, launch-brained

FORTUNE_TEMPLATES = {
    "spacex": [
        "Your {img} energy is already on the pad. Stop polishing the fairings and light the damn fuse — the tower is waiting with open arms.",
        "This poem has booster-catch swagger. Whatever you're stalling on? Stage separation was three lines ago. Go do the bold thing.",
        "Telemetry says: confidence rising, doubt in free-fall. Trust the {img}. Trust the burn. Trust yourself more than the countdown clock.",
        "You're not 'almost ready.' You're max-q ready. Ride the pressure; the fairings always find their way home.",
        "Hardware is beautiful, but this reading is about soft guts in a steel age. Your next move wants {img} — and you already know which one.",
    ],
    "cosmic": [
        "The cosmos read your {img} and winked. You're allowed to want the sky and still keep one hand on the ground. Both are holy.",
        "Stars don't apologize for burning. Neither should you. Let this poem's {img} be permission to take up more night.",
        "Something quiet in you is already in orbit. Stop treating it like a draft. Publish the feeling. Launch the soft truth.",
        "You wrote {img} into the dark and the dark wrote back: keep going. Wonder is not a luxury item — it's your thruster package.",
        "This verse is a constellation with your name on it. Trace it. Follow it. Ignore anyone who calls wonder 'extra.'",
    ],
    "heart": [
        "Your {img} is doing more heavy lifting than you admit. Soft is not the opposite of strong — soft is what survives reentry.",
        "Someone (maybe you) needs the tenderness in this poem more than the clever line. Lead with the squeeze. Land the feeling.",
        "Love, in any form, is a tower catch: rare, technical, and worth the whole mission. Don't downplay your {img}.",
        "This poem has hand-holding energy at T-0. Whatever heart-thing you're circling — stop orbiting. Dock.",
        "Your capacity for awe is not cringe. It's the whole payload. Protect the {img}. Share it with people who clap for landings.",
    ],
    "fire": [
        "That {img} isn't a mood — it's a propulsion system. Point it at something that deserves the heat.",
        "You're mid-burn and still second-guessing. Cute. Incorrect. Let the roar finish its sentence.",
        "Ash means you already survived the fire once. Use the {img}. Write hotter. Live louder. Soften only on purpose.",
        "This poem smells like pad-side ozone and good decisions. Your next risk wants less permission and more ignition.",
        "Flames don't ask if they're 'too much.' Neither should your art. Fan the {img}. The night can take it.",
    ],
}

# Playful mission status lines
STATUS_TEMPLATES = [
    "MISSION STATUS: GO for wonder. Hold only for snacks and better lighting.",
    "MISSION STATUS: Nominal sass. Payload integrity: shamelessly high.",
    "MISSION STATUS: All green. Emotional grid fins deployed. Landing expected to be cute.",
    "MISSION STATUS: Slightly unhinged, fully fueled. Abort only if joy leaves the vehicle.",
    "MISSION STATUS: Tower has a lock on your softest truth. Catch attempt: inevitable.",
    "MISSION STATUS: Max Q of self-doubt: cleared. Resume full-throttle dreaming.",
    "MISSION STATUS: Telemetry nominal. Heart rate elevated for the right reasons.",
    "MISSION STATUS: Stage sep complete. You are now the upper stage. Act like it.",
    "MISSION STATUS: Weather is 90% vibes, 10% chaos. Still a launch window.",
    "MISSION STATUS: No RUD detected in your spirit. Proceed to next beautiful risk.",
    "MISSION STATUS: Crew is you, coffee, and the night sky. Manifest: locked.",
    "MISSION STATUS: Fairings jettisoned. The real poem is the one you live next.",
]

PREDICTION_TEMPLATES = [
    "COSMIC PREDICTION: In the next few days, a small bold choice will feel like liftoff. Take it before the window closes.",
    "COSMIC PREDICTION: Someone will notice the fire in your work before you do. Accept the compliment without dimming.",
    "COSMIC PREDICTION: A 'random' conversation will hand you a missing line — or a missing courage. Keep your ears open.",
    "COSMIC PREDICTION: The thing you're overthinking already wants to land. Stop thrashing the controls.",
    "COSMIC PREDICTION: Joy will show up disguised as a technical detail. High-five it anyway.",
    "COSMIC PREDICTION: You'll want to rewrite the ending. Maybe don't. Sometimes the soft landing is the point.",
    "COSMIC PREDICTION: A night sky (literal or metaphorical) is about to answer a question you asked three poems ago.",
    "COSMIC PREDICTION: Your next draft — or next dare — needs less polish and more pulse. Give it both if you must, but pulse first.",
    "COSMIC PREDICTION: Expect unexpected applause. Practice receiving it without shrinking.",
    "COSMIC PREDICTION: The universe is not testing you; it's teasing you. Flirt back.",
]

FALLBACK_IMAGES = [
    "starlight", "ember", "plume", "orbit", "spark", "roar", "velvet night",
    "countdown", "tower catch", "heart",
]


# =============================================================================
# ASCII FRAMES — cute rocket / starry art
# =============================================================================

FRAMES = [
    # Classic mini rocket
    r"""
          *
     /\      .
    /  \   *
   /____\
   |    |     .
   |    |
   |____|  *
    ||||
    ||||     .
   /_||_\
""",
    # Star field cookie
    r"""
    .  *    .   *  .   *
  *    .  ☆      .   *
    .    *    .  *   .
  *   .    ✦     .  *
    .  *   .   *   .
""",
    # Sideways sass rocket
    r"""
         *
    .   /|\   .
       /_|_\
       | o |   *
    .  |___| .
       /|||\
      * |||  .
""",
    # Orbit rings
    r"""
       *   .   *
    .    (   )    .
   *   .  \ /  .   *
         =o=      .
    *   /   \   *
      .   *   .
""",
]


def pick_frame(seed: str) -> str:
    h = int(hashlib.sha256(seed.encode()).hexdigest()[8:16], 16)
    return FRAMES[h % len(FRAMES)].strip("\n")


# =============================================================================
# FORTUNE ASSEMBLY
# =============================================================================

def _pick_image(vibe: dict, rng: random.Random) -> str:
    imgs = vibe.get("images") or []
    if imgs:
        return rng.choice(imgs)
    return rng.choice(FALLBACK_IMAGES)


def craft_fortune(text: str, title: str, vibe: dict, salt: str = "") -> dict:
    """Generate mission name, fortune, status, prediction, frame."""
    seed = f"{title}\n{text}\n{salt}"
    # Stable-ish per poem so re-runs feel related, but allow mild variation via salt
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))

    dominant = vibe["dominant"]
    templates = FORTUNE_TEMPLATES.get(dominant, FORTUNE_TEMPLATES["cosmic"])
    # If vibe is mixed, occasionally borrow from another bucket
    if vibe["scores"].get("spacex", 0) >= 2 and dominant != "spacex" and rng.random() < 0.35:
        templates = templates + FORTUNE_TEMPLATES["spacex"]

    img = _pick_image(vibe, rng)
    fortune = rng.choice(templates).format(img=img, title=title)
    status = rng.choice(STATUS_TEMPLATES)
    prediction = rng.choice(PREDICTION_TEMPLATES)
    code = mission_code_name(seed, vibe)
    frame = pick_frame(seed)

    tagline = rng.choice([
        "Crack carefully. Contents may include courage.",
        "Not responsible for sudden urge to rewrite, relaunch, or high-five a stranger.",
        "Best served with night sky, strong coffee, and zero apologies.",
        "If this fortune feels too accurate, that's the cosmos flirting. Wave back.",
        "Store in a cool, dry place next to your favorite unfinished stanza.",
    ])

    return {
        "title": title,
        "mission_code": code,
        "fortune": fortune,
        "status": status,
        "prediction": prediction,
        "frame": frame,
        "tagline": tagline,
        "dominant": dominant,
        "images": vibe.get("images") or [],
        "img_used": img,
    }


def format_reading(reading: dict, for_terminal: bool = True) -> str:
    """Pretty terminal / markdown body for the fortune cookie reading."""
    frame = reading["frame"]
    lines = [
        frame,
        "",
        f"  ✦ COSMIC POEM FORTUNE COOKIE ✦",
        f"  Mission: {reading['mission_code']}",
        f"  Poem:    {reading['title']}",
        "",
        "  " + "─" * 40,
        "",
        "  YOUR FORTUNE",
        f"  {reading['fortune']}",
        "",
        f"  {reading['status']}",
        "",
        f"  {reading['prediction']}",
        "",
        "  " + "─" * 40,
        f"  {reading['tagline']}",
        "",
        frame,
    ]
    body = "\n".join(lines)
    if for_terminal:
        return body
    return body


# =============================================================================
# SAVE + PRINT
# =============================================================================

def print_reading(reading: dict) -> None:
    print("\n" + "=" * 64)
    print("  CRACK — the cookie opens. Starlight spills out.")
    print("=" * 64)
    print(format_reading(reading, for_terminal=True))
    print("=" * 64)
    print("  You're already the launch. This was just the paper slip.")
    print("=" * 64 + "\n")


def save_fortune_markdown(
    original_text: str,
    reading: dict,
    source_path: Path | None,
) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d")
    title = reading["title"]

    if source_path:
        out_path = source_path.parent / f"{source_path.stem}_fortune.md"
    else:
        safe = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:30] or "poem"
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        out_path = Path(f"{safe}_fortune_{ts}.md")

    images = ", ".join(reading["images"][:6]) if reading["images"] else "(pure vibes — no labeled hardware required)"
    frame_block = reading["frame"]

    md = f"""# {title} — Cosmic Poem Fortune Cookie

*Generated by poem_fortune.py on {stamp}*  
*Voice: Chief Poet tech-poetess edition — snarky, loving, rocket-obsessed, slightly unhinged*

**Mission code:** `{reading['mission_code']}`  
**Dominant vibe sniffed:** `{reading['dominant']}`  
**Imagery in the mix:** {images}

---

```
{frame_block}

  ✦ COSMIC POEM FORTUNE COOKIE ✦
  Mission: {reading['mission_code']}
  Poem:    {title}

  YOUR FORTUNE
  {reading['fortune']}

  {reading['status']}

  {reading['prediction']}

  {reading['tagline']}

{frame_block}
```

---

## Original Poem (for the archive)

```
{original_text.rstrip()}
```

---

*Remember: fortunes don't replace courage — they just high-five it on the way to the pad.*  
*Go make it roar.* 🚀

*— Your friendly neighborhood Chief Poet aspirant (currently covered in cookie crumbs and pride)*
"""

    out_path.write_text(md, encoding="utf-8")
    return out_path


# =============================================================================
# MAIN
# =============================================================================

def main():
    text, source_path = get_input_interactive()
    # Light clean for vibe sniff only; we keep original for display/save
    cleaned = clean_transcript(text)
    title = guess_title(text.splitlines())
    vibe = sniff_vibe(cleaned if cleaned else text)
    reading = craft_fortune(text, title, vibe)

    print_reading(reading)

    out_path = save_fortune_markdown(text, reading, source_path)
    print(f"Saved full fortune → {out_path.resolve()}")
    print("Crack another poem whenever the night needs a mission code.\n")


if __name__ == "__main__":
    main()
