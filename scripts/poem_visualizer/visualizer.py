#!/usr/bin/env python3
"""
visualizer.py — Poem → style match → Imagine prompts (Phase 1 MVP).

Run from repo root:
    python -m scripts.poem_visualizer.visualizer
    python scripts/poem_visualizer/visualizer.py

What it does:
- Accepts pasted poem OR path to a .md / .txt file
- Loads styles from the living styles/ catalog
- Suggests a best-fit style (keyword + vibe matching)
- Lets you accept, override, or list styles
- Builds strong image + video prompts
- Saves a markdown report next to the poem
- Optionally calls Grok Imagine if XAI_API_KEY is set
- After each version, offers another pass on the same poem (new style/direction)

Voice: tech-poetess with a grid fin and a soft spot for sakura.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

# Allow `python scripts/poem_visualizer/visualizer.py` without install
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    _repo = Path(__file__).resolve().parents[2]
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))
    __package__ = "scripts.poem_visualizer"

from .imagine_client import ImagineClient
from .prompts import build_prompts, render_prompts_markdown
from .style_loader import Style, format_style_list, get_style, load_all_styles
from .style_matcher import score_styles, suggest_style
from .utils import (
    default_output_path,
    find_repo_root,
    guess_title,
    read_poem_interactive,
)


# =============================================================================
# VOICE & BANNER
# =============================================================================

BANNER = r"""
   /\
  /  \     poem_visualizer  ·  Phase 1
 /____\    poetry → style → image + video prompts
 |    |    
 |~~~~|    "Paint the verse. Then make it move."
 |____|
  ||||
  ||||
