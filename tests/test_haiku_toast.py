"""Checks for the Daily Haiku Toast runner: catalog, dry path, weather parse."""

from __future__ import annotations

import json
import random
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
from scripts.haiku_toast.drawers import (
    DRAWER_CLEAR_HOT,
    DRAWER_CLEAR_MILD,
    DRAWER_FOG,
    DRAWER_HYBRID,
    DRAWER_OVERCAST,
    DRAWER_RAIN,
    DRAWER_STARLIT,
    DRAWERS,
    LastDrawer,
    choose_tell,
    choose_tell_filtered,
    drawer_voice_problems,
    extract_key_words,
    load_last_drawer,
    prior_mornings,
    recent_noun_reuse,
    recent_signature_nouns,
    save_last_drawer,
    select_drawer,
    soft_nature_doubledip,
    soft_nature_hits,
    tell_collides_with_recent,
    yesterday_note,
)
from scripts.haiku_toast.voice_modes import (
    MODE_NAMES,
    choose_mode,
    get_mode,
    mode_for_drawer,
)
from scripts.haiku_toast.weather import (
    WeatherSeed,
    fetch_san_diego_weather,
    parse_open_meteo,
)

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
        self.assertIn("Do not double-dip the soft-nature body lexicon", VOICE_BRIEF)
        self.assertIn("recent mornings' signature nouns", VOICE_BRIEF)
        self.assertIn("one required drawer tell", VOICE_BRIEF)
        self.assertNotIn("sassy-tender", VOICE_BRIEF)
        self.assertNotIn("Hallmark zen", VOICE_BRIEF)

    def test_writer_user_prompt_seeds_date_weather_and_mode(self) -> None:
        text = writer_user_prompt(
            date_line="Wednesday, September 9, 2026",
            weekday_vibe="hump-day stubbornness, marine or canyon",
            weather_seed="06:00 PT hourly · code 0 clear · 81°F",
            mode_name="sun_ode",
            mode_heat="0–1",
            mode_hint="Sun-ode. Photons on forehead",
            drawer_name="CLEAR HOT",
            drawer_reason="weather_code 0, 81°F ≥ 75 at 06:00 → CLEAR HOT",
            chosen_tell="photons on forehead",
            avoids="gray on the pane, mist, clover-as-weather",
        )
        self.assertIn("Wednesday, September 9, 2026", text)
        self.assertIn("06:00 PT hourly · code 0 clear · 81°F", text)
        self.assertIn("Voice mode for this run: sun_ode", text)
        self.assertIn("Weather drawer: CLEAR HOT", text)
        self.assertIn("photons on forehead", text)
        self.assertIn("three-line haiku", text)
        self.assertIn("morning scrap", text)
        self.assertIn("do not regenerate for syllable counts", text)
        self.assertIn("Never raise chili", text)
        self.assertIn("Do not double-dip the soft-nature body lexicon", text)
        self.assertNotIn("Write one English 5-7-5", text)

    def test_writer_user_prompt_names_recent_nouns(self) -> None:
        text = writer_user_prompt(
            date_line="Thursday, September 10, 2026",
            weekday_vibe="slow start",
            weather_seed="06:30 PT hourly · code 45 fog · 62°F",
            mode_name="verdant",
            mode_heat="0–1",
            chosen_tell="chimes still",
            recent_nouns="clover, mist, toes",
            nature_only=True,
        )
        self.assertIn("Do not repeat recent mornings' signature nouns: clover, mist, toes", text)
        self.assertIn("one required tell", text)
        self.assertIn("nature-forward", text)
        self.assertNotIn("Prefer one weather/nature tell + one other voltage", text)


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


TZ = ZoneInfo("America/Los_Angeles")
FIXTURE_20260909 = REPO_ROOT / "tests" / "fixtures" / "open_meteo_20260909_sandiego.json"
SUNRISE_0909 = datetime(2026, 9, 9, 6, 28, tzinfo=TZ)


