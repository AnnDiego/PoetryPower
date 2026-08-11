"""
Prompt building helpers — turn poem + style into ready-to-use Imagine prompts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .style_loader import Style
from .style_matcher import (
    analyze_mood,
    extract_key_visuals,
    infer_default_couple_instruction,
    summarize_poem,
)


# Motion / camera language tuned for short vertical clips (6–10s, 9:16)
_MOTION_BY_STYLE = {
    "charcoal_sketch": (
        "Slow gentle camera drift; subtle paper-grain shimmer; "
        "soft smudges that breathe as if a hand just lifted from the page; "
        "quiet, meditative pacing."
    ),
    "artistic_collage": (
        "Layers of paper and fabric fragments drift and settle into place; "
        "threads pull taut; words flutter like confetti then still; "
        "hopeful, assembling motion."
    ),
    "moody_comic": (
        "Cinematic push-in on the subject; dramatic light flicker; "
        "panel-like framing with a slow parallax on shadows; "
        "tense, noir pacing."
    ),
    "romantic_anime": (
        "Soft sakura petals drift across frame; warm light breathing; "
        "gentle character micro-expressions; slow intimate push-in; "
        "tender, unhurried motion."
    ),
    "anime_cyberpunk": (
        "Neon signs flicker and pulse; soft rain streaks; "
        "subtle handheld drift through urban night; "
        "reflections shimmer on wet pavement; charged, romantic energy."
    ),
}

_DEFAULT_MOTION = (
    "Slow cinematic camera move; atmospheric particles in air; "
    "subtle living detail; composed for a 6–10 second vertical clip."
)

# Mild anatomy lock for video only (image models usually need less of this)
_VIDEO_ANATOMY_LINE = (
    "Anatomically correct figures with exactly two arms and two legs. "
    "Clean anatomy, no extra limbs."
)


@dataclass
class BuiltPrompts:
    """Final prompts ready for Imagine (or manual copy-paste)."""

    poem_summary: str
    mood: str
    image_prompt: str
    video_prompt: str
    motion_notes: str
    style_name: str
    style_display_name: str
    special_direction: str = ""
    couple_instruction: str = ""


def motion_for_style(style: Style) -> str:
    """Return style-aware motion language for short vertical video."""
    return _MOTION_BY_STYLE.get(style.name, _DEFAULT_MOTION)


def key_visual_reinforcement(poem_text: str, *, max_items: int = 8) -> str:
    """
    Short hard constraint listing distinctive objects from the poem.

    Empty string if none found — keeps romantic/style language uncluttered.
    """
    keys: List[str] = extract_key_visuals(poem_text, max_items=max_items)
    if not keys:
        return ""
    listed = ", ".join(keys)
    return (
        f"\n\nImportant visual elements that must appear accurately: {listed}. "
        "Do not replace them with generic versions."
    )


def couple_reinforcement(
    poem_text: str,
    *,
    special_direction: str = "",
) -> str:
    """
    Gentle default couple line when the poem is two people with no gender cues.

    Empty when not applicable or when special_direction already steers figures.
    """
    line = infer_default_couple_instruction(
        poem_text, special_direction=special_direction
    )
    if not line:
        return ""
    return f"\n\n{line}"


def special_direction_block(special_direction: str) -> str:
    """
    Highest-priority free-text instruction from the poet (CLI).

    Empty string when the user pressed Enter / left it blank.
    """
    text = (special_direction or "").strip()
    if not text:
        return ""
    return (
        f"\n\nSpecial direction from the poet (highest priority — follow carefully): "
        f"{text}"
    )


def _append_shared_constraints(
    body: str,
    poem_text: str,
    *,
    special_direction: str = "",
) -> str:
    """
    Shared tail for image + video: objects, couple default, then special direction.

    Order matters: style/scene first, then hard object locks, then gentle couple
    default, then poet special direction last so it can override casting/props.
    """
    body += key_visual_reinforcement(poem_text)
    body += couple_reinforcement(poem_text, special_direction=special_direction)
    body += special_direction_block(special_direction)
    return body


def build_image_prompt(
    style: Style,
    poem_text: str,
    *,
    poem_summary: Optional[str] = None,
    mood: Optional[str] = None,
    special_direction: str = "",
) -> str:
    """
    Compose the final still-image prompt from the style base_prompt
    plus a poem-derived summary and mood.

    Appends:
      - key-object reinforcement (Cybertruck, martini glass, star chart, …)
      - default male/female couple line when appropriate
      - optional special direction from the CLI (highest priority)
    """
    summary = poem_summary if poem_summary is not None else summarize_poem(poem_text)
    mood_label = mood if mood is not None else analyze_mood(poem_text)

    body = style.format_base_prompt(poem_summary=summary, mood=mood_label)
    body = _append_shared_constraints(
        body, poem_text, special_direction=special_direction
    )

    # Reinforce vertical social framing without fighting the style text
    framing = (
        "\n\nComposition: vertical 9:16 portrait framing suitable for phone screens; "
        "strong focal subject; cohesive artistic rendering; no watermark, no text overlay."
    )
    return body + framing


def build_video_prompt(
    style: Style,
    poem_text: str,
    *,
    poem_summary: Optional[str] = None,
    mood: Optional[str] = None,
    special_direction: str = "",
    duration_hint: str = "8 seconds",
) -> str:
    """
    Compose a text-to-video prompt: same visual style + short motion description
    tuned for ~6–10s vertical (9:16) clips.

    Same object / couple / special-direction constraints as the image prompt,
    plus mild clean-anatomy language (video-only) to reduce extra-limb artifacts.
    """
    summary = poem_summary if poem_summary is not None else summarize_poem(poem_text)
    mood_label = mood if mood is not None else analyze_mood(poem_text)
    motion = motion_for_style(style)

    # Reuse style DNA, then shared constraints, then pivot into motion language
    visual_core = style.format_base_prompt(poem_summary=summary, mood=mood_label)
    visual_core = _append_shared_constraints(
        visual_core, poem_text, special_direction=special_direction
    )

    video_block = f"""