"""

INTRO = (
    "Welcome back, Chief Poet. We'll match your lines to a visual style, "
    "spin up Imagine-ready prompts, and — if your XAI_API_KEY is glowing — "
    "try to generate the goods. No key? No problem. Prompts still ship.\n"
)


def _print_banner() -> None:
    print(BANNER)
    print(INTRO)


def _choose_style(
    poem_text: str,
    styles: Dict[str, Style],
) -> Style:
    """Interactive style selection with suggestion, override, and list."""
    ranked = score_styles(poem_text, styles)
    top = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None

    print("─" * 56)
    print("STYLE MATCH")
    print("─" * 56)
    print(f"  Suggested:  {top.style.display_name}  ({top.style.name})")
    print(f"  Score:      {top.score:.1f}")
    if top.hits:
        print(f"  Signals:    {', '.join(top.hits[:8])}")
    print()
    print(f"  Vibe: {top.style.vibe}")
    if top.style.notes:
        print(f"  Notes: {top.style.notes}")
    if runner_up and runner_up.score > 0.5:
        print(
            f"\n  (Runner-up: {runner_up.style.display_name} "
            f"@ {runner_up.score:.1f} — jealousy is a valid aesthetic.)"
        )
    print()
    print("Options:")
    print("  [a] Accept suggestion  (default)")
    print("  [l] List all styles")
    print("  [name] Type another style name to override")
    print()

    while True:
        raw = input("Your call [a]: ").strip()
        if not raw or raw.lower() in {"a", "accept", "y", "yes"}:
            print(f"\nLocked in: {top.style.display_name}. Excellent taste.\n")
            return top.style

        if raw.lower() in {"l", "list", "ls", "?"}:
            print("\nAvailable styles:\n")
            print(format_style_list(styles))
            print()
            continue

        chosen = get_style(styles, raw)
        if chosen:
            print(
                f"\nOverride accepted: {chosen.display_name}. "
                "The algorithm bows to the poet.\n"
            )
            return chosen

        # Fuzzy help: show close names
        print(
            f"Hmm, no style named '{raw}'. "
            "Try [l] to list, [a] to accept, or a real style name "
            f"(e.g. {', '.join(list(styles.keys())[:3])})."
        )


def _ask_special_direction() -> str:
    """
    Optional free-text steering for image/video prompts.

    Shown after style is locked. Empty string = use defaults (including the
    automatic male/female couple assumption when the poem is clearly dual).
    """
    print("─" * 56)
    print("SPECIAL DIRECTION  (optional)")
    print("─" * 56)
    print("Any special direction for the image/video? (optional)")
    print('Examples: "male/female couple", "two women", "include clear martini glasses",')
    print('          "Cybertruck must be accurate", "solo figure"')
    print("Press Enter to use defaults.")
    print()
    try:
        raw = input("Your direction: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n(Skipping special direction.)\n")
        return ""
    if raw:
        print(f"\nNoted: {raw}\n")
    else:
        print("\nDefaults it is — the verse leads.\n")
    return raw


def _ask_generate_video() -> bool:
    """
    Whether to spend credits on a live video call after the still image.

    Default yes — keeps historical behavior. Answer n during testing to
    save video credits (image generation still runs if a key is present).
    """
    print("─" * 56)
    print("VIDEO GENERATION")
    print("─" * 56)
    print("Generate video? (y/n) [y]")
    print("(Choose n to save credits during testing — image still generates.)")
    print()
    try:
        raw = input("Your call [y]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n(Defaulting to yes — video will be attempted.)\n")
        return True

    # Empty / y / yes → True; n / no → False; anything else → True with a nudge
    if not raw or raw in {"y", "yes"}:
        print("\nVideo on. Buckle up for the longer burn.\n")
        return True
    if raw in {"n", "no"}:
        print("\nVideo skipped — image only. Credits conserved.\n")
        return False

    print(f"\nUnrecognized '{raw}' — treating as yes (default).\n")
    return True


def _maybe_generate(
    image_prompt: str,
    video_prompt: str,
    *,
    generate_video: bool = True,
) -> tuple[Optional[str], Optional[str], str]:
    """
    Optional Imagine API path. Returns (image_url, video_url, notes_md).
    Never raises — failures become graceful notes.

    When *generate_video* is False, only the still image is requested (if a
    key is available). The video prompt is still built and saved elsewhere.
    """
    client = ImagineClient.from_env()
    if client is None:
        note = (
            "_No `XAI_API_KEY` in the environment (or `requests` missing). "
            "Prompts saved only — paste them into Grok Imagine whenever you're ready._"
        )
        if not generate_video:
            note += "\n\n_Video generation was not requested (user chose skip)._"
        print(
            "No XAI_API_KEY detected (or requests not installed). "
            "Skipping live generation — your prompts are still the star of the show.\n"
        )
        return None, None, note

    print("XAI_API_KEY found. Summoning Grok Imagine…\n")
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    notes: list[str] = []

    print("  → Generating image (9:16)…")
    img = client.generate_image(image_prompt, aspect_ratio="9:16")
    if img.ok and img.url:
        image_url = img.url
        print(f"     Image ready: {image_url}\n")
        notes.append("Image generation: **ok**")
    else:
        print(f"     Image skipped/failed: {img.error}\n")
        notes.append(f"Image generation: failed — {img.error}")

    if not generate_video:
        print("  → Video generation skipped (user chose n — credits conserved).\n")
        notes.append("Video generation: **skipped** (user chose not to generate video)")
        return image_url, None, "\n".join(f"- {n}" for n in notes)

    # Prefer image-to-video when we have a still; else text-to-video
    print("  → Generating video (9:16, ~8s) — this can take a few minutes…")
    vid = client.generate_video(
        video_prompt,
        duration=8,
        aspect_ratio="9:16",
        resolution="720p",
        image_url=image_url,
    )
    if vid.ok and vid.url:
        video_url = vid.url
        print(f"     Video ready: {video_url}\n")
        notes.append("Video generation: **ok**")
    else:
        print(f"     Video skipped/failed: {vid.error}\n")
        notes.append(f"Video generation: failed — {vid.error}")

    return image_url, video_url, "\n".join(f"- {n}" for n in notes)


def _print_prompts(image_prompt: str, video_prompt: str) -> None:
    print("─" * 56)
    print("IMAGE PROMPT  (copy into Grok Imagine)")
    print("─" * 56)
    print(image_prompt)
    print()
    print("─" * 56)
    print("VIDEO PROMPT  (6–10s · 9:16 vertical)")
    print("─" * 56)
    print(video_prompt)
    print()


def _ask_another_version() -> bool:
    """
    After a report is saved: offer another pass on the same poem.

    Default is no (Enter / n) so a single-run session still exits cleanly.
    Yes restarts at style selection with the poem already loaded.
    """
    print()
    print("─" * 56)
    print("ANOTHER VERSION?")
    print("─" * 56)
    print("Generate another version from this poem? (y/n) [n]")
    print("(Yes → restyle / re-prompt without re-pasting the poem.)")
    print()
    try:
        raw = input("Your call [n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        # Treat abort here as "we're done" — same as choosing no
        print()
        return False

    if raw in {"y", "yes"}:
        print("\nAnother orbit it is — same poem, fresh choices.\n")
        return True
    if not raw or raw in {"n", "no"}:
        return False

    print(f"\nUnrecognized '{raw}' — treating as no (done for now).\n")
    return False


def _run_one_version(
    *,
    poem_text: str,
    title: str,
    source_path: Optional[Path],
    styles: Dict[str, Style],
    repo_root: Path,
    version_num: int = 1,
) -> int:
    """
    One full pass: style → special direction → video flag → prompts → API → report.

    Returns 0 on success, non-zero on hard failure (e.g. cannot write report).
    KeyboardInterrupt / Ctrl+C still bubble up so the user can exit mid-prompt.
    """
    if version_num > 1:
        print("─" * 56)
        print(f"VERSION {version_num}  ·  same poem: {title}")
        print("─" * 56)
        print()

    # --- style choice ---
    style = _choose_style(poem_text, styles)

    # --- optional poet steering (genders, props, solo, brand accuracy, …) ---
    special_direction = _ask_special_direction()

    # --- video on/off (default yes; n saves credits during testing) ---
    generate_video = _ask_generate_video()

    # --- prompts ---
    built = build_prompts(
        style, poem_text, special_direction=special_direction
    )
    _print_prompts(built.image_prompt, built.video_prompt)

    # --- optional API (video call only if generate_video) ---
    image_url, video_url, api_notes = _maybe_generate(
        built.image_prompt,
        built.video_prompt,
        generate_video=generate_video,
    )

    # --- save markdown (timestamped path → unique file per version) ---
    out_path = default_output_path(source_path, title, repo_root=repo_root)
    report = render_prompts_markdown(
        title=title,
        poem_text=poem_text,
        built=built,
        image_url=image_url,
        video_url=video_url,
        api_notes=api_notes,
        generate_video=generate_video,
    )
    try:
        out_path.write_text(report, encoding="utf-8")
    except OSError as exc:
        print(f"Could not write report to {out_path}: {exc}")
        return 1

    print("─" * 56)
    print(f"Report saved → {out_path}")
    print("Prompts locked. Now go make the cosmos look good.")
    print("─" * 56)
    return 0


def run() -> int:
    _print_banner()
    repo_root = find_repo_root()

    # --- load catalog (once per session) ---
    try:
        styles = load_all_styles(repo_root=repo_root)
    except FileNotFoundError as exc:
        print(f"Style catalog trouble: {exc}")
        return 1

    print(f"Loaded {len(styles)} style(s) from {repo_root / 'styles'}\n")

    # --- poem input (once; kept for every version in the loop) ---
    try:
        poem_text, source_path = read_poem_interactive()
    except FileNotFoundError as exc:
        print(f"{exc}")
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nAborted mid-flight. The stars will wait.")
        return 130

    title = guess_title(poem_text)
    if source_path:
        # Prefer filename stem when title sniff is weak
        stem = source_path.stem.replace("_", " ").replace("-", " ").strip()
        if title == "Untitled Verse" and stem:
            title = stem

    print(f"Working title: {title}\n")

    # --- version loop: style → … → report, then optional another pass ---
    version_num = 1
    while True:
        try:
            rc = _run_one_version(
                poem_text=poem_text,
                title=title,
                source_path=source_path,
                styles=styles,
                repo_root=repo_root,
                version_num=version_num,
            )
        except (EOFError, KeyboardInterrupt):
            # Easy exit mid-style / special-direction / video prompt
            print("\nAborted mid-version. Earlier reports are still saved.")
            print("Until next launch, Chief Poet.")
            return 130

        if rc != 0:
            return rc

        if not _ask_another_version():
            print()
            print("All set. The verse has been painted — see you among the stars.")
            return 0

        version_num += 1


def main() -> None:
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        print("\nCaught abort. Grid fins deployed. See you next launch.")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