def _snap(**kwargs) -> WeatherSeed:
    """Morning hourly snapshot; defaults are a mild clear 8am (CLEAR MILD)."""
    base = dict(
        ok=True,
        high_f=80,
        low_f=60,
        condition="clear",
        weather_code=0,
        cloud_cover=10,
        visibility_m=30000,
        relative_humidity_2m=50,
        temperature_2m=70,
        precipitation=0.0,
        precipitation_probability=0,
        is_day=1,
        sunrise=SUNRISE_0909,
        pull_at=datetime(2026, 9, 9, 8, 0, tzinfo=TZ),
    )
    base.update(kwargs)
    return WeatherSeed(**base)


class VoiceModeTests(unittest.TestCase):
    def test_mode_lookup_and_aliases(self) -> None:
        self.assertIn("sun_ode", MODE_NAMES)
        self.assertIn("hybrid_burnoff", MODE_NAMES)
        self.assertIn("rain", MODE_NAMES)
        self.assertIn("clear_mild", MODE_NAMES)
        self.assertIn("tender", MODE_NAMES)
        self.assertEqual(get_mode("starlit-dawn").name, "starlit_dawn")
        self.assertEqual(get_mode("clear_hot").name, "sun_ode")
        self.assertEqual(get_mode("fog").name, "verdant")
        self.assertIsNone(get_mode("siren"))

    def test_choose_mode_override_and_unknown(self) -> None:
        weather = _snap(weather_code=61, precipitation=0.2)
        pick = choose_mode(weather, name="tender")
        self.assertEqual(pick.mode.name, "tender")
        self.assertEqual(pick.selection, "cli")
        self.assertIn("--mode tender", pick.reason)
        with self.assertRaises(ValueError) as ctx:
            choose_mode(weather, name="siren")
        self.assertIn("Unknown voice mode", str(ctx.exception))

    def test_failed_weather_falls_back_to_clear_mild(self) -> None:
        missing = WeatherSeed(ok=False, error="unavailable")
        pick = choose_mode(missing, seed=3)
        self.assertEqual(pick.mode.name, "clear_mild")
        self.assertEqual(pick.selection, "fallback")
        self.assertEqual(pick.drawer, DRAWER_CLEAR_MILD)
        self.assertEqual(pick.mode.heat, "0–1")

    def test_rain_hourly_is_rain_mode(self) -> None:
        rain = _snap(weather_code=61, precipitation=0.4, temperature_2m=64)
        pick = choose_mode(rain, seed=1)
        self.assertEqual(pick.mode.name, "rain")
        self.assertEqual(pick.selection, "weather")
        self.assertEqual(pick.drawer, DRAWER_RAIN)
        self.assertEqual(pick.mode.heat, "0–1")


