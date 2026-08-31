"""Minimal style-catalog checks: load, auto-match, motion language."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.poem_visualizer.prompts import motion_for_style
from scripts.poem_visualizer.style_loader import get_style, load_all_styles
from scripts.poem_visualizer.style_matcher import score_styles, suggest_style

REPO_ROOT = Path(__file__).resolve().parents[1]

LEGACY_STYLES = {
    "charcoal_sketch",
    "romantic_anime",
    "moody_comic",
    "artistic_collage",
    "anime_cyberpunk",
}


class StyleCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.styles = load_all_styles(repo_root=REPO_ROOT)

    def test_loads_thick_impasto_and_legacy_styles(self) -> None:
        self.assertIn("thick_impasto", self.styles)
        self.assertTrue(LEGACY_STYLES.issubset(self.styles.keys()))
        style = self.styles["thick_impasto"]
        self.assertEqual(style.name, "thick_impasto")
        self.assertEqual(style.display_name, "Thick Impasto")
        self.assertTrue(style.vibe)
        self.assertIn("{poem_summary}", style.base_prompt)
        self.assertIn("{mood}", style.base_prompt)
        self.assertTrue(style.notes)
        self.assertTrue(style.examples)

    def test_lookup_by_name_and_display_name(self) -> None:
        by_key = get_style(self.styles, "thick_impasto")
        by_display = get_style(self.styles, "Thick Impasto")
        self.assertIsNotNone(by_key)
        self.assertIsNotNone(by_display)
        assert by_key is not None and by_display is not None
        self.assertEqual(by_key.name, "thick_impasto")
        self.assertEqual(by_display.name, "thick_impasto")

    def test_examples_are_stills_only(self) -> None:
        types = {ex.type for ex in self.styles["thick_impasto"].examples}
        ids = [ex.id for ex in self.styles["thick_impasto"].examples]
        self.assertTrue(types <= {"text_to_image", "image_to_image"})
        self.assertNotIn("text_to_video", types)
        self.assertIn("moonlit_window", ids)
        self.assertTrue(all(not i.endswith("_motion") for i in ids))

    def test_matcher_scores_thick_impasto(self) -> None:
        poem = (
            "Tactile oil on canvas, palette-knife ridges and a paint-storm "
            "over a lush painted field; moonlit interior oil, thick and sculptural."
        )
        ranked = score_styles(poem, self.styles)
        by_name = {r.name: r for r in ranked}
        self.assertIn("thick_impasto", by_name)
        self.assertGreater(by_name["thick_impasto"].score, 0.01)
        self.assertEqual(suggest_style(poem, self.styles).name, "thick_impasto")

    def test_legacy_styles_still_match(self) -> None:
        cases = {
            "charcoal_sketch": (
                "A hush of charcoal on paper, a delicate pencil sketch "
                "of desert dunes and a faint smudged twilight."
            ),
            "anime_cyberpunk": (
                "Neon cyber streets, chrome touchscreen glow, "
                "a futuristic Tokyo alley in the rain."
            ),
            "moody_comic": (
                "A noir comic panel, cinematic ink, bittersweet "
                "spotlight on a lonely phone in the dark."
            ),
            "artistic_collage": (
                "Layered collage of handwritten verses and fabric scraps, "
                "threads bind a phoenix of reinvention."
            ),
            "romantic_anime": (
                "Soft sakura petals, a tender anime kiss, "
                "warm ramen-shop blush and cherry blossoms."
            ),
        }
        for expected, poem in cases.items():
            with self.subTest(style=expected):
                self.assertEqual(suggest_style(poem, self.styles).name, expected)

    def test_motion_language_for_thick_impasto(self) -> None:
        motion = motion_for_style(self.styles["thick_impasto"])
        self.assertIn("paint ridges", motion.lower())
        self.assertIn("palette knife", motion.lower())
        self.assertIn("not live-action", motion.lower())
        # Existing styles keep their dedicated motion, not the default fallback
        charcoal = motion_for_style(self.styles["charcoal_sketch"])
        self.assertIn("paper-grain", charcoal)


if __name__ == "__main__":
    unittest.main()
