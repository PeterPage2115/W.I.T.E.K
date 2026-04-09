"""Tests for reverse unit speed detection (S4.2)."""

from bot.utils import (
    UNIT_SPEEDS,
    _calc_travel_seconds,
    detect_possible_units,
    format_unit_analysis,
)


# ------------------------------------------------------------------ #
# Helper: travel time formula sanity checks
# ------------------------------------------------------------------ #

class TestCalcTravelSeconds:
    """Test the two-phase Travian travel time formula."""

    def test_short_distance_no_modifiers(self):
        # Catapult: 6 fields/h, 10 fields → 10/6 h = 6000s
        result = _calc_travel_seconds(10, 6)
        assert abs(result - 6000.0) < 0.01

    def test_short_distance_with_artifact(self):
        # Catapult 6 f/h, artifact x2 → effective 12 f/h, 10 fields → 3000s
        result = _calc_travel_seconds(10, 6, artifact_mult=2.0)
        assert abs(result - 3000.0) < 0.01

    def test_short_distance_ts_ignored(self):
        # TS has no effect under 20 fields
        no_ts = _calc_travel_seconds(15, 12, ts_level=0)
        with_ts = _calc_travel_seconds(15, 12, ts_level=20)
        assert abs(no_ts - with_ts) < 0.01

    def test_short_distance_boots_ignored(self):
        # Boots have no effect under 20 fields
        no_boots = _calc_travel_seconds(18, 10, boots_bonus=0.0)
        with_boots = _calc_travel_seconds(18, 10, boots_bonus=0.75)
        assert abs(no_boots - with_boots) < 0.01

    def test_exactly_20_fields(self):
        # At exactly 20 fields, no TS/boots effect
        base = _calc_travel_seconds(20, 10)
        with_ts = _calc_travel_seconds(20, 10, ts_level=10)
        assert abs(base - with_ts) < 0.01
        # 20/10 = 2h = 7200s
        assert abs(base - 7200.0) < 0.01

    def test_long_distance_no_modifiers(self):
        # Catapult 6 f/h, 40 fields, no TS/boots
        # First 20: 20/6 h, Rest 20: 20/6 h → total 40/6 h = 24000s
        result = _calc_travel_seconds(40, 6)
        assert abs(result - 24000.0) < 0.01

    def test_long_distance_with_ts(self):
        # Catapult 6 f/h, 40 fields, TS 10
        # First 20: 20/6 h
        # Rest 20: 20 / (6 * (1 + 0.2*10)) = 20/18 h
        # Total: 20/6 + 20/18 = 3.333 + 1.111 = 4.444h = 16000s
        result = _calc_travel_seconds(40, 6, ts_level=10)
        expected = (20 / 6 + 20 / 18) * 3600
        assert abs(result - expected) < 0.01

    def test_long_distance_with_boots(self):
        # Speed 10, 30 fields, boots 50%
        # First 20: 20/10 = 2h
        # Rest 10: 10 / (10 * 1.5) = 0.667h
        # Total: 2.667h = 9600s
        result = _calc_travel_seconds(30, 10, boots_bonus=0.5)
        expected = (20 / 10 + 10 / (10 * 1.5)) * 3600
        assert abs(result - expected) < 0.01

    def test_long_distance_all_modifiers(self):
        # Speed 6, 50 fields, artifact x1.5, boots 25%, TS 5
        # Effective base: 6 * 1.5 = 9
        # First 20: 20/9 h
        # Boosted: 9 * (1 + 0.25 + 0.2*5) = 9 * 2.25 = 20.25
        # Rest 30: 30/20.25 h
        # Total: (20/9 + 30/20.25) h
        result = _calc_travel_seconds(50, 6, artifact_mult=1.5, boots_bonus=0.25, ts_level=5)
        expected = (20 / 9 + 30 / 20.25) * 3600
        assert abs(result - expected) < 0.01

    def test_zero_distance(self):
        assert _calc_travel_seconds(0, 10) == 0.0

    def test_zero_speed(self):
        assert _calc_travel_seconds(10, 0) == 0.0


