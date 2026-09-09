#!/usr/bin/env python3
"""
Daily Haiku Toast runner.

Run from repo root:
    python -m scripts.haiku_toast
    python -m scripts.haiku_toast --dry-run
    python -m scripts.haiku_toast --style buttered
    python -m scripts.haiku_toast --style toaster_popup
    python -m scripts.haiku_toast --seed 17
    python -m scripts.haiku_toast.runner

Flow:
  San Diego date + thin weather seed
  → one English 5-7-5 (xAI chat, or dry sample if no key)
  → pick an enabled Imagine style (random, or --style / --seed)
  → optional Grok Imagine still (reuses poem_visualizer.ImagineClient)
  → save haiku.txt + report.md + image (when generated)

Site posting / daily X / Notion / physical toaster: not in v1.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

# Allow `python scripts/haiku_toast/runner.py` without install
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    _repo = Path(__file__).resolve().parents[2]
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))
    __package__ = "scripts.haiku_toast"

from .prompts import (
    FUTURE_STYLES_NOTE,
    IMAGINE_ASPECT_RATIO,
    KEEPER_SAMPLE_HAIKU,
    SAN_DIEGO_TZ,
    VOICE_BRIEF,
)
from .style_catalog import (
    ToastStyle,
    choose_style,
    enabled_names,
    fill_imagine_prompt,
)
from .syllables import counts_label, haiku_counts, parse_haiku
from .weather import WeatherSeed, fetch_san_diego_weather, weekday_vibe
from .writer import WriteResult, resolve_api_key, write_haiku


@dataclass
class RunArtifacts:
    out_dir: Path
    stamp: str
    haiku_path: Path
    report_path: Path
    image_path: Optional[Path] = None


@dataclass
class RunResult:
    date_line: str
    weekday: str
    weather: WeatherSeed
    haiku: str
    imagine_prompt: str
    dry: bool
    wrote_live: bool
    imagined: bool
    style: Optional[ToastStyle] = None
    style_selection: str = "random"
    style_seed: Optional[int] = None
    image_url: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    artifacts: Optional[RunArtifacts] = None
    write: Optional[WriteResult] = None


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Walk up until poems/ or styles/ appears (same cue as the visualizer)."""
    here = (start or Path(__file__)).resolve()
    if here.is_file():
        here = here.parent
    for candidate in [here, *here.parents]:
        if (candidate / "styles").is_dir() or (candidate / "poems").is_dir():
            return candidate
    return Path(__file__).resolve().parents[2]


def default_out_dir(repo_root: Optional[Path] = None) -> Path:
    return (repo_root or find_repo_root()) / "toasts"


def san_diego_now(when: Optional[datetime] = None) -> datetime:
    tz = ZoneInfo(SAN_DIEGO_TZ)
    if when is None:
        return datetime.now(tz)
    if when.tzinfo is None:
        return when.replace(tzinfo=tz)
    return when.astimezone(tz)


def format_date_line(when: datetime) -> str:
    # Wednesday, September 9, 2026  (day is unpadded)
    return f"{when.strftime('%A')}, {when.strftime('%B')} {when.day}, {when.year}"


def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m scripts.haiku_toast",
        description=(
            "Daily Haiku Toast: San Diego date + weather seed → 5-7-5 → "
            "Imagine still from the local toast style catalog."
        ),
    )
    p.add_argument(
        "--style",
        metavar="NAME",
        help=(
            "Force a catalog style (buttered, toaster_popup). "
            "Default: random among enabled styles."
        ),
    )
    p.add_argument(
        "--seed",
        type=int,
        help="RNG seed for the random style pick (ignored when --style is set).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Prompt-only: skip chat + Imagine even if XAI_API_KEY is set.",
    )
    p.add_argument(
        "--no-weather",
        action="store_true",
        help="Skip the Open-Meteo fetch (offline / tests).",
    )
    p.add_argument(
        "--no-imagine",
        action="store_true",
        help="Write the haiku but do not call Grok Imagine.",
    )
    p.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Override the San Diego calendar date (default: today, PT).",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        help="Artifact directory (default: <repo>/toasts).",
    )
    p.add_argument(
        "--haiku",
        help="Use this haiku (use \\n between lines) instead of calling the writer.",
    )
    return p.parse_args(argv)


