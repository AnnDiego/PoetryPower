"""Checks for the Daily Haiku Toast runner: catalog, dry path, weather parse."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from scripts.haiku_toast.prompts import (
    KEEPER_SAMPLE_HAIKU,
    VOICE_BRIEF,
    VOICE_SEED_PATH,
    writer_user_prompt,
)
from scripts.haiku_toast.runner import format_date_line, render_report, run, RunResult
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
from scripts.haiku_toast.voice_modes import (
    MODE_NAMES,
    choose_mode,
    get_mode,
    primary_pool,
)
from scripts.haiku_toast.weather import WeatherSeed, parse_open_meteo

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
    def test_voice_brief_is_the_locked_poetess_seed(self) -> None:
        self.assertTrue(VOICE_SEED_PATH.is_file())
        self.assertEqual(VOICE_BRIEF, VOICE_SEED_PATH.read_text(encoding="utf-8").strip())
        self.assertIn("Poetess Ann", VOICE_BRIEF)
        self.assertIn("Sensual-cosmic lyric", VOICE_BRIEF)
        self.assertIn("Heat ceiling 0–2", VOICE_BRIEF)
        self.assertIn("breakfast voltage", VOICE_BRIEF)
        self.assertIn("Do NOT regenerate for syllable counts", VOICE_BRIEF)
        self.assertNotIn("sassy-tender", VOICE_BRIEF)
        self.assertNotIn("Hallmark zen", VOICE_BRIEF)

    def test_writer_user_prompt_seeds_date_weather_and_mode(self) -> None:
        text = writer_user_prompt(
            date_line="Wednesday, September 9, 2026",
            weekday_vibe="hump-day stubbornness, marine or canyon",
            weather_seed="high 76°F / low 64°F, overcast",
            mode_name="verdant",
            mode_heat="0–1",
            mode_hint="Mist, May gray / June gloom",
        )
        self.assertIn("Wednesday, September 9, 2026", text)
        self.assertIn("high 76°F / low 64°F, overcast", text)
        self.assertIn("Voice mode for this run: verdant", text)
        self.assertIn("three-line haiku", text)
        self.assertIn("morning scrap", text)
        self.assertIn("do not regenerate for syllable counts", text)
        self.assertNotIn("Write one English 5-7-5", text)


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

    def test_writer_does_not_retry_on_counts(self) -> None:
        from scripts.haiku_toast import writer as writer_mod

        src = Path(writer_mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("is_way_off", src)
        self.assertNotIn("rewrite_user_prompt", src)
        self.assertNotIn("regenerated", src)
        self.assertNotIn("rewrite_user_prompt", dir(writer_mod))


class VoiceModeTests(unittest.TestCase):
    def test_five_locked_modes(self) -> None:
        self.assertEqual(
            MODE_NAMES,
            ["verdant", "starlit_dawn", "tender", "picnic_wink", "soft_weather_soul"],
        )
        self.assertEqual(get_mode("starlit-dawn").name, "starlit_dawn")
        self.assertIsNone(get_mode("siren"))

    def test_weather_primary_pools(self) -> None:
        overcast = WeatherSeed(ok=True, high_f=68, low_f=58, condition="overcast")
        names, _, reason = primary_pool(overcast)
        self.assertEqual(set(names), {"verdant", "soft_weather_soul"})
        self.assertIn("overcast", reason)

        rain = WeatherSeed(ok=True, high_f=64, low_f=55, condition="rain")
        names, _, reason = primary_pool(rain)
        self.assertEqual(names, ["soft_weather_soul"])

        fog = WeatherSeed(ok=True, high_f=66, low_f=57, condition="fog")
        self.assertEqual(set(primary_pool(fog)[0]), {"verdant", "soft_weather_soul"})

        cool_clear = WeatherSeed(ok=True, high_f=68, low_f=52, condition="clear")
        early_names, early_w, early_r = primary_pool(cool_clear, hour=6)
        self.assertEqual(set(early_names), {"starlit_dawn", "verdant"})
        self.assertGreater(early_w["starlit_dawn"], early_w["verdant"])
        self.assertIn("starlit_dawn weighted", early_r)
        later_names, later_w, _ = primary_pool(cool_clear, hour=10)
        self.assertGreater(later_w["verdant"], later_w["starlit_dawn"])

        warm_clear = WeatherSeed(ok=True, high_f=78, low_f=64, condition="sunny")
        self.assertEqual(set(primary_pool(warm_clear)[0]), {"verdant", "picnic_wink"})

        windy = WeatherSeed(ok=True, high_f=70, low_f=58, condition="windy")
        self.assertEqual(set(primary_pool(windy)[0]), {"soft_weather_soul", "verdant"})

        missing = WeatherSeed(ok=False, error="--no-weather")
        self.assertEqual(set(primary_pool(missing)[0]), set(MODE_NAMES))

    def test_choose_mode_override_and_unknown(self) -> None:
        weather = WeatherSeed(ok=True, high_f=70, low_f=58, condition="rain")
        pick = choose_mode(weather, name="tender")
        self.assertEqual(pick.mode.name, "tender")
        self.assertEqual(pick.selection, "cli")
        self.assertIn("--mode tender", pick.reason)
        with self.assertRaises(ValueError) as ctx:
            choose_mode(weather, name="siren")
        self.assertIn("Unknown voice mode", str(ctx.exception))

    def test_failed_weather_random_stays_in_five_modes(self) -> None:
        missing = WeatherSeed(ok=False, error="unavailable")
        names = {
            choose_mode(missing, seed=i, allow_alternate=False).mode.name
            for i in range(40)
        }
        self.assertTrue(names <= set(MODE_NAMES))
        self.assertEqual(names, set(MODE_NAMES))
        self.assertEqual(
            choose_mode(missing, seed=3).mode.name,
            choose_mode(missing, seed=3).mode.name,
        )

    def test_rain_primary_without_alternate_is_weather_soul(self) -> None:
        rain = WeatherSeed(ok=True, high_f=64, low_f=55, condition="rain")
        pick = choose_mode(rain, seed=1, allow_alternate=False)
        self.assertEqual(pick.mode.name, "soft_weather_soul")
        self.assertEqual(pick.selection, "weather")


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
        self.assertIn("Poetess Ann", report)
        self.assertIn("Sensual-cosmic lyric", report)
        self.assertIn("## Voice mode", report)
        self.assertIn("report-only, not a gate", report)
        self.assertNotIn("target 5-7-5", report)
        self.assertIn("Dry run: **yes**", report)
        self.assertIn("Imagine: **skipped (dry / no key)**", report)
        self.assertIn("Imagine candidates: 4 would be requested", report)
        self.assertIn("`--imagine-n`", report)
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
        self.assertEqual(len(chosen_a), 2)
        self.assertRegex(chosen_a[0], r"`(buttered|toaster_popup)`")
        self.assertRegex(
            chosen_a[1],
            r"`(verdant|starlit_dawn|tender|picnic_wink|soft_weather_soul)`",
        )
        self.assertIn("`--seed 7`", report_a)
        self.assertIn("random among enabled", report_a)

    def test_dry_run_mode_override_is_separate_from_style(self) -> None:
        _, report = self._dry(["--style", "toaster_popup", "--mode", "tender"])
        self.assertIn("style `toaster_popup`", report)
        self.assertIn("mode `tender`", report)
        self.assertIn("`--mode tender`", report)
        self.assertIn("stainless steel toaster", report)
        self.assertIn("Voice mode for this run: tender", report)

    def test_unknown_mode_exits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                run(
                    [
                        "--dry-run",
                        "--no-weather",
                        "--mode",
                        "siren",
                        "--out-dir",
                        tmp,
                    ]
                )
            self.assertIn("Unknown voice mode", str(ctx.exception))

    def test_haiku_override_still_fills_the_template(self) -> None:
        supplied = "Harbor light, leftover\nramen steam on the laptop\nPadres night crumbs"
        haiku_text, report = self._dry(
            ["--style", "buttered", "--haiku", supplied.replace("\n", "\\n")]
        )
        self.assertIn("Harbor light, leftover", haiku_text)
        self.assertIn("Harbor light, leftover", report)
        self.assertIn("writer skipped", report.lower())
        prompt_block = report.split("```", 2)[1]
        self.assertIn("Harbor light, leftover", prompt_block)
        self.assertIn("rustic wooden board", prompt_block)

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
        self.assertTrue(hasattr(ImagineClient, "collect_image_urls"))
        self.assertIn("collect_image_urls", src)
        self.assertIn("pick_legible_still", src)
        self.assertIn("--imagine-n", src)


class ImagineNFlagTests(unittest.TestCase):
    def test_imagine_n_override_appears_on_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc = run(
                [
                    "--dry-run",
                    "--no-weather",
                    "--style",
                    "buttered",
                    "--imagine-n",
                    "3",
                    "--out-dir",
                    tmp,
                ]
            )
            self.assertEqual(rc, 0)
            report = next(Path(tmp).glob("*_toast.md")).read_text(encoding="utf-8")
            self.assertIn("Imagine candidates: 3 would be requested", report)

    def test_imagine_n_out_of_range_exits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                run(
                    [
                        "--dry-run",
                        "--no-weather",
                        "--imagine-n",
                        "0",
                        "--out-dir",
                        tmp,
                    ]
                )
            self.assertIn("--imagine-n must be between 1 and 10", str(ctx.exception))


class LegibilityTests(unittest.TestCase):
    """Selection helper: keeper-like misspellings pass; 2026-09-10 garbles fail."""

    KEEPER = KEEPER_SAMPLE_HAIKU
    KEEPER_BUTTERED = (
        "Crispslice, quiet dawnn\ninkofheatwrittes seventeen\nsylllables ofgoldd"
    )
    KEEPER_TOASTER = (
        "Crispslice, quiet dawnn\nink of heat writeseventeen\nsylllables of goldd"
    )
    GARBLED = [
        "Maikiku,\ncheckered\nhaiku",
        "haiku\nsoundeugh\nhoiku",
        "Haiku baects\nno tove drink\nhaiku mistost",
        "",
        "hello world breakfast photo",
    ]

    def test_score_accepts_keeperish_and_rejects_garbage(self) -> None:
        from scripts.haiku_toast.legibility import score_burn_in

        self.assertTrue(score_burn_in(self.KEEPER, self.KEEPER).passed)
        self.assertTrue(score_burn_in(self.KEEPER_BUTTERED, self.KEEPER).passed)
        self.assertTrue(score_burn_in(self.KEEPER_TOASTER, self.KEEPER).passed)
        for text in self.GARBLED:
            score = score_burn_in(text, self.KEEPER)
            self.assertFalse(score.passed, msg=repr(text))

    def test_pick_keeps_best_passer_and_fails_closed(self) -> None:
        from scripts.haiku_toast.legibility import (
            ExtractResult,
            StillCandidate,
            pick_legible_still,
        )

        cands = [
            StillCandidate(index=1, url="http://a"),
            StillCandidate(index=2, url="http://b"),
            StillCandidate(index=3, url="http://c"),
        ]
        texts = {
            1: self.GARBLED[0],
            2: self.KEEPER_BUTTERED,
            3: self.GARBLED[1],
        }

        def extract(cand: StillCandidate) -> ExtractResult:
            return ExtractResult(text=texts[cand.index], method="fake")

        pick = pick_legible_still(self.KEEPER, cands, extract_fn=extract)
        self.assertTrue(pick.ok)
        self.assertEqual(pick.tried, 3)
        self.assertEqual(pick.kept_index, 2)
        self.assertIn("kept candidate #2 of 3", pick.note)

        all_bad = pick_legible_still(
            self.KEEPER,
            cands,
            extract_fn=lambda c: ExtractResult(text=self.GARBLED[0], method="fake"),
        )
        self.assertFalse(all_bad.ok)
        self.assertIsNone(all_bad.kept)
        self.assertIn("not shipping", all_bad.note.lower())
        self.assertIn("garbled", all_bad.note.lower())

        unread = pick_legible_still(
            self.KEEPER,
            cands,
            extract_fn=lambda c: ExtractResult(
                text="", method="none", error="no reader"
            ),
        )
        self.assertFalse(unread.ok)
        self.assertIn("could not read", unread.note)

    def test_report_records_kept_and_all_failed(self) -> None:
        weather = WeatherSeed(ok=False, error="--no-weather")
        base = dict(
            date_line="Wednesday, September 9, 2026",
            weekday="Wednesday",
            weather=weather,
            haiku=self.KEEPER,
            imagine_prompt="prompt",
            dry=False,
            wrote_live=False,
            imagined=True,
            imagine_n=4,
            imagine_tried=4,
            imagine_kept=2,
            image_url="http://example.com/toast.jpg",
        )
        kept = render_report(RunResult(**base))
        self.assertIn("Imagine: **ok**", kept)
        self.assertIn("kept #2 of 4 requested", kept)

        failed = render_report(
            RunResult(
                **{
                    **base,
                    "imagined": False,
                    "imagine_kept": None,
                    "image_url": None,
                }
            )
        )
        self.assertIn("Imagine: **failed (no legible burn-in)**", failed)
        self.assertIn("none passed (requested 4) — still not shipped", failed)

    def test_maybe_imagine_does_not_ship_garbage(self) -> None:
        from scripts.haiku_toast.legibility import ExtractResult
        from scripts.haiku_toast.runner import _maybe_imagine
        from scripts.poem_visualizer.imagine_client import ImagineResult

        client = MagicMock()
        client.collect_image_urls.return_value = ImagineResult(
            ok=True, url="http://a", urls=["http://a", "http://b"]
        )

        def fake_dl(url: str, path: Path) -> None:
            path.write_bytes(b"fake-jpg")
            return None

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "20260910-0800_toast.jpg"
            with patch(
                "scripts.poem_visualizer.imagine_client.ImagineClient.from_env",
                return_value=client,
            ), patch("scripts.haiku_toast.runner._download_image", side_effect=fake_dl):
                url, path, note, pick = _maybe_imagine(
                    "prompt",
                    dest,
                    haiku=self.KEEPER,
                    n=2,
                    extract_fn=lambda c: ExtractResult(
                        text="Maikiku, checkered haiku", method="fake"
                    ),
                )
            self.assertIsNone(url)
            self.assertIsNone(path)
            self.assertFalse(dest.exists())
            self.assertFalse(pick.ok)
            self.assertIn("not shipping", note.lower())
            self.assertEqual(len(list(Path(tmp).glob("*rejected*"))), 2)

    def test_maybe_imagine_keeps_the_legible_draw(self) -> None:
        from scripts.haiku_toast.legibility import ExtractResult, StillCandidate
        from scripts.haiku_toast.runner import _maybe_imagine
        from scripts.poem_visualizer.imagine_client import ImagineResult

        client = MagicMock()
        client.collect_image_urls.return_value = ImagineResult(
            ok=True, url="http://a", urls=["http://a", "http://b"]
        )
        texts = {1: "Maikiku, checkered haiku", 2: self.KEEPER_BUTTERED}

        def fake_dl(url: str, path: Path) -> None:
            path.write_bytes(b"winner" if "cand2" in path.name else b"junk")
            return None

        def extract(cand: StillCandidate) -> ExtractResult:
            return ExtractResult(text=texts[cand.index], method="fake")

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "20260910-0800_toast.jpg"
            with patch(
                "scripts.poem_visualizer.imagine_client.ImagineClient.from_env",
                return_value=client,
            ), patch("scripts.haiku_toast.runner._download_image", side_effect=fake_dl):
                url, path, note, pick = _maybe_imagine(
                    "prompt", dest, haiku=self.KEEPER, n=2, extract_fn=extract
                )
            self.assertEqual(url, "http://b")
            self.assertEqual(path, dest)
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.read_bytes(), b"winner")
            self.assertTrue(pick.ok)
            self.assertEqual(pick.kept_index, 2)
            self.assertIn("kept candidate #2", note)
            self.assertFalse(list(Path(tmp).glob("*_cand*")))


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