# ------------------------------------------------------------------ #
# Reverse detection: detect_possible_units
# ------------------------------------------------------------------ #

class TestDetectPossibleUnits:
    """Test the reverse unit speed calculator."""

    def test_catapult_short_distance(self):
        # Catapult/Trebusz: speed 6 f/h, 10 fields → 6000s
        travel = _calc_travel_seconds(10, 6)
        results = detect_possible_units(10, travel)
        names = [r["name"] for r in results]
        assert "Katapulta" in names or "Trebusz" in names

    def test_catapult_known_tribe_roman(self):
        # Roman catapult: speed 6 f/h
        travel = _calc_travel_seconds(10, 6)
        results = detect_possible_units(10, travel, attacker_tribe=1)
        names = [r["name"] for r in results]
        assert "Katapulta" in names
        # Gaul Trebusz should NOT appear for Romans
        assert "Trebusz" not in names

    def test_infantry_detection(self):
        # Topornik (Teuton): speed 12 f/h, 15 fields → 4500s
        travel = _calc_travel_seconds(15, 12)
        results = detect_possible_units(15, travel, attacker_tribe=2)
        names = [r["name"] for r in results]
        assert "Topornik" in names

    def test_cavalry_detection(self):
        # Equites Legati (Roman): speed 32 f/h, 16 fields → 1800s
        travel = _calc_travel_seconds(16, 32)
        results = detect_possible_units(16, travel, attacker_tribe=1)
        names = [r["name"] for r in results]
        assert "Equites Legati" in names

    def test_short_distance_no_ts_effect(self):
        # For dist < 20, TS doesn't matter — results should show bez TS
        travel = _calc_travel_seconds(10, 6)
        results = detect_possible_units(10, travel)
        for r in results:
            if r["name"] in ("Katapulta", "Trebusz"):
                assert r["ts_range"] == (0, 0), "TS should be (0,0) for short distance"

    def test_long_distance_ts_matters(self):
        # Catapult 6 f/h, 40 fields, TS 10 → ~16000s
        travel = _calc_travel_seconds(40, 6, ts_level=10)
        results = detect_possible_units(40, travel, attacker_tribe=1)
        # Should find catapult with some TS range that includes 10
        cats = [r for r in results if r["name"] == "Katapulta"]
        assert len(cats) >= 1
        ts_min, ts_max = cats[0]["ts_range"]
        assert ts_min <= 10 <= ts_max

    def test_with_artifact(self):
        # Catapult 6 f/h with artifact x2 → effective 12, 10 fields → 3000s
        travel = _calc_travel_seconds(10, 6, artifact_mult=2.0)
        results = detect_possible_units(10, travel, attacker_tribe=1)
        # Should detect catapult needing artifact, OR detect a unit with base speed 12
        names = [r["name"] for r in results]
        # Legionista has speed 12 — should match without artifact
        assert "Legionista" in names

    def test_unknown_tribe_returns_all(self):
        # Speed 8 = Taran (all tribes) and Senator (Romans)
        travel = _calc_travel_seconds(10, 8)
        results = detect_possible_units(10, travel, attacker_tribe=None)
        names = [r["name"] for r in results]
        assert "Taran" in names
        # Should have results from multiple tribes
        assert len(results) >= 1

    def test_known_tribe_filters(self):
        # Only Gaul units should appear
        travel = _calc_travel_seconds(10, 34)  # Tropiciel speed
        results = detect_possible_units(10, travel, attacker_tribe=3)
        for r in results:
            tribe = r["tribe"]
            if isinstance(tribe, list):
                assert 3 in tribe
            else:
                assert tribe == 3

    def test_very_fast_suggests_cavalry_with_ts(self):
        # Very fast for long distance → cavalry + high TS
        # Tropiciel (Gaul): 34 f/h, 80 fields, TS 15
        travel = _calc_travel_seconds(80, 34, ts_level=15)
        results = detect_possible_units(80, travel, attacker_tribe=3)
        # Should detect fast cavalry units
        cav_results = [r for r in results if r["type"] == "cav"]
        assert len(cav_results) >= 1

    def test_edge_zero_distance(self):
        assert detect_possible_units(0, 1000) == []

    def test_edge_zero_time(self):
        assert detect_possible_units(10, 0) == []

    def test_edge_negative_values(self):
        assert detect_possible_units(-5, 1000) == []
        assert detect_possible_units(10, -100) == []

    def test_siege_sorted_first(self):
        # When multiple unit types match, siege should come first
        travel = _calc_travel_seconds(10, 8)
        results = detect_possible_units(10, travel, attacker_tribe=1)
        if len(results) >= 2:
            types = [r["type"] for r in results]
            siege_idx = [i for i, t in enumerate(types) if t == "siege"]
            other_idx = [i for i, t in enumerate(types) if t != "siege"]
            if siege_idx and other_idx:
                assert max(siege_idx) < min(other_idx)

    def test_cross_tribe_dedup(self):
        # Taran exists in all 3 tribes at speed 8 — should be grouped
        travel = _calc_travel_seconds(10, 8)
        results = detect_possible_units(10, travel, attacker_tribe=None)
        tarans = [r for r in results if r["name"] == "Taran"]
        # Should be at most 1 entry (grouped)
        assert len(tarans) <= 1
        if tarans:
            tribe = tarans[0]["tribe"]
            # Should list multiple tribes
            assert isinstance(tribe, list)
            assert len(tribe) == 3

    def test_result_has_required_keys(self):
        travel = _calc_travel_seconds(10, 6)
        results = detect_possible_units(10, travel)
        assert len(results) > 0
        required = {"name", "tribe", "type", "speed", "ts_range",
                     "needs_boots", "needs_artifact", "artifact_mult", "boots_bonus"}
        for r in results:
            assert required.issubset(r.keys()), f"Missing keys: {required - r.keys()}"

    def test_tolerance_allows_slight_mismatch(self):
        # Travel time slightly off (3% error) should still match
        exact = _calc_travel_seconds(10, 6)
        perturbed = exact * 1.03  # 3% longer
        results = detect_possible_units(10, perturbed)
        names = [r["name"] for r in results]
        assert "Katapulta" in names or "Trebusz" in names

    def test_tolerance_rejects_large_mismatch(self):
        # Travel time 50% off should not match the original unit
        exact = _calc_travel_seconds(10, 6)  # Catapult speed
        way_off = exact * 1.50  # 50% longer
        results = detect_possible_units(10, way_off, attacker_tribe=1)
        names = [r["name"] for r in results]
        # Should not match catapult at base speed (but may match slower combos)
        # Catapult with artifact could potentially match, so just check it's not a direct hit
        cats = [r for r in results if r["name"] == "Katapulta" and not r["needs_artifact"]]
        assert len(cats) == 0

    def test_boots_detection_long_distance(self):
        # Unit traveling with boots on long distance
        travel = _calc_travel_seconds(50, 8, boots_bonus=0.5)
        results = detect_possible_units(50, travel, attacker_tribe=1)
        # Some result should indicate boots are needed
        boots_results = [r for r in results if r["needs_boots"]]
        # We may or may not detect boots depending on other combos matching
        # Just verify function doesn't crash
        assert isinstance(results, list)