def _resolve_when(date_str: Optional[str]) -> datetime:
    now = san_diego_now()
    if not date_str:
        return now
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"Bad --date {date_str!r}: expected YYYY-MM-DD ({exc})") from exc
    return d.replace(
        hour=now.hour,
        minute=now.minute,
        second=now.second,
        tzinfo=ZoneInfo(SAN_DIEGO_TZ),
    )


def _download_image(url: str, dest: Path) -> Optional[str]:
    try:
        import requests
    except ImportError:
        return "requests not installed; image URL saved in the report only."
    try:
        resp = requests.get(url, timeout=120)
    except Exception as exc:  # noqa: BLE001
        return f"image download failed: {exc}"
    if resp.status_code >= 400:
        return f"image download HTTP {resp.status_code}"
    dest.write_bytes(resp.content)
    return None


def render_report(result: RunResult) -> str:
    weather = result.weather
    write = result.write
    style = result.style
    style_name = style.name if style else "unknown"
    style_display = style.display_name if style else "unknown"
    counts = haiku_counts(result.haiku.splitlines()) if result.haiku else []
    pool = ", ".join(f"`{n}`" for n in enabled_names())
    if result.style_selection == "cli":
        pick_line = f"`--style {style_name}`"
    elif result.style_seed is not None:
        pick_line = f"random among enabled ({pool}), `--seed {result.style_seed}`"
    else:
        pick_line = f"random among enabled ({pool})"
    lines = [
        f"# Daily Haiku Toast — {result.date_line}",
        "",
        f"_San Diego · {result.weekday} · style `{style_name}`_",
        "",
        "## Style",
        "",
        f"- **Chosen:** `{style_name}` — {style_display}",
        f"- **Selection:** {pick_line}",
        "",
        "## Haiku",
        "",
        result.haiku or "_(no haiku this run)_",
        "",
        "## Date & weather seed",
        "",
        f"- **Date:** {result.date_line} (`{SAN_DIEGO_TZ}`)",
        f"- **Weekday vibe:** {weekday_vibe(result.weekday)}",
        f"- **Weather:** {weather.seed_line()}",
        f"- **Source:** {weather.source} ({weather.source_url}) — high/low °F + one condition word. Not a weather product.",
        "",
        "## Syllables (cheap heuristic)",
        "",
        f"- Count: `{counts_label(counts) or 'n/a'}`  (target 5-7-5)",
    ]
    if write is not None:
        if write.regenerated:
            lines.append("- Regenerated once after the first pass looked way off.")
        if write.way_off:
            lines.append("- Still way off after one retry — kept as-is (soft fail).")
        if write.model:
            lines.append(f"- Chat model: `{write.model}`")
        if write.error:
            lines.append(f"- Writer: {write.error}")
    if result.dry:
        lines.append("- Dry / no-key path: live writer was not called.")
    if result.imagined:
        imagine_status = "ok"
    elif result.dry:
        imagine_status = "skipped (dry / no key)"
    else:
        imagine_status = "skipped / failed"
    lines += [
        "",
        f"## Imagine prompt (`{style_name}` — catalog template, `{{HAIKU}}` only)",
        "",
        "```",
        result.imagine_prompt.rstrip(),
        "```",
        "",
        "## Generation",
        "",
        f"- Dry run: **{'yes' if result.dry else 'no'}**",
        f"- Live writer: **{'yes' if result.wrote_live else 'no'}**",
        f"- Imagine: **{imagine_status}**",
    ]
    if result.image_url:
        lines.append(f"- Image URL: {result.image_url}")
    if result.artifacts:
        art = result.artifacts
        lines += [
            "",
            "## Artifacts",
            "",
            f"- Haiku: `{art.haiku_path}`",
            f"- Report: `{art.report_path}`",
        ]
        if art.image_path:
            lines.append(f"- Image: `{art.image_path}`")
    if result.notes:
        lines += ["", "## Notes", ""]
        lines += [f"- {n}" for n in result.notes]
    lines += [
        "",
        "## Later (not v1)",
        "",
        "- Site / Notion post, daily auto-X, physical toaster, toast agent.",
        f"- {FUTURE_STYLES_NOTE}",
        "",
        "---",
        "",
        "_Daily Haiku Toast — local style catalog. Voice brief locked._",
        "",
    ]
    return "\n".join(lines)


