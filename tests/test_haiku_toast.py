"""Checks for the Daily Haiku Toast runner: catalog, dry path, weather parse."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.haiku_toast.prompts import (
    KEEPER_SAMPLE_HAIKU,
    VOICE_BRIEF,
    writer_user_prompt,
)
from scripts.haiku_toast.runner import format_date_line, run
from scripts.haiku_toast.style_catalog import (
    BUTTERED_TEMPLATE,
    TOASTER_POPUP_TEMPLATE,
    ToastStyle,
    choose_style,
    enabled_names,
    fill_imagine_prompt,
    get_style,
    load_catalog,
    load_styles,
)
from scripts.haiku_toast.syllables import (
    count_syllables,
    haiku_counts,
    is_way_off,
    parse_haiku,
)
from scripts.haiku_toast.weather import parse_open_meteo

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "scripts" / "haiku_toast" / "examples"
ENABLED = {"buttered", "toaster_popup"}


class StyleCatalogTests(unittest.TestCase):
    def test_loads_enabled_buttered_and_toaster_popup_only(self) -> None:
        catalog = load_catalog()
        names = {s.name for s in catalog}
        self.assertEqual(names, ENABLED)
        self.assertEqual(set(enabled_names()), ENABLED)
        self.assertEqual(set(load_styles()), ENABLED)
        for style in catalog:
            self.assertTrue(style.enabled)

    def test_lookup_accepts_hyphen_and_display_name(self) -> None:
        self.assertEqual(get_style("toaster_popup").name, "toaster_popup")
        self.assertEqual(get_style("toaster-popup").name, "toaster_popup")
        self.assertEqual(get_style("Buttered (board)").name, "buttered")
        self.assertIsNone(get_style("plate"))
        self.assertIsNone(get_style("avocado"))
        self.assertIsNone(get_style("egg"))

    def test_choose_style_override_and_unknown(self) -> None:
        self.assertEqual(choose_style(name="buttered").name, "buttered")
        self.assertEqual(choose_style(name="toaster_popup").name, "toaster_popup")
        with self.assertRaises(ValueError) as ctx:
            choose_style(name="avocado")
        self.assertIn("Unknown toast style", str(ctx.exception))
        self.assertIn("buttered", str(ctx.exception))

    def test_random_pick_stays_in_enabled_set(self) -> None:
        extra = list(load_catalog()) + [
            ToastStyle(
                name="plate",
                display_name="Plate (future)",
                imagine_template="plate {HAIKU}",
                enabled=False,
            )
        ]
        names = {choose_style(catalog=extra, seed=i).name for i in range(40)}
        self.assertTrue(names <= ENABLED)
        self.assertEqual(names, ENABLED)
        self.assertNotIn("plate", names)
        self.assertEqual(choose_style(catalog=extra, seed=1).name, choose_style(catalog=extra, seed=1).name)

    def test_templates_require_three_lines_and_maillard(self) -> None:
        for style in load_catalog():
            tmpl = style.imagine_template
            self.assertEqual(tmpl.count("{HAIKU}"), 1)
            self.assertIn("exactly three lines", tmpl)
            self.assertIn("crumb", tmpl.lower())
            self.assertIn("Maillard browning", tmpl)
            self.assertIn("not printed ink", tmpl)
            filled = style.fill(KEEPER_SAMPLE_HAIKU)
            self.assertNotIn("{HAIKU}", filled)
            self.assertIn(KEEPER_SAMPLE_HAIKU, filled)

    def test_fill_defaults_to_buttered(self) -> None:
        filled = fill_imagine_prompt("one\ntwo\nthree")
        self.assertIn("rustic wooden board", filled)
        self.assertIn("melting butter", filled)
        self.assertEqual(
            filled.replace("one\ntwo\nthree", "{HAIKU}"),
            BUTTERED_TEMPLATE,
        )
        toaster = fill_imagine_prompt("one\ntwo\nthree", get_style("toaster_popup"))
        self.assertIn("stainless steel toaster", toaster)
        self.assertIn("orange juice", toaster)
        self.assertNotIn("melting butter", toaster)
        self.assertEqual(
            toaster.replace("one\ntwo\nthree", "{HAIKU}"),
            TOASTER_POPUP_TEMPLATE,
        )


class LockedVoiceTests(unittest.TestCase):
    def test_voice_brief_is_the_approved_scrap(self) -> None:
        self.assertIn("sassy-tender", VOICE_BRIEF)
        self.assertIn("marine layer", VOICE_BRIEF)
        self.assertIn("not a forecast lecture", VOICE_BRIEF)
        self.assertIn("Hallmark zen", VOICE_BRIEF)

    def test_writer_user_prompt_seeds_date_and_weather(self) -> None:
        text = writer_user_prompt(
            date_line="Wednesday, September 9, 2026",
            weekday_vibe="hump-day stubbornness, marine or canyon",
            weather_seed="high 76°F / low 64°F, overcast",
        )
        self.assertIn("Wednesday, September 9, 2026", text)
        self.assertIn("high 76°F / low 64°F, overcast", text)
        self.assertIn("5-7-5", text)


class SyllableTests(unittest.TestCase):
    def test_keeper_sample_is_near_575(self) -> None:
        lines = KEEPER_SAMPLE_HAIKU.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertFalse(is_way_off(lines))
        counts = haiku_counts(lines)
        self.assertEqual(counts, [5, 7, 5])

    def test_way_off_catches_a_howler_and_wrong_line_count(self) -> None:
        self.assertTrue(is_way_off(["this line has far too many syllables for a haiku opening"]))
        self.assertTrue(
            is_way_off(
                [
                    "a very long opening line that is nowhere near five",
                    "and another even longer middle line that refuses to be seven syllables",
                    "plus a last line that also rambles well past five",
                ]
            )
        )
        self.assertFalse(is_way_off(["crisp slice quiet dawn", "ink of heat writes seventeen", "syllables of gold"]))

    def test_parse_haiku_strips_fences_and_chatter(self) -> None:
        raw = (
            "Sure, here you go:\n"
            "```\n"
            "Crisp slice, quiet dawn\n"
            "ink of heat writes seventeen\n"
            "syllables of gold\n"
            "```\n"
        )
        lines, text = parse_haiku(raw)
        self.assertEqual(len(lines), 3)
        self.assertIn("Crisp slice, quiet dawn", text)

    def test_seventeen_is_three_syllables(self) -> None:
        self.assertEqual(count_syllables("seventeen"), 3)


class WeatherParseTests(unittest.TestCase):
    def test_parse_open_meteo_daily(self) -> None:
        seed = parse_open_meteo(
            {
                "daily": {
                    "temperature_2m_max": [76.2],
                    "temperature_2m_min": [64.4],
                    "weather_code": [3],
                }
            }
        )
        self.assertTrue(seed.ok)
        self.assertEqual(seed.high_f, 76)
        self.assertEqual(seed.low_f, 64)
        self.assertEqual(seed.condition, "overcast")
        self.assertIn("high 76°F / low 64°F, overcast", seed.seed_line())
        self.assertEqual(seed.source, "Open-Meteo")

    def test_parse_failure_is_soft(self) -> None:
        seed = parse_open_meteo({})
        self.assertFalse(seed.ok)
        self.assertIn("unavailable", seed.seed_line())


class DateAndDryRunTests(unittest.TestCase):
    def test_format_date_line_unpadded_day(self) -> None:
        when = datetime(2026, 9, 9, 8, 15, tzinfo=ZoneInfo("America/Los_Angeles"))
        self.assertEqual(format_date_line(when), "Wednesday, September 9, 2026")

    def _dry(self, extra: list[str]) -> tuple[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rc = run(
                [
                    "--dry-run",
                    "--no-weather",
                    "--date",
                    "2026-09-09",
                    "--out-dir",
                    str(out),
                    *extra,
                ]
            )
            self.assertEqual(rc, 0)
            haikus = list(out.glob("*_haiku.txt"))
            reports = list(out.glob("*_toast.md"))
            self.assertEqual(len(haikus), 1)
            self.assertEqual(len(reports), 1)
            self.assertFalse(list(out.glob("*.jpg")))
            return haikus[0].read_text(encoding="utf-8"), reports[0].read_text(encoding="utf-8")

    def test_dry_run_writes_haiku_and_report_without_key(self) -> None:
        haiku_text, report = self._dry(["--style", "buttered"])
        self.assertIn("Crisp slice, quiet dawn", haiku_text)
        self.assertIn("Wednesday, September 9, 2026", report)
        self.assertIn("style `buttered`", report)
        self.assertIn("**Chosen:** `buttered`", report)
        self.assertIn("`--style buttered`", report)
        self.assertIn("rustic wooden board", report)
        self.assertIn("exactly three lines", report)
        self.assertIn("melting butter", report)
        self.assertIn(KEEPER_SAMPLE_HAIKU, report)
        self.assertIn("Open-Meteo", report)
        self.assertIn("sassy-tender", report)
        self.assertIn("Dry run: **yes**", report)
        self.assertIn("Imagine: **skipped (dry / no key)**", report)
        prompt_block = report.split("```", 2)[1]
        self.assertNotIn("{HAIKU}", prompt_block)
        self.assertIn("Crisp slice, quiet dawn", prompt_block)

    def test_dry_run_toaster_popup_override(self) -> None:
        _, report = self._dry(["--style", "toaster_popup"])
        self.assertIn("style `toaster_popup`", report)
        self.assertIn("stainless steel toaster", report)
        self.assertIn("orange juice", report)
        self.assertNotIn("melting butter", report.split("```", 2)[1])

    def test_dry_run_seed_is_reproducible(self) -> None:
        _, report_a = self._dry(["--seed", "7"])
        _, report_b = self._dry(["--seed", "7"])
        chosen_a = [ln for ln in report_a.splitlines() if ln.startswith("- **Chosen:**")]
        chosen_b = [ln for ln in report_b.splitlines() if ln.startswith("- **Chosen:**")]
        self.assertEqual(chosen_a, chosen_b)
        self.assertEqual(len(chosen_a), 1)
        self.assertRegex(chosen_a[0], r"`(buttered|toaster_popup)`")
        self.assertIn("`--seed 7`", report_a)
        self.assertIn("random among enabled", report_a)

    def test_unknown_style_exits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                run(
                    [
                        "--dry-run",
                        "--no-weather",
                        "--style",
                        "avocado",
                        "--out-dir",
                        tmp,
                    ]
                )
            self.assertIn("Unknown toast style", str(ctx.exception))

    def test_reuses_visualizer_imagine_client(self) -> None:
        import scripts.haiku_toast.runner as runner
        from scripts.poem_visualizer.imagine_client import ImagineClient

        self.assertIs(runner._maybe_imagine.__globals__.get("ImagineClient"), None)
        src = Path(runner.__file__).read_text(encoding="utf-8")
        self.assertIn(
            "from scripts.poem_visualizer.imagine_client import ImagineClient",
            src,
        )
        self.assertNotIn("poem_visualizer.style_loader", src)
        self.assertTrue(hasattr(ImagineClient, "generate_image"))
        self.assertTrue(hasattr(ImagineClient, "from_env"))


class KeeperStillsTests(unittest.TestCase):
    def test_enabled_and_future_examples_exist(self) -> None:
        buttered = EXAMPLES / "buttered.jpg"
        toaster = EXAMPLES / "toaster_popup.jpg"
        plate = EXAMPLES / "toast-plate.jpg"
        board = EXAMPLES / "toast-board.jpg"
        for path in (buttered, toaster, plate, board):
            self.assertTrue(path.is_file(), f"missing {path}")
            self.assertGreater(path.stat().st_size, 1000)
        note = (EXAMPLES / "README.md").read_text(encoding="utf-8")
        self.assertIn("buttered", note)
        self.assertIn("toaster_popup", note)
        self.assertIn("not in the enabled pool", note)
        self.assertIn("avocado", note)
        self.assertIn("egg", note)


if __name__ == "__main__":
    unittest.main()