class DrawerTreeTests(unittest.TestCase):
    def _name(self, **kwargs) -> str:
        return select_drawer(_snap(**kwargs)).name

    def test_rain_from_precip_and_from_code(self) -> None:
        self.assertEqual(self._name(precipitation=0.2, weather_code=0), DRAWER_RAIN)
        self.assertEqual(self._name(precipitation=0, weather_code=61), DRAWER_RAIN)
        self.assertEqual(self._name(precipitation=0, weather_code=80), DRAWER_RAIN)
        self.assertEqual(self._name(precipitation=0, weather_code=95), DRAWER_RAIN)
        reason = select_drawer(_snap(precipitation=0.4, weather_code=0)).reason
        self.assertIn("RAIN", reason)
        self.assertIn("precipitation", reason)

    def test_fog_from_code_and_from_vis_rh(self) -> None:
        self.assertEqual(self._name(weather_code=45, precipitation=0), DRAWER_FOG)
        self.assertEqual(self._name(weather_code=48, precipitation=0), DRAWER_FOG)
        self.assertEqual(
            self._name(
                weather_code=1,
                precipitation=0,
                visibility_m=1500,
                relative_humidity_2m=88,
            ),
            DRAWER_FOG,
        )
        # Rain wins if both signals fire.
        self.assertEqual(
            self._name(
                weather_code=45,
                precipitation=0.1,
                visibility_m=1500,
                relative_humidity_2m=90,
            ),
            DRAWER_RAIN,
        )

    def test_overcast_from_code_and_cloud(self) -> None:
        self.assertEqual(
            self._name(weather_code=3, precipitation=0, cloud_cover=70),
            DRAWER_OVERCAST,
        )
        self.assertEqual(
            self._name(weather_code=2, precipitation=0, cloud_cover=90),
            DRAWER_OVERCAST,
        )

    def test_hybrid_burnoff(self) -> None:
        self.assertEqual(
            self._name(
                weather_code=2,
                cloud_cover=55,
                temperature_2m=74,
                precipitation=0,
                is_day=1,
                pull_at=datetime(2026, 9, 9, 8, 0, tzinfo=TZ),
            ),
            DRAWER_HYBRID,
        )
        # Too cool at pull → not hybrid.
        self.assertEqual(
            self._name(
                weather_code=2,
                cloud_cover=55,
                temperature_2m=70,
                precipitation=0,
                is_day=1,
                pull_at=datetime(2026, 9, 9, 8, 0, tzinfo=TZ),
            ),
            DRAWER_CLEAR_MILD,
        )

    def test_clear_hot(self) -> None:
        self.assertEqual(
            self._name(
                weather_code=0,
                temperature_2m=81,
                precipitation=0,
                cloud_cover=0,
                is_day=0,
                pull_at=datetime(2026, 9, 9, 6, 0, tzinfo=TZ),
            ),
            DRAWER_CLEAR_HOT,
        )
        self.assertEqual(
            self._name(
                weather_code=1,
                temperature_2m=75,
                precipitation=0,
                is_day=1,
            ),
            DRAWER_CLEAR_HOT,
        )

    def test_starlit_dawn(self) -> None:
        # Clear + cool + still dark → starlit (CLEAR HOT needs ≥75).
        self.assertEqual(
            self._name(
                weather_code=0,
                temperature_2m=68,
                precipitation=0,
                cloud_cover=5,
                is_day=0,
                pull_at=datetime(2026, 9, 9, 6, 0, tzinfo=TZ),
            ),
            DRAWER_STARLIT,
        )
        # After sunrise but within 40 min, moon/Venus override.
        self.assertEqual(
            self._name(
                weather_code=1,
                temperature_2m=68,
                precipitation=0,
                is_day=1,
                pull_at=datetime(2026, 9, 9, 6, 50, tzinfo=TZ),
                bodies_up=True,
            ),
            DRAWER_STARLIT,
        )
        # After the dawn window → mild, not starlit.
        self.assertEqual(
            self._name(
                weather_code=0,
                temperature_2m=68,
                precipitation=0,
                is_day=1,
                pull_at=datetime(2026, 9, 9, 8, 0, tzinfo=TZ),
                bodies_up=True,
            ),
            DRAWER_CLEAR_MILD,
        )

    def test_clear_mild_else(self) -> None:
        self.assertEqual(
            self._name(
                weather_code=0,
                temperature_2m=70,
                precipitation=0,
                is_day=1,
                pull_at=datetime(2026, 9, 9, 8, 0, tzinfo=TZ),
            ),
            DRAWER_CLEAR_MILD,
        )
        self.assertEqual(
            self._name(
                weather_code=2,
                cloud_cover=20,
                temperature_2m=70,
                precipitation=0,
                is_day=1,
            ),
            DRAWER_CLEAR_MILD,
        )

    def test_2026_09_09_clear_hot_fixture(self) -> None:
        data = json.loads(FIXTURE_20260909.read_text(encoding="utf-8"))
        when = datetime(2026, 9, 9, 6, 30, tzinfo=TZ)
        seed = parse_open_meteo(data, when=when)
        self.assertTrue(seed.ok)
        self.assertEqual(seed.weather_code, 0)
        self.assertGreaterEqual(seed.temperature_2m, 75)
        self.assertEqual(seed.pull_at.hour, 6)
        self.assertEqual(seed.high_f, 95)
        # Daily weather_code 2 must not steal the morning drawer.
        self.assertEqual(data["daily"]["weather_code"][0], 2)
        decision = select_drawer(seed)
        self.assertEqual(decision.name, DRAWER_CLEAR_HOT)
        self.assertIn("CLEAR HOT", decision.reason)
        self.assertIn("morning hourly", decision.reason)
        pick = choose_mode(seed, seed=1)
        self.assertEqual(pick.mode.name, "sun_ode")
        self.assertEqual(pick.mode.heat, "0–1")
        self.assertEqual(pick.drawer, DRAWER_CLEAR_HOT)
        self.assertNotIn("heat 2", pick.reason.lower())

    def test_temperature_never_raises_heat(self) -> None:
        hot = _snap(weather_code=0, temperature_2m=105, precipitation=0)
        pick = choose_mode(hot, seed=1)
        self.assertEqual(pick.mode.heat, "0–1")
        for name in DRAWERS:
            self.assertEqual(mode_for_drawer(name).heat, "0–1")
            self.assertEqual(DRAWERS[name].heat, "0–1")

    def test_prefer_morning_over_afternoon_daily(self) -> None:
        # Socked-in morning, even if we stash a blazing daily high.
        morning = _snap(
            weather_code=3,
            cloud_cover=95,
            temperature_2m=64,
            high_f=92,
            precipitation=0,
        )
        self.assertEqual(select_drawer(morning).name, DRAWER_OVERCAST)

    def test_yesterday_tell_skipped_when_drawer_changes(self) -> None:
        spec = DRAWERS[DRAWER_CLEAR_HOT]
        reused = choose_tell(
            spec,
            yesterday_drawer=DRAWER_FOG,
            yesterday_tell="photons on forehead",
            rng=random.Random(0),
        )
        self.assertNotEqual(reused, "photons on forehead")
        # Same drawer may reuse.
        same = choose_tell(
            spec,
            yesterday_drawer=DRAWER_CLEAR_HOT,
            yesterday_tell="photons on forehead",
            rng=random.Random(0),
        )
        self.assertIn(same, spec.tells)

    def test_drawer_state_is_previous_day_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            save_last_drawer(
                path, date="2026-09-09", drawer=DRAWER_FOG, tell="mist"
            )
            y_d, y_t = yesterday_note(
                LastDrawer("2026-09-09", DRAWER_FOG, "mist"), "2026-09-10"
            )
            self.assertEqual((y_d, y_t), (DRAWER_FOG, "mist"))
            same_day = yesterday_note(
                LastDrawer("2026-09-10", DRAWER_FOG, "mist"), "2026-09-10"
            )
            self.assertEqual(same_day, (None, None))

    def test_writer_rejects_clear_hot_fog_lexicon(self) -> None:
        spec = DRAWERS[DRAWER_CLEAR_HOT]
        bad = "gray still on the pane\nmist in the clover\nsoulmate moonbeams"
        problems = drawer_voice_problems(bad, spec, "photons on forehead")
        self.assertTrue(any("tell" in p for p in problems))
        self.assertTrue(any("pane" in p or "fog" in p for p in problems))
        good = "photons on my forehead\nthe day coaxes a shirt loose\ngold wins"
        self.assertEqual(drawer_voice_problems(good, spec, "photons on forehead"), [])