def save_artifacts(
    result: RunResult,
    *,
    out_dir: Path,
    stamp: Optional[str] = None,
    image_path: Optional[Path] = None,
) -> RunArtifacts:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or san_diego_now().strftime("%Y%m%d-%H%M")
    haiku_path = out_dir / f"{stamp}_haiku.txt"
    report_path = out_dir / f"{stamp}_toast.md"
    haiku_path.write_text((result.haiku or "") + "\n", encoding="utf-8")
    artifacts = RunArtifacts(
        out_dir=out_dir,
        stamp=stamp,
        haiku_path=haiku_path,
        report_path=report_path,
        image_path=image_path,
    )
    result.artifacts = artifacts
    report_path.write_text(render_report(result), encoding="utf-8")
    return artifacts


def _maybe_imagine(imagine_prompt: str, dest: Path) -> tuple[Optional[str], Optional[Path], str]:
    """
    Optional Imagine path. Reuses scripts.poem_visualizer.imagine_client.

    Returns (url, saved_path, note).
    """
    from scripts.poem_visualizer.imagine_client import ImagineClient

    client = ImagineClient.from_env()
    if client is None:
        return (
            None,
            None,
            "No XAI_API_KEY (or requests missing) — Imagine skipped; prompt saved.",
        )

    img = client.generate_image(imagine_prompt, aspect_ratio=IMAGINE_ASPECT_RATIO)
    if not (img.ok and img.url):
        return None, None, f"Imagine failed: {img.error}"

    err = _download_image(img.url, dest)
    if err:
        return img.url, None, f"Imagine ok, {err}"
    return img.url, dest, "Imagine: ok"


