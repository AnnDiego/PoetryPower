"""
Common helpers: repo root discovery, poem file I/O, light text utilities.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


def find_repo_root(start: Optional[Path] = None) -> Path:
    """
    Walk upward from *start* (or this file) until we find a directory that
    looks like the ChiefPoetSpaceX repo root (has styles/ and/or poems/).
    """
    here = (start or Path(__file__)).resolve()
    if here.is_file():
        here = here.parent

    for candidate in [here, *here.parents]:
        if (candidate / "styles").is_dir() or (candidate / "poems").is_dir():
            return candidate

    # Fallback: three levels up from this package (scripts/poem_visualizer/)
    return Path(__file__).resolve().parents[2]


def read_text_file(path: Path) -> str:
    """Read a UTF-8 text/markdown file, raising a friendly ValueError on failure."""
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read {path}: {exc}") from exc


def resolve_poem_path(raw: str, repo_root: Optional[Path] = None) -> Path:
    """
    Resolve a user-supplied poem path.
    Tries the path as-is, then relative to cwd, then poems/ under repo root.
    """
    raw = raw.strip().strip("\"'")
    candidates = [
        Path(raw).expanduser(),
        Path.cwd() / raw,
    ]
    root = repo_root or find_repo_root()
    candidates.append(root / raw)
    candidates.append(root / "poems" / raw)
    candidates.append(root / "poems" / Path(raw).name)

    for p in candidates:
        if p.exists() and p.is_file():
            return p.resolve()

    raise FileNotFoundError(
        f"Couldn't find poem file '{raw}'. "
        "Tried cwd, repo root, and poems/ — check the path and try again."
    )


def guess_title(poem_text: str, fallback: str = "Untitled Verse") -> str:
    """Tolerant title sniffer: first short non-prose line, or filename-ish fallback."""
    prose_hints = (
        "a poem", "inspired by", "join the cosmic", "for starship",
        "check out my", "by ann", "---",
    )
    for line in poem_text.splitlines()[:10]:
        cl = line.strip()
        if not cl or len(cl) > 70:
            continue
        cl_clean = cl.lstrip("#*_ ").strip().rstrip(".,;:!? ")
        cl_lower = cl_clean.lower()
        if any(cl_lower.startswith(h) for h in prose_hints):
            continue
        if 3 < len(cl_clean) < 60:
            return cl_clean
    return fallback


def slugify(text: str, max_len: int = 48) -> str:
    """Filename-safe slug from a title or style name."""
    s = text.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "_", s).strip("_")
    return (s or "poem")[:max_len]


def default_output_path(
    source_path: Optional[Path],
    title: str,
    repo_root: Optional[Path] = None,
) -> Path:
    """
    Build a markdown path next to the original poem, or under poems/ / cwd
    if the poem was pasted.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    name = f"{slugify(title)}_visualizer_{stamp}.md"

    if source_path is not None:
        return source_path.parent / name

    root = repo_root or find_repo_root()
    poems_dir = root / "poems"
    if poems_dir.is_dir():
        return poems_dir / name
    return Path.cwd() / name


def collapse_whitespace(text: str) -> str:
    """Normalize runs of whitespace for keyword matching."""
    return re.sub(r"\s+", " ", text).strip()


def read_poem_interactive() -> Tuple[str, Optional[Path]]:
    """
    CLI input: paste poem (END to finish) or load from file path.
    Returns (poem_text, source_path_or_None).
    """
    print("How shall we feed the muse?")
    print("  [p] Paste poem text")
    print("  [f] Load from .md / .txt file")
    choice = input("\nYour pick (p/f) [p]: ").strip().lower() or "p"

    if choice.startswith("f"):
        raw = input("Path to file: ").strip().strip("\"'")
        path = resolve_poem_path(raw)
        text = read_text_file(path)
        print(f"\nLoaded: {path}\n")
        return text, path

    print("\nPaste your poem. Include blank lines for stanzas — they matter.")
    print("When you're done, type END on its own line and hit return.\n")

    collected: list[str] = []
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
        raise SystemExit(
            "No poem detected. Exiting with dignity "
            "(and a grid fin tucked under one arm)."
        )
    return text, None