class AntiRepetitionTests(unittest.TestCase):
    ANN_SCRAP = (
        "gray marine at dawn\n"
        "sun creeps from my toes inward\n"
        "clover drinks the mist"
    )

    def test_toes_and_clover_is_within_scrap_doubledip(self) -> None:
        self.assertTrue(soft_nature_doubledip(self.ANN_SCRAP, "clover"))
        self.assertIn("toes", soft_nature_hits(self.ANN_SCRAP))
        self.assertIn("clover", soft_nature_hits(self.ANN_SCRAP))
        self.assertIn("mist", soft_nature_hits(self.ANN_SCRAP))
        problems = drawer_voice_problems(
            self.ANN_SCRAP, DRAWERS[DRAWER_FOG], "clover"
        )
        self.assertTrue(any("double-dip" in p for p in problems))

    def test_key_words_keep_cluster_not_generic_sun(self) -> None:
        words = extract_key_words("clover", self.ANN_SCRAP)
        self.assertIn("clover", words)
        self.assertIn("toes", words)
        self.assertIn("mist", words)
        self.assertIn("marine", words)
        self.assertNotIn("sun", words)
        self.assertNotIn("gray", words)

    def test_single_tell_is_not_doubledip(self) -> None:
        scrap = "clover drinks the dew\npillow fails as a dawn-shield\nI keep the extra mug"
        self.assertFalse(soft_nature_doubledip(scrap, "clover"))
        self.assertEqual(
            drawer_voice_problems(scrap, DRAWERS[DRAWER_FOG], "clover"),
            [],
        )

    def test_hybrid_pane_toes_tell_is_not_doubledip(self) -> None:
        tell = "pane still gray / sun finds the toes"
        scrap = "pane still gray this hour\nsun finds the toes at last\ncoffee steams the mug"
        self.assertFalse(soft_nature_doubledip(scrap, tell))
        piled = scrap.replace("coffee steams the mug", "clover drinks the mist")
        self.assertTrue(soft_nature_doubledip(piled, tell))

    def test_choose_tell_skips_recent_soft_earth_when_alternatives_exist(self) -> None:
        spec = DRAWERS[DRAWER_FOG]
        recent = [
            LastDrawer(
                date="2026-09-08",
                drawer=DRAWER_FOG,
                tell="clover",
                motifs=("soft_earth",),
                key_words=("clover", "mist", "toes"),
            )
        ]
        picked = {
            choose_tell(spec, recent=recent, rng=random.Random(i))
            for i in range(40)
        }
        self.assertTrue(picked)
        self.assertTrue(picked <= set(spec.tells))
        self.assertNotIn("clover", picked)
        self.assertNotIn("mist", picked)
        self.assertNotIn("pane", picked)
        self.assertNotIn("peat", picked)
        self.assertTrue(picked & {"chimes still", "shirt-to-skin chill", "gray concede"})

    def test_choose_tell_falls_back_when_all_recent(self) -> None:
        spec = DRAWERS[DRAWER_HYBRID]
        recent = [
            LastDrawer(
                date="2026-09-07",
                drawer=DRAWER_HYBRID,
                tell=tell,
                key_words=tuple(extract_key_words(tell)),
            )
            for tell in spec.tells
        ]
        picked = choose_tell(spec, recent=recent, rng=random.Random(0))
        self.assertIn(picked, spec.tells)

    def test_recent_history_skip_same_drawer_tell(self) -> None:
        spec = DRAWERS[DRAWER_CLEAR_MILD]
        recent = [
            LastDrawer(
                date="2026-09-09",
                drawer=DRAWER_CLEAR_MILD,
                tell="brie",
                key_words=("brie", "coffee"),
            )
        ]
        self.assertTrue(tell_collides_with_recent("brie", recent))
        tell, skipped = choose_tell_filtered(
            spec, recent=recent, rng=random.Random(1)
        )
        self.assertNotEqual(tell, "brie")
        self.assertIn("brie", skipped)

    def test_rolling_history_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            first = save_last_drawer(
                out,
                date="2026-09-07",
                drawer=DRAWER_FOG,
                tell="clover",
                haiku=self.ANN_SCRAP,
            )
            self.assertTrue(first.is_file())
            day1 = load_last_drawer(out)
            self.assertIsNotNone(day1)
            assert day1 is not None
            self.assertEqual(day1.tell, "clover")
            self.assertIn("clover", day1.key_words)
            self.assertIn("toes", day1.key_words)
            self.assertIn("mist", day1.key_words)
            save_last_drawer(
                out,
                date="2026-09-08",
                drawer=DRAWER_CLEAR_HOT,
                tell="photons on forehead",
                haiku="photons on my forehead\nthe day coaxes a shirt loose\ngold wins",
                previous=day1,
            )
            day2 = load_last_drawer(out)
            assert day2 is not None
            prior = prior_mornings(day2, "2026-09-09")
            self.assertEqual([m.date for m in prior], ["2026-09-08", "2026-09-07"])
            self.assertEqual(prior[0].tell, "photons on forehead")
            self.assertEqual(prior[1].tell, "clover")
            save_last_drawer(
                out,
                date="2026-09-09",
                drawer=DRAWER_CLEAR_MILD,
                tell="brie",
                haiku="first ray on the cloth\nbrie waits beside the coffee\nwet lawn keeps the ants",
                previous=day2,
            )
            day3 = load_last_drawer(out)
            assert day3 is not None
            recent = prior_mornings(day3, "2026-09-10")
            self.assertEqual(
                [m.date for m in recent],
                ["2026-09-09", "2026-09-08", "2026-09-07"],
            )
            nouns = recent_signature_nouns(recent)
            self.assertIn("brie", nouns)
            self.assertIn("photons", nouns)
            self.assertIn("clover", nouns)

    def test_recent_noun_reuse_ignores_todays_tell(self) -> None:
        reused = recent_noun_reuse(
            "clover drinks the dew\nyour mug still waiting\nI leave the wool alone",
            "clover",
            ["clover", "mist", "toes"],
        )
        self.assertEqual(reused, [])
        reused = recent_noun_reuse(
            self.ANN_SCRAP,
            "chimes still",
            ["clover", "mist", "toes"],
        )
        self.assertIn("clover", reused)
        self.assertIn("mist", reused)
        self.assertIn("toes", reused)

    def test_writer_retries_once_on_doubledip(self) -> None:
        from scripts.haiku_toast import writer as writer_mod

        good = "clover drinks the dew\npillow fails as a dawn-shield\nI keep the extra mug"
        replies = [self.ANN_SCRAP, good]

        def _fake_chat(**_kwargs: object) -> str:
            return replies.pop(0)

        with patch.object(writer_mod, "_chat_complete", side_effect=_fake_chat):
            with patch.object(writer_mod, "resolve_api_key", return_value="test-key"):
                result = writer_mod.write_haiku(
                    date_line="Thursday, September 10, 2026",
                    weekday_vibe="slow start",
                    weather_seed="fog",
                    mode_name="verdant",
                    chosen_tell="clover",
                    recent_nouns="toes, mist",
                    nature_only=True,
                    drawer_spec=DRAWERS[DRAWER_FOG],
                    api_key="test-key",
                )
        self.assertTrue(result.ok)
        self.assertEqual(result.haiku, good)
        self.assertEqual(len(result.raw_replies), 2)

    def test_report_notes_avoided_recent_motifs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            save_last_drawer(
                out,
                date="2026-09-08",
                drawer=DRAWER_FOG,
                tell="clover",
                haiku=self.ANN_SCRAP,
            )
            data = json.loads(FIXTURE_20260909.read_text(encoding="utf-8"))
            seed = parse_open_meteo(
                data, when=datetime(2026, 9, 9, 6, 30, tzinfo=TZ)
            )
            with patch(
                "scripts.haiku_toast.runner.fetch_san_diego_weather",
                return_value=seed,
            ):
                rc = run(
                    [
                        "--dry-run",
                        "--date",
                        "2026-09-09",
                        "--style",
                        "buttered",
                        "--out-dir",
                        str(out),
                    ]
                )
            self.assertEqual(rc, 0)
            report = next(out.glob("*_toast.md")).read_text(encoding="utf-8")
            self.assertIn("**Avoided recent motifs:**", report)
            avoided_line = next(
                ln for ln in report.splitlines()
                if ln.startswith("- **Avoided recent motifs:**")
            )
            self.assertIn("clover", avoided_line)
            self.assertIn("mist", avoided_line)
            self.assertIn("toes", avoided_line)
            self.assertNotIn("sun", avoided_line)
            self.assertNotIn("Skipped drawer tells: clover", report)
            self.assertIn("Do not repeat recent mornings' signature nouns", report)
            state = json.loads((out / ".last_drawer.json").read_text(encoding="utf-8"))
            self.assertEqual(state["drawer"], DRAWER_CLEAR_HOT)
            self.assertTrue(state["history"])
            self.assertEqual(state["history"][0]["tell"], "clover")


