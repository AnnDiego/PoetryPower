"""
Local Imagine-style catalog for Daily Haiku Toast.

This is not the poem_visualizer styles/ catalog and does not import
style_loader. Add a ToastStyle (enabled=True) to put a new look in the
daily random pool — no even/odd or weekday hacks.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

# Ann-approved Imagine templates. {HAIKU} is the only substitution.
# Strengthened: exactly three lines; letters follow crumb as Maillard
# browning, not printed ink.

BUTTERED_TEMPLATE = """\
Photorealistic close-up of a single slice of freshly toasted artisan bread on a rustic wooden board, warm morning sidelight, faint steam. A haiku of exactly three lines is burned into the golden crust in darker toasted-brown letters, clearly readable, following the crumb texture:

{HAIKU}

Letters look like selective Maillard browning, not printed ink. A small pat of melting butter appears at one corner of the toast itself. Shallow depth of field, food-photography realism, no extra captions, no watermark.
"""

TOASTER_POPUP_TEMPLATE = """\
Photorealistic close-up of a single slice of freshly toasted artisan bread rising out of a stainless steel toaster, warm morning sidelight, faint steam. A haiku of exactly three lines is burned into the golden crust in darker toasted-brown letters, clearly readable, following the crumb texture:

{HAIKU}

Letters look like selective Maillard browning, not printed ink. Small morning breakfast items such as a glass of orange juice or cup of tea are visible in the background of the scene. Shallow depth of field, food-photography realism, no extra captions, no watermark.
"""


@dataclass(frozen=True)
class ToastStyle:
    """One Imagine look local to haiku_toast."""

    name: str
    display_name: str
    imagine_template: str
    enabled: bool = True
    notes: str = ""
    example: str = ""  # filename under scripts/haiku_toast/examples/

    def fill(self, haiku: str) -> str:
        """Substitute {HAIKU} only. Leave the rest of the template intact."""
        if self.imagine_template.count("{HAIKU}") != 1:
            raise ValueError(
                f"Style {self.name!r} must contain exactly one {{HAIKU}} placeholder."
            )
        return self.imagine_template.replace("{HAIKU}", haiku.strip())


# Enabled pool for v2. Plate / avocado / egg stay documented as future
# and are not catalogued here so they cannot be picked.
_STYLES: Sequence[ToastStyle] = (
    ToastStyle(
        name="buttered",
        display_name="Buttered (board)",
        imagine_template=BUTTERED_TEMPLATE,
        enabled=True,
        notes="Board default evolution. Melting butter on the toast itself.",
        example="buttered.jpg",
    ),
    ToastStyle(
        name="toaster_popup",
        display_name="Toaster popup",
        imagine_template=TOASTER_POPUP_TEMPLATE,
        enabled=True,
        notes="Slice rising from a stainless toaster; juice or tea in the blur.",
        example="toaster_popup.jpg",
    ),
)


def _normalize(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def load_catalog() -> List[ToastStyle]:
    """Return every catalogued style (enabled and disabled), name-sorted."""
    return sorted(_STYLES, key=lambda s: s.name)


def load_styles() -> Dict[str, ToastStyle]:
    """Return {name: ToastStyle} for the full catalog."""
    return {s.name: s for s in load_catalog()}


def enabled_styles(
    catalog: Optional[Iterable[ToastStyle]] = None,
) -> List[ToastStyle]:
    """Enabled styles only, name-sorted so seeded picks are stable."""
    styles = list(catalog) if catalog is not None else load_catalog()
    return sorted((s for s in styles if s.enabled), key=lambda s: s.name)


def enabled_names(catalog: Optional[Iterable[ToastStyle]] = None) -> List[str]:
    return [s.name for s in enabled_styles(catalog)]


def get_style(
    name: str,
    catalog: Optional[Iterable[ToastStyle]] = None,
) -> Optional[ToastStyle]:
    """Case-insensitive lookup by name or display_name (hyphens ok)."""
    styles = list(catalog) if catalog is not None else load_catalog()
    key = _normalize(name)
    if not key:
        return None
    for style in styles:
        if _normalize(style.name) == key:
            return style
        if _normalize(style.display_name) == key:
            return style
    return None


def choose_style(
    *,
    name: Optional[str] = None,
    seed: Optional[int] = None,
    catalog: Optional[Iterable[ToastStyle]] = None,
    rng: Optional[random.Random] = None,
) -> ToastStyle:
    """
    Pick one style.

    --style name  → that catalog entry (enabled or not, if present)
    otherwise     → random among enabled, optionally seeded
    """
    styles = list(catalog) if catalog is not None else load_catalog()
    if name:
        found = get_style(name, styles)
        if found is None:
            known = ", ".join(s.name for s in sorted(styles, key=lambda s: s.name)) or "(none)"
            raise ValueError(f"Unknown toast style {name!r}. Known: {known}")
        return found

    pool = enabled_styles(styles)
    if not pool:
        raise RuntimeError("No enabled toast styles in the catalog.")
    if rng is not None:
        chooser = rng
    elif seed is not None:
        chooser = random.Random(seed)
    else:
        chooser = random
    return chooser.choice(pool)


def fill_imagine_prompt(haiku: str, style: Optional[ToastStyle] = None) -> str:
    """Fill {HAIKU} in the given style, or buttered if none is supplied."""
    chosen = style or get_style("buttered")
    if chosen is None:
        raise RuntimeError("buttered style missing from the toast catalog.")
    return chosen.fill(haiku)
