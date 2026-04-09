"""Tests for interception time calculator."""

import pytest
from bot.utils import calc_interception_times, _calc_travel_seconds, torus_distance


class TestCalcInterceptionTimes:
    """Test interception send-time calculation."""

    def test_basic_interception(self):
        """Calculate send times for tribe units to reach a village."""
        results = calc_interception_times(
            our_x=0, our_y=0,
            def_x=10, def_y=0,
            attack_eta_seconds=7200,  # Attack in 2 hours
            our_tribe=3,  # Gauls
            ts_level=0,
        )
        assert len(results) > 0
        for r in results:
            assert "name" in r
            assert "send_in_seconds" in r
            assert "travel_seconds" in r
            assert "can_make_it" in r

    def test_fast_unit_has_more_time(self):
        """Faster units have later send times (more time to spare)."""
        results = calc_interception_times(
            our_x=0, our_y=0, def_x=10, def_y=0,
            attack_eta_seconds=7200, our_tribe=3, ts_level=0,
        )
        tropiciel = next((r for r in results if "Tropiciel" in r["name"]), None)
        falanga = next((r for r in results if "Falanga" in r["name"]), None)
        if tropiciel and falanga and tropiciel["can_make_it"] and falanga["can_make_it"]:
            assert tropiciel["send_in_seconds"] > falanga["send_in_seconds"]

    def test_attack_too_soon_some_cant_make_it(self):
        """If attack is very soon, slow units can't make it."""
        results = calc_interception_times(
            our_x=0, our_y=0, def_x=50, def_y=0,
            attack_eta_seconds=600,  # 10 minutes
            our_tribe=1, ts_level=0,
        )
        catapult = next((r for r in results if "Katapulta" in r["name"]), None)
        if catapult:
            assert catapult["can_make_it"] is False

    def test_ts_shortens_travel_for_long_distance(self):
        """TS reduces travel time for distances > 20 fields."""
        results_no_ts = calc_interception_times(
            our_x=0, our_y=0, def_x=50, def_y=0,
            attack_eta_seconds=14400, our_tribe=3, ts_level=0,
        )
        results_with_ts = calc_interception_times(
            our_x=0, our_y=0, def_x=50, def_y=0,
            attack_eta_seconds=14400, our_tribe=3, ts_level=10,
        )
        for r_ts in results_with_ts:
            r_no = next((r for r in results_no_ts if r["name"] == r_ts["name"]), None)
            if r_no and r_ts["can_make_it"] and r_no["can_make_it"]:
                assert r_ts["send_in_seconds"] >= r_no["send_in_seconds"]

    def test_torus_distance_used(self):
        """Distance wraps around torus map correctly."""
        results = calc_interception_times(
            our_x=199, our_y=0, def_x=-199, def_y=0,
            attack_eta_seconds=7200, our_tribe=1, ts_level=0,
            map_size=401,
        )
        for r in results:
            assert r["can_make_it"] is True

    def test_zero_distance(self):
        """Same village → travel time 0, all units can make it."""
        results = calc_interception_times(
            our_x=10, our_y=10, def_x=10, def_y=10,
            attack_eta_seconds=60, our_tribe=2, ts_level=0,
        )
        for r in results:
            assert r["can_make_it"] is True
            assert r["travel_seconds"] == 0

    def test_sort_order_urgent_first(self):
        """Results sorted by send_in_seconds, most urgent (can_make_it) first."""
        results = calc_interception_times(
            our_x=0, our_y=0, def_x=30, def_y=0,
            attack_eta_seconds=3600, our_tribe=1, ts_level=0,
        )
        can_make = [r for r in results if r["can_make_it"]]
        cant_make = [r for r in results if not r["can_make_it"]]
        # All can_make_it entries come before can't
        if can_make and cant_make:
            last_can = results.index(can_make[-1])
            first_cant = results.index(cant_make[0])
            assert last_can < first_cant
        # Within can_make_it group, sorted ascending by send_in_seconds
        for i in range(1, len(can_make)):
            assert can_make[i]["send_in_seconds"] >= can_make[i - 1]["send_in_seconds"]

    def test_unknown_tribe_returns_empty(self):
        """Unknown tribe ID returns empty list."""
        results = calc_interception_times(
            our_x=0, our_y=0, def_x=10, def_y=0,
            attack_eta_seconds=7200, our_tribe=99,
        )
        assert results == []
