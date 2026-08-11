"""
Load and manage the living style catalog under styles/.

Each style lives in its own folder:
    styles/<style_name>/style.yaml
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .utils import find_repo_root


@dataclass
class StyleExample:
    """A single example prompt attached to a style (for reference / future use)."""

    id: str
    type: str  # e.g. text_to_image, image_to_image
    prompt: str


@dataclass
class Style:
    """One visual style from the catalog."""

    name: str
    display_name: str
    vibe: str
    base_prompt: str
    notes: str = ""
    examples: List[StyleExample] = field(default_factory=list)
    path: Optional[Path] = None  # folder that held style.yaml

    def format_base_prompt(self, poem_summary: str, mood: str) -> str:
        """Fill {poem_summary} and {mood} placeholders in base_prompt."""
        return (
            self.base_prompt
            .replace("{poem_summary}", poem_summary.strip())
            .replace("{mood}", mood.strip())
            .strip()
        )


def _parse_examples(raw: Any) -> List[StyleExample]:
    if not raw or not isinstance(raw, list):
        return []
    out: List[StyleExample] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            StyleExample(
                id=str(item.get("id", "unnamed")),
                type=str(item.get("type", "text_to_image")),
                prompt=str(item.get("prompt", "")).strip(),
            )
        )
    return out


def load_style_file(yaml_path: Path) -> Style:
    """Load a single style.yaml into a Style dataclass."""
    yaml_path = yaml_path.resolve()
    with yaml_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Invalid style file (expected mapping): {yaml_path}")

    name = str(data.get("name") or yaml_path.parent.name).strip()
    return Style(
        name=name,
        display_name=str(data.get("display_name") or name).strip(),
        vibe=str(data.get("vibe") or "").strip(),
        base_prompt=str(data.get("base_prompt") or "").rstrip(),
        notes=str(data.get("notes") or "").strip(),
        examples=_parse_examples(data.get("examples")),
        path=yaml_path.parent,
    )


def styles_dir(repo_root: Optional[Path] = None) -> Path:
    """Return the absolute path to the styles/ catalog."""
    root = repo_root or find_repo_root()
    return (root / "styles").resolve()


def load_all_styles(
    catalog_dir: Optional[Path] = None,
    *,
    repo_root: Optional[Path] = None,
) -> Dict[str, Style]:
    """
    Scan styles/* /style.yaml and return {style_name: Style}.

    Skips hidden folders and non-directories. Raises if none are found.
    """
    base = Path(catalog_dir) if catalog_dir else styles_dir(repo_root)
    if not base.is_dir():
        raise FileNotFoundError(
            f"Style catalog not found at {base}. "
            "Expected styles/<name>/style.yaml under the repo root."
        )

    styles: Dict[str, Style] = {}
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        yaml_path = child / "style.yaml"
        if not yaml_path.is_file():
            # Allow style.yml as a soft fallback
            yaml_path = child / "style.yml"
        if not yaml_path.is_file():
            continue
        style = load_style_file(yaml_path)
        styles[style.name] = style

    if not styles:
        raise FileNotFoundError(
            f"No style.yaml files found under {base}. "
            "Add at least one styles/<name>/style.yaml and try again."
        )
    return styles


def get_style(styles: Dict[str, Style], name: str) -> Optional[Style]:
    """Case-insensitive lookup by name or display_name."""
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    if key in styles:
        return styles[key]
    for style in styles.values():
        if style.name.lower() == key:
            return style
        if style.display_name.lower().replace(" ", "_") == key:
            return style
        if style.display_name.lower() == name.strip().lower():
            return style
    return None


def format_style_list(styles: Dict[str, Style]) -> str:
    """Pretty multi-line listing for the CLI."""
    lines = []
    for name in sorted(styles.keys()):
        s = styles[name]
        vibe_short = s.vibe if len(s.vibe) <= 100 else s.vibe[:97] + "…"
        lines.append(f"  • {s.name:20}  {s.display_name}")
        lines.append(f"      vibe: {vibe_short}")
        if s.notes:
            notes_short = s.notes if len(s.notes) <= 90 else s.notes[:87] + "…"
            lines.append(f"      notes: {notes_short}")
    return "\n".join(lines)
