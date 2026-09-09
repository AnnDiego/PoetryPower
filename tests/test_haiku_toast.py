"""Checks for the Daily Haiku Toast runner: locked template, dry path, weather parse."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.haiku_toast.prompts import (
    IMAGINE_TEMPLATE,
    KEEPER_SAMPLE_HAIKU,
    VOICE_BRIEF,
    fill_imagine_prompt,
    writer_user_prompt,
)
from scripts.haiku_toast.runner import format_date_line, run
from scripts.haiku_toast.syllables import (
    count_syllables,
    haiku_counts,
    is_way_off,
    parse_haiku,
)
from scripts.haiku_toast.weather import parse_open_meteo

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "scripts" / "haiku_toast" / "examples"


class LockedTemplateTests(unittest.TestCase):
    def test_template_has_single_placeholder(self) -> None:
        self.assertEqual(IMAGINE_TEMPLATE.count("{HAIKU}"), 1)
        self.assertIn("rustic wooden board", IMAGINE_TEMPLATE)
        self.assertIn("Maillard browning", IMAGINE_TEMPLATE)
        self.assertNotIn("ceramic plate", IMAGINE_TEMPLATE)
        self.assertNotIn("coffee", IMAGINE_TEMPLATE.lower())

    def test_fill_replaces_haiku_only(self) -> None:
        haiku = "one\ntwo\nthree"
        filled = fill_imagine_prompt(haiku)
        self.assertNotIn("{HAIKU}", filled)
        self.assertIn(haiku, filled)
        self.assertEqual(
            filled.replace(haiku, "{HAIKU}"),
            IMAGINE_TEMPLATE,
        )

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

    def test_dry_run_writes_haiku_and_report_without_key(self) -> None:
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
                ]
            )
            self.assertEqual(rc, 0)
            haikus = list(out.glob("*_haiku.txt"))
            reports = list(out.glob("*_toast.md"))
            self.assertEqual(len(haikus), 1)
            self.assertEqual(len(reports), 1)
            self.assertFalse(list(out.glob("*.jpg")))
            haiku_text = haikus[0].read_text(encoding="utf-8")
            report = reports[0].read_text(encoding="utf-8")
            self.assertIn("Crisp slice, quiet dawn", haiku_text)
            self.assertIn("Wednesday, September 9, 2026", report)
            self.assertIn("rustic wooden board", report)
            self.assertIn(KEEPER_SAMPLE_HAIKU, report)
            self.assertIn("Open-Meteo", report)
            self.assertIn("sassy-tender", report)
            self.assertIn("Dry run: **yes**", report)
            # Heading mentions the placeholder; the filled prompt must not.
            prompt_block = report.split("```", 2)[1]
            self.assertNotIn("{HAIKU}", prompt_block)
            self.assertIn("Crisp slice, quiet dawn", prompt_block)

    def test_reuses_visualizer_imagine_client(self) -> None:
        import scripts.haiku_toast.runner as runner
        from scripts.poem_visualizer.imagine_client import ImagineClient

        self.assertIs(runner._maybe_imagine.__globals__.get("ImagineClient"), None)
        # Import path is inside the function to keep startup thin; check source.
        src = Path(runner.__file__).read_text(encoding="utf-8")
        self.assertIn(
            "from scripts.poem_visualizer.imagine_client import ImagineClient",
            src,
        )
        self.assertTrue(hasattr(ImagineClient, "generate_image"))
        self.assertTrue(hasattr(ImagineClient, "from_env"))


class KeeperStillsTests(unittest.TestCase):
    def test_board_and_plate_examples_exist(self) -> None:
        board = EXAMPLES / "toast-board.jpg"
        plate = EXAMPLES / "toast-plate.jpg"
        self.assertTrue(board.is_file(), f"missing {board}")
        self.assertTrue(plate.is_file(), f"missing {plate}")
        self.assertGreater(board.stat().st_size, 1000)
        self.assertGreater(plate.stat().st_size, 1000)
        note = (EXAMPLES / "README.md").read_text(encoding="utf-8")
        self.assertIn("v1 default", note)
        self.assertIn("Later A/B", note)


if __name__ == "__main__":
    unittest.main()