Animate this scene as a short {duration_hint} vertical video (aspect ratio 9:16).

Motion and camera:
{motion}

{_VIDEO_ANATOMY_LINE}

Keep the visual style consistent throughout. Adult characters if figures are present.
Smooth, high-quality motion; no jump cuts; no on-screen text or watermarks.
""".strip()

    return f"{visual_core}\n\n{video_block}"


def build_prompts(
    style: Style,
    poem_text: str,
    *,
    special_direction: str = "",
) -> BuiltPrompts:
    """One-shot builder: summary, mood, image + video prompts (+ optional direction)."""
    summary = summarize_poem(poem_text)
    mood = analyze_mood(poem_text)
    motion = motion_for_style(style)
    direction = (special_direction or "").strip()
    couple = infer_default_couple_instruction(
        poem_text, special_direction=direction
    )
    return BuiltPrompts(
        poem_summary=summary,
        mood=mood,
        image_prompt=build_image_prompt(
            style,
            poem_text,
            poem_summary=summary,
            mood=mood,
            special_direction=direction,
        ),
        video_prompt=build_video_prompt(
            style,
            poem_text,
            poem_summary=summary,
            mood=mood,
            special_direction=direction,
        ),
        motion_notes=motion,
        style_name=style.name,
        style_display_name=style.display_name,
        special_direction=direction,
        couple_instruction=couple,
    )


def render_prompts_markdown(
    *,
    title: str,
    poem_text: str,
    built: BuiltPrompts,
    image_url: Optional[str] = None,
    video_url: Optional[str] = None,
    api_notes: Optional[str] = None,
    generate_video: bool = True,
) -> str:
    """
    Serialize a full visualizer report as markdown.

    *generate_video* records whether a live video API call was requested
    (False = user skipped video to save credits; the video *prompt* is still
    included so it can be pasted into Imagine later).
    """
    from datetime import datetime

    video_status = (
        "attempted (API call)"
        if generate_video
        else "skipped (user chose not to generate video)"
    )

    lines = [
        f"# Poem Visualizer — {title}",
        "",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "## Style",
        "",
        f"- **Name:** `{built.style_name}`",
        f"- **Display:** {built.style_display_name}",
        f"- **Mood (detected):** {built.mood}",
        f"- **Video generation:** {video_status}",
        "",
    ]

    if built.special_direction:
        lines += [
            f"- **Special direction:** {built.special_direction}",
            "",
        ]
    if built.couple_instruction:
        lines += [
            f"- **Couple default:** {built.couple_instruction}",
            "",
        ]

    lines += [
        "## Poem summary (for prompts)",
        "",
        built.poem_summary,
        "",
        "## Image prompt",
        "",
        "```",
        built.image_prompt,
        "```",
        "",
        "## Video prompt",
        "",
        f"_Motion notes:_ {built.motion_notes}",
        "",
        "```",
        built.video_prompt,
        "```",
        "",
    ]

    if image_url or video_url or api_notes:
        lines += ["## Generation results", ""]
        if image_url:
            lines += [f"- **Image URL:** {image_url}"]
        if video_url:
            lines += [f"- **Video URL:** {video_url}"]
        if api_notes:
            lines += ["", api_notes, ""]
        lines.append("")

    lines += [
        "## Source poem",
        "",
        "```",
        poem_text.strip(),
        "```",
        "",
        "---",
        "",
        "_Phase 1 poem_visualizer — prompts ready for Grok Imagine._",
        "",
    ]
    return "\n".join(lines)
