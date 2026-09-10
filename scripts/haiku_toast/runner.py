#!/usr/bin/env python3
"""
Daily Haiku Toast runner.

Run from repo root:
    python -m scripts.haiku_toast
    python -m scripts.haiku_toast --dry-run
    python -m scripts.haiku_toast --style buttered
    python -m scripts.haiku_toast --style toaster_popup
    python -m scripts.haiku_toast --seed 17
    python -m scripts.haiku_toast --mode verdant
    python -m scripts.haiku_toast --imagine-n 4
    python -m scripts.haiku_toast.runner

Flow:
  San Diego date + morning hourly Open-Meteo
  → Ann weather drawer (or --mode)
  → one short three-line haiku (xAI chat, or dry sample if no key)
  → pick an enabled Imagine style (random, or --style / --seed)
  → optional Grok Imagine stills (reuses poem_visualizer.ImagineClient;
    several candidates, keep the most legible burn-in)
  → save haiku.txt + report.md + image (when a still passes)

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

from .legibility import (
    PickResult,
    StillCandidate,
    make_extract_fn,
    pick_legible_still,
)
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
from .drawers import (
    DRAWERS,
    load_last_drawer,
    save_last_drawer,
    yesterday_note,
)
from .voice_modes import MODE_NAMES, ModePick, choose_mode
from .weather import WeatherSeed, fetch_san_diego_weather, weekday_vibe
from .writer import WriteResult, resolve_api_key, write_haiku
from scripts.poem_visualizer.imagine_client import MAX_IMAGE_N

# Morning default: a small gallery, not a single unlucky draw.
DEFAULT_IMAGINE_N = 4
MAX_IMAGINE_N = MAX_IMAGE_N


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
    voice: Optional[ModePick] = None
    image_url: Optional[str] = None
    imagine_n: int = 4
    imagine_tried: int = 0
    imagine_kept: Optional[int] = None
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
            "Daily Haiku Toast: San Diego date + morning hourly weather "
            "drawer → short three-line haiku → Imagine still from the "
            "local catalog."
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
        help=(
            "RNG seed for random style pick and drawer-tell pick "
            "(ignored for a pick that has an explicit --style / --mode)."
        ),
    )
    p.add_argument(
        "--mode",
        metavar="NAME",
        help=(
            "Force a voice mode ("
            + ", ".join(MODE_NAMES)
            + "). Default: Ann's weather → drawer tree (first match wins)."
        ),
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
    p.add_argument(
        "--imagine-n",
        type=int,
        default=DEFAULT_IMAGINE_N,
        metavar="N",
        help=(
            "How many Imagine stills to request and score for the same "
            f"prompt (default {DEFAULT_IMAGINE_N}, max {MAX_IMAGINE_N}). "
            "Keeps the most legible burn-in; ships nothing if all fail."
        ),
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
    voice = result.voice
    if voice is not None:
        mode_name = voice.mode.name
        mode_display = voice.mode.display_name
        mode_heat = voice.mode.heat
        mode_reason = voice.reason
        drawer_name = voice.drawer_display or voice.drawer or "n/a"
        tell = voice.tell or "n/a"
        if voice.selection == "cli":
            mode_pick_line = f"`--mode {mode_name}`"
        elif voice.selection == "fallback":
            mode_pick_line = "CLEAR MILD fallback (weather unavailable)"
        else:
            mode_pick_line = "weather drawer (Imagine style is separate)"
    else:
        mode_name = "unknown"
        mode_display = "unknown"
        mode_heat = "?"
        mode_reason = "mode was not chosen this run"
        mode_pick_line = "n/a"
        drawer_name = "n/a"
        tell = "n/a"
    lines = [
        f"# Daily Haiku Toast — {result.date_line}",
        "",
        f"_San Diego · {result.weekday} · style `{style_name}` · mode `{mode_name}` · drawer `{drawer_name}`_",
        "",
        "## Style",
        "",
        f"- **Chosen:** `{style_name}` — {style_display}",
        f"- **Selection:** {pick_line}",
        "",
        "## Voice mode",
        "",
        f"- **Chosen:** `{mode_name}` — {mode_display} (heat {mode_heat})",
        f"- **Selection:** {mode_pick_line}",
        f"- **Reason:** {mode_reason}",
        "",
        "## Weather drawer",
        "",
        f"- **Drawer:** {drawer_name}",
        f"- **Reason:** {mode_reason}",
        f"- **Tell:** {tell}",
        "",
        "## Haiku",
        "",
        result.haiku or "_(no haiku this run)_",
        "",
        "## Date & weather",
        "",
        f"- **Date:** {result.date_line} (`{SAN_DIEGO_TZ}`)",
        f"- **Weekday vibe:** {weekday_vibe(result.weekday)}",
        f"- **Hourly:** {weather.hourly_report_line()}",
        f"- **Daily:** {weather.daily_context_line()}",
        f"- **Source:** {weather.source} ({weather.source_url}) — hourly at pull hour + daily sunrise. Not a weather product.",
        "",
        "## Syllables (optional heuristic)",
        "",
        f"- Count: `{counts_label(counts) or 'n/a'}` — report-only, not a gate.",
    ]
    if write is not None:
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
    elif result.imagine_tried and not result.imagine_kept:
        imagine_status = "failed (no legible burn-in)"
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
    if result.dry:
        lines.append(
            f"- Imagine candidates: {result.imagine_n} would be requested "
            f"(`--imagine-n`; live runs score burn-in and keep one or fail)"
        )
    elif result.imagine_tried:
        if result.imagine_kept:
            lines.append(
                f"- Imagine candidates: {result.imagine_tried} scored, "
                f"kept #{result.imagine_kept} of {result.imagine_n} requested"
            )
        else:
            lines.append(
                f"- Imagine candidates: {result.imagine_tried} scored, "
                f"none passed (requested {result.imagine_n}) — still not shipped"
            )
    else:
        lines.append(
            f"- Imagine candidates: {result.imagine_n} configured (`--imagine-n`)"
        )
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
        "_Daily Haiku Toast — local style catalog + Poetess Ann voice seed. Heat 0–2._",
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


def _maybe_imagine(
    imagine_prompt: str,
    dest: Path,
    *,
    haiku: str,
    n: int = DEFAULT_IMAGINE_N,
    extract_fn=None,
) -> tuple[Optional[str], Optional[Path], str, PickResult]:
    """
    Optional Imagine path. Reuses scripts.poem_visualizer.imagine_client.

    Requests up to ``n`` stills for the same prompt, scores burned text
    against ``haiku``, and keeps one passer. If every candidate fails,
    no official toast image is written.

    Returns (url, saved_path, note, pick).
    """
    from scripts.poem_visualizer.imagine_client import ImagineClient

    empty = PickResult(ok=False, tried=0, note="")
    client = ImagineClient.from_env()
    if client is None:
        return (
            None,
            None,
            "No XAI_API_KEY (or requests missing) — Imagine skipped; prompt saved.",
            empty,
        )

    img = client.collect_image_urls(
        imagine_prompt, aspect_ratio=IMAGINE_ASPECT_RATIO, n=n
    )
    if not (img.ok and img.urls):
        return None, None, f"Imagine failed: {img.error}", empty

    dest.parent.mkdir(parents=True, exist_ok=True)
    candidates: List[StillCandidate] = []
    for i, url in enumerate(img.urls, start=1):
        cand_path = dest.with_name(f"{dest.stem}_cand{i}{dest.suffix}")
        err = _download_image(url, cand_path)
        if err:
            candidates.append(StillCandidate(index=i, url=url, path=None))
        else:
            candidates.append(StillCandidate(index=i, url=url, path=cand_path))

    key = resolve_api_key()
    picker = extract_fn or make_extract_fn(api_key=key)
    pick = pick_legible_still(haiku, candidates, extract_fn=picker)

    if pick.ok and pick.kept and pick.kept.candidate.path:
        winner = pick.kept.candidate.path
        dest.write_bytes(winner.read_bytes())
        _cleanup_candidates(candidates, keep=dest)
        return pick.kept.candidate.url, dest, pick.note, pick

    # All failed (or winner had no local file): persist rejects, no official jpg.
    _rename_rejects(candidates)
    return None, None, pick.note, pick


def _cleanup_candidates(candidates: List[StillCandidate], *, keep: Path) -> None:
    keep_resolved = keep.resolve()
    for cand in candidates:
        if cand.path is None:
            continue
        try:
            if cand.path.resolve() != keep_resolved:
                cand.path.unlink(missing_ok=True)
        except OSError:
            pass


def _rename_rejects(candidates: List[StillCandidate]) -> None:
    for cand in candidates:
        if cand.path is None or not cand.path.is_file():
            continue
        rejected = cand.path.with_name(
            cand.path.name.replace("_cand", "_rejected_", 1)
        )
        # _toast_cand1.jpg → _toast_rejected_1.jpg
        try:
            cand.path.replace(rejected)
        except OSError:
            pass


def run(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    if args.imagine_n < 1 or args.imagine_n > MAX_IMAGINE_N:
        raise SystemExit(
            f"--imagine-n must be between 1 and {MAX_IMAGINE_N} "
            f"(got {args.imagine_n})"
        )
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

    if args.no_weather:
        weather = WeatherSeed(ok=False, error="--no-weather")
        print("Weather fetch skipped (--no-weather).")
    else:
        print("Fetching San Diego morning hourly from Open-Meteo…")
        weather = fetch_san_diego_weather(when=when)
        print(f"  {weather.seed_line()}")

    today = when.date().isoformat()
    y_drawer, y_tell = yesterday_note(load_last_drawer(out_dir), today)
    try:
        voice = choose_mode(
            weather,
            name=args.mode,
            hour=when.hour,
            seed=None if args.mode else args.seed,
            yesterday_drawer=y_drawer,
            yesterday_tell=y_tell,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    drawer_label = voice.drawer_display or voice.drawer or "n/a"
    print(f"  Drawer: {drawer_label}")
    print(f"  Mode: {voice.mode.name}  ({voice.reason})")
    if voice.tell:
        print(f"  Tell: {voice.tell}")
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
            mode_name=voice.mode.name,
            mode_heat=voice.mode.heat,
            mode_hint=voice.mode.hint,
            drawer_name=voice.drawer_display or voice.drawer or "",
            drawer_reason=voice.reason,
            chosen_tell=voice.tell or "",
            avoids=", ".join(voice.avoids),
            yesterday_tell=voice.yesterday_tell or "",
            drawer_changed=bool(
                voice.yesterday_drawer
                and voice.drawer
                and voice.yesterday_drawer != voice.drawer
            ),
            drawer_spec=DRAWERS.get(voice.drawer or ""),
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
            mode_name=voice.mode.name,
            mode_heat=voice.mode.heat,
            mode_hint=voice.mode.hint,
            drawer_name=voice.drawer_display or voice.drawer or "",
            drawer_reason=voice.reason,
            chosen_tell=voice.tell or "",
            avoids=", ".join(voice.avoids),
            yesterday_tell=voice.yesterday_tell or "",
            drawer_changed=bool(
                voice.yesterday_drawer
                and voice.drawer
                and voice.yesterday_drawer != voice.drawer
            ),
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

    image_url: Optional[str] = None
    image_path: Optional[Path] = None
    imagined = False
    imagine_tried = 0
    imagine_kept: Optional[int] = None
    stamp = san_diego_now().strftime("%Y%m%d-%H%M")
    pending_image = out_dir / f"{stamp}_toast.jpg"

    if args.no_imagine:
        notes.append("Imagine skipped (--no-imagine).")
        print("Imagine skipped (--no-imagine).\n")
    elif dry:
        notes.append(
            "Imagine skipped (dry / no key). Paste the prompt into Grok Imagine when ready. "
            f"Live runs request {args.imagine_n} candidate(s) and keep the most legible burn-in."
        )
        print("Imagine skipped (dry / no key). Prompt is saved.\n")
    else:
        print(
            f"Summoning Grok Imagine ({IMAGINE_ASPECT_RATIO}, n={args.imagine_n}) "
            "via poem_visualizer.ImagineClient…"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        image_url, image_path, note, pick = _maybe_imagine(
            imagine_prompt,
            pending_image,
            haiku=haiku,
            n=args.imagine_n,
        )
        notes.append(note)
        imagine_tried = pick.tried
        imagine_kept = pick.kept_index
        for row in pick.scores:
            preview = (row.score.extracted or "").replace("\n", " / ")
            if len(preview) > 80:
                preview = preview[:79] + "…"
            bit = f"#{row.candidate.index} {row.score.summary()} [{row.method}]"
            if preview:
                bit += f" — {preview}"
            elif row.error:
                bit += f" — {row.error}"
            notes.append(f"Imagine candidate {bit}")
        imagined = image_path is not None
        if image_path:
            print(f"  {note}")
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
        voice=voice,
        image_url=image_url,
        imagine_n=args.imagine_n,
        imagine_tried=imagine_tried,
        imagine_kept=imagine_kept,
        notes=notes,
        write=write,
    )
    if user_preview:
        result.notes.append("Voice brief (system):\n\n" + VOICE_BRIEF.strip())
        result.notes.append("Writer user seed:\n\n" + user_preview)

    artifacts = save_artifacts(
        result, out_dir=out_dir, stamp=stamp, image_path=image_path
    )
    if voice.drawer and voice.tell:
        save_last_drawer(
            out_dir, date=today, drawer=voice.drawer, tell=voice.tell
        )

    print("─" * 56)
    print(f"Haiku  → {artifacts.haiku_path}")
    print(f"Report → {artifacts.report_path}")
    if artifacts.image_path:
        print(f"Image  → {artifacts.image_path}")
    print(
        f"Style `{style.name}` · mode `{voice.mode.name}` · "
        f"drawer `{drawer_label}`."
    )
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