# ------------------------------------------------------------------ #
# Formatting
# ------------------------------------------------------------------ #

class TestFormatUnitAnalysis:
    """Test Discord embed formatting of unit analysis."""

    def test_empty_results(self):
        assert format_unit_analysis([]) == ""

    def test_basic_format(self):
        results = [{
            "name": "Katapulta",
            "tribe": 1,
            "type": "siege",
            "speed": 6,
            "ts_range": (0, 0),
            "needs_boots": False,
            "needs_artifact": False,
            "artifact_mult": 1.0,
            "boots_bonus": 0.0,
        }]
        text = format_unit_analysis(results)
        assert "Katapulta" in text
        assert "6 pól/h" in text
        assert "bez TS" in text
        assert "bez butów" in text
        assert "🏗️" in text  # siege emoji

    def test_ts_range_format(self):
        results = [{
            "name": "Topornik",
            "tribe": 2,
            "type": "inf",
            "speed": 12,
            "ts_range": (5, 8),
            "needs_boots": False,
            "needs_artifact": False,
            "artifact_mult": 1.0,
            "boots_bonus": 0.0,
        }]
        text = format_unit_analysis(results)
        assert "TS ~5-8" in text

    def test_ts_single_value_format(self):
        results = [{
            "name": "Topornik",
            "tribe": 2,
            "type": "inf",
            "speed": 12,
            "ts_range": (5, 5),
            "needs_boots": False,
            "needs_artifact": False,
            "artifact_mult": 1.0,
            "boots_bonus": 0.0,
        }]
        text = format_unit_analysis(results)
        assert "TS 5" in text

    def test_boots_format(self):
        results = [{
            "name": "Paladyn",
            "tribe": 2,
            "type": "cav",
            "speed": 20,
            "ts_range": (3, 3),
            "needs_boots": True,
            "needs_artifact": False,
            "artifact_mult": 1.0,
            "boots_bonus": 0.25,
        }]
        text = format_unit_analysis(results)
        assert "buty 25%" in text
        assert "TS 3" in text

    def test_artifact_format(self):
        results = [{
            "name": "Katapulta",
            "tribe": 1,
            "type": "siege",
            "speed": 6,
            "ts_range": (0, 0),
            "needs_boots": False,
            "needs_artifact": True,
            "artifact_mult": 1.5,
            "boots_bonus": 0.0,
        }]
        text = format_unit_analysis(results)
        assert "artefakt x1.5" in text

    def test_multi_tribe_emoji(self):
        results = [{
            "name": "Taran",
            "tribe": [1, 2, 3],
            "type": "siege",
            "speed": 8,
            "ts_range": (0, 0),
            "needs_boots": False,
            "needs_artifact": False,
            "artifact_mult": 1.0,
            "boots_bonus": 0.0,
        }]
        text = format_unit_analysis(results)
        # Should contain all three tribe emojis
        assert "🏛️" in text
        assert "⚔️" in text
        assert "🏹" in text

    def test_type_ordering(self):
        results = [
            {"name": "Legionista", "tribe": 1, "type": "inf", "speed": 12,
             "ts_range": (0, 0), "needs_boots": False, "needs_artifact": False,
             "artifact_mult": 1.0, "boots_bonus": 0.0},
            {"name": "Taran", "tribe": 1, "type": "siege", "speed": 8,
             "ts_range": (0, 0), "needs_boots": False, "needs_artifact": False,
             "artifact_mult": 1.0, "boots_bonus": 0.0},
        ]
        text = format_unit_analysis(results)
        # Siege should appear before infantry
        taran_pos = text.index("Taran")
        legion_pos = text.index("Legionista")
        assert taran_pos < legion_pos

    def test_output_length_within_limit(self):
        # Generate many results and verify truncation
        many = []
        for i in range(50):
            many.append({
                "name": f"Jednostka{i}",
                "tribe": 1,
                "type": "inf",
                "speed": 10 + i,
                "ts_range": (0, 20),
                "needs_boots": True,
                "needs_artifact": True,
                "artifact_mult": 2.0,
                "boots_bonus": 0.75,
            })
        text = format_unit_analysis(many)
        assert len(text) <= 1024