def run(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    repo_root = find_repo_root()
    out_dir = Path(args.out_dir) if args.out_dir else default_out_dir(repo_root)
    if not out_dir.is_absolute():
        out_dir = (Path.cwd() / out_dir).resolve()

    when = _resolve_when(args.date)
    date_line = format_date_line(when)
    weekday = when.strftime("%A")

    try:
        style = choose_style(name=args.style, seed=args.seed)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    style_selection = "cli" if args.style else "random"

    print("Daily Haiku Toast  ·  San Diego morning scrap, burned into crust")
    print(f"  {date_line}  ({SAN_DIEGO_TZ})")
    if style_selection == "cli":
        print(f"  Style: {style.name}  (--style)")
    elif args.seed is not None:
        print(f"  Style: {style.name}  (random, seed={args.seed})")
    else:
        print(f"  Style: {style.name}  (random among {', '.join(enabled_names())})")
    print()

    if args.no_weather:
        weather = WeatherSeed(ok=False, error="--no-weather")
        print("Weather fetch skipped (--no-weather).")
    else:
        print("Fetching thin San Diego seed from Open-Meteo…")
        weather = fetch_san_diego_weather()
        print(f"  {weather.seed_line()}")
    print()

    key = resolve_api_key()
    dry = bool(args.dry_run or not key)
    notes: List[str] = []
    write: Optional[WriteResult] = None
    wrote_live = False

    if args.haiku:
        raw = args.haiku.replace("\\n", "\n")
        _lines, haiku = parse_haiku(raw)
        if not haiku:
            haiku = raw.strip()
        notes.append("Haiku supplied via --haiku (writer skipped).")
        print("Using --haiku (writer skipped).\n")
    elif dry:
        haiku = KEEPER_SAMPLE_HAIKU
        if args.dry_run:
            notes.append("Dry-run: sample keeper haiku, no chat call.")
            print("Dry-run. Using the keeper sample haiku (no chat call).\n")
        else:
            notes.append("No XAI_API_KEY — prompt-only. Sample keeper haiku filled in.")
            print(
                "No XAI_API_KEY. Prompt-only path. "
                "Filling the chosen style template with the keeper sample.\n"
            )
    else:
        print("XAI_API_KEY found. Asking the writer for this morning's scrap…")
        write = write_haiku(
            date_line=date_line,
            weekday_vibe=weekday_vibe(weekday),
            weather_seed=weather.seed_line(),
            api_key=key,
        )
        if not write.ok:
            print(f"  Writer failed: {write.error}")
            print("  Falling back to the keeper sample so Imagine can still run.\n")
            haiku = KEEPER_SAMPLE_HAIKU
            notes.append(f"Writer failed ({write.error}); used keeper sample.")
        else:
            haiku = write.haiku
            wrote_live = True
            print(f"  Syllables: {counts_label(write.counts)}  (target 5-7-5)")
            if write.regenerated:
                print("  Regenerated once (heuristic was way off).")
            if write.way_off:
                print("  Still way off after one retry — keeping it (soft fail).")
            print()

    print("─" * 56)
    print("HAIKU")
    print("─" * 56)
    print(haiku)
    print()

    imagine_prompt = fill_imagine_prompt(haiku, style)
    print("─" * 56)
    print(f"IMAGINE PROMPT  ({style.name} · catalog · {{HAIKU}} only)")
    print("─" * 56)
    print(imagine_prompt)
    print()

    # Writer prompt is useful on the dry path so Ann can see the seed.
    user_preview = None
    if dry and not args.haiku:
        from .prompts import writer_user_prompt

        user_preview = writer_user_prompt(
            date_line=date_line,
            weekday_vibe=weekday_vibe(weekday),
            weather_seed=weather.seed_line(),
        )
        notes.append("Writer system brief + user seed saved in this report's notes.")
        print("─" * 56)
        print("WRITER PROMPT  (would be sent if a key were set)")
        print("─" * 56)
        print("System:")
        print(VOICE_BRIEF.strip())
        print()
        print("User:")
        print(user_preview)
        print()

    skip_imagine = dry or args.no_imagine
    image_url: Optional[str] = None
    image_path: Optional[Path] = None
    imagined = False
    stamp = san_diego_now().strftime("%Y%m%d-%H%M")
    pending_image = out_dir / f"{stamp}_toast.jpg"

    if args.no_imagine:
        notes.append("Imagine skipped (--no-imagine).")
        print("Imagine skipped (--no-imagine).\n")
    elif dry:
        notes.append("Imagine skipped (dry / no key). Paste the prompt into Grok Imagine when ready.")
        print("Imagine skipped (dry / no key). Prompt is saved.\n")
    else:
        print(f"Summoning Grok Imagine ({IMAGINE_ASPECT_RATIO}) via poem_visualizer.ImagineClient…")
        out_dir.mkdir(parents=True, exist_ok=True)
        image_url, image_path, note = _maybe_imagine(imagine_prompt, pending_image)
        notes.append(note)
        imagined = image_url is not None
        if image_path:
            print(f"  Image saved → {image_path}\n")
        else:
            print(f"  {note}\n")

    result = RunResult(
        date_line=date_line,
        weekday=weekday,
        weather=weather,
        haiku=haiku,
        imagine_prompt=imagine_prompt,
        dry=dry,
        wrote_live=wrote_live,
        imagined=imagined,
        style=style,
        style_selection=style_selection,
        style_seed=None if args.style else args.seed,
        image_url=image_url,
        notes=notes,
        write=write,
    )
    if user_preview:
        result.notes.append("Voice brief (system):\n\n" + VOICE_BRIEF.strip())
        result.notes.append("Writer user seed:\n\n" + user_preview)

    artifacts = save_artifacts(
        result, out_dir=out_dir, stamp=stamp, image_path=image_path
    )

    print("─" * 56)
    print(f"Haiku  → {artifacts.haiku_path}")
    print(f"Report → {artifacts.report_path}")
    if artifacts.image_path:
        print(f"Image  → {artifacts.image_path}")
    print(f"Style `{style.name}` from the local toast catalog.")
    print("─" * 56)
    return 0


def main() -> None:
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        print("\nAborted. The toast can wait.")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