class WeatherParseTests(unittest.TestCase):
    def test_parse_open_meteo_hourly(self) -> None:
        data = json.loads(FIXTURE_20260909.read_text(encoding="utf-8"))
        seed = parse_open_meteo(
            data, when=datetime(2026, 9, 9, 6, 30, tzinfo=TZ)
        )
        self.assertTrue(seed.ok)
        self.assertEqual(seed.weather_code, 0)
        self.assertEqual(seed.condition, "clear")
        self.assertAlmostEqual(seed.temperature_2m, 81.4)
        self.assertEqual(seed.cloud_cover, 0)
        self.assertEqual(seed.visibility_m, 33900)
        self.assertEqual(seed.relative_humidity_2m, 54)
        self.assertEqual(seed.precipitation, 0)
        self.assertEqual(seed.is_day, 0)
        self.assertEqual(seed.sunrise.hour, 6)
        self.assertEqual(seed.sunrise.minute, 28)
        self.assertEqual(seed.high_f, 95)
        self.assertEqual(seed.low_f, 74)
        self.assertIn("06:00 PT hourly", seed.seed_line())
        self.assertIn("code 0", seed.seed_line())
        self.assertEqual(seed.source, "Open-Meteo")

    def test_parse_failure_is_soft(self) -> None:
        seed = parse_open_meteo({})
        self.assertFalse(seed.ok)
        self.assertIn("unavailable", seed.seed_line())

    def test_daily_only_payload_is_unavailable(self) -> None:
        seed = parse_open_meteo(
            {
                "daily": {
                    "temperature_2m_max": [76.2],
                    "temperature_2m_min": [64.4],
                    "weather_code": [3],
                }
            }
        )
        self.assertFalse(seed.ok)
        self.assertIn("hourly", seed.error or "")

    def test_fetch_asks_for_hourly_not_daily_code(self) -> None:
        try:
            import requests  # noqa: F401
        except ImportError:
            self.skipTest("requests not installed")

        class _Resp:
            status_code = 200

            def json(self) -> dict:
                return json.loads(FIXTURE_20260909.read_text(encoding="utf-8"))

        with patch("requests.get", return_value=_Resp()) as get:
            seed = fetch_san_diego_weather(
                when=datetime(2026, 9, 9, 6, 30, tzinfo=TZ)
            )
        self.assertTrue(seed.ok)
        params = get.call_args.kwargs.get("params") or get.call_args[1]
        hourly = params["hourly"]
        daily = params["daily"]
        for field in (
            "weather_code",
            "cloud_cover",
            "visibility",
            "relative_humidity_2m",
            "temperature_2m",
            "precipitation",
            "precipitation_probability",
            "is_day",
        ):
            self.assertIn(field, hourly)
        self.assertIn("sunrise", daily)
        self.assertNotIn("weather_code", daily.split(","))


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
        self.assertIn("## Weather drawer", report)
        self.assertIn("CLEAR MILD", report)
        self.assertIn("**Tell:**", report)
        self.assertIn("**Avoided recent motifs:** none yet", report)
        self.assertIn("hourly at pull hour", report)
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
            r"`(verdant|starlit_dawn|tender|picnic_wink|soft_weather_soul|"
            r"hybrid_burnoff|sun_ode|rain|clear_mild)`",
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

    def test_dry_run_fixture_names_clear_hot_drawer(self) -> None:
        data = json.loads(FIXTURE_20260909.read_text(encoding="utf-8"))
        seed = parse_open_meteo(
            data, when=datetime(2026, 9, 9, 6, 30, tzinfo=TZ)
        )
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "scripts.haiku_toast.runner.fetch_san_diego_weather",
                return_value=seed,
            ):
                rc = run(
                    [
                        "--dry-run",
                        "--date",
                        "2026-09-09",
                        "--style",
                        "buttered",
                        "--out-dir",
                        tmp,
                    ]
                )
            self.assertEqual(rc, 0)
            report = next(Path(tmp).glob("*_toast.md")).read_text(encoding="utf-8")
            self.assertIn("CLEAR HOT", report)
            self.assertIn("mode `sun_ode`", report)
            self.assertIn("## Weather drawer", report)
            self.assertIn("morning hourly", report)
            self.assertIn("not used for the drawer or chili", report)
            self.assertIn("heat 0–1", report)
            self.assertNotIn("high/low °F + one condition word", report)
            state = Path(tmp) / ".last_drawer.json"
            self.assertTrue(state.is_file())
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["drawer"], DRAWER_CLEAR_HOT)

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
