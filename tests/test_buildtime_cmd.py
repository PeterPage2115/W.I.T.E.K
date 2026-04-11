"""Testy dla komendy /tbuildtime — kalkulator czasu treningu."""

import pytest

from bot.cogs.economy import (
    TRAINING_COSTS,
    calc_training_time,
    format_duration,
)


class TestCalcTrainingTime:
    """Test calc_training_time at various building levels."""

    def test_level_1(self):
        # base_time / (1 + 1*0.1) = 1600 / 1.1
        result = calc_training_time(1600, 1)
        assert result == pytest.approx(1600 / 1.1)

    def test_level_10(self):
        result = calc_training_time(1600, 10)
        assert result == pytest.approx(1600 / 2.0)

    def test_level_20(self):
        result = calc_training_time(1600, 20)
        assert result == pytest.approx(1600 / 3.0)


class TestFormatDuration:
    """Test format_duration helper."""

    def test_seconds_only(self):
        assert format_duration(45) == "45s"

    def test_minutes_and_seconds(self):
        assert format_duration(90) == "1m 30s"

    def test_hours_minutes_seconds(self):
        assert format_duration(3661) == "1h 1m 1s"

    def test_exact_hours(self):
        assert format_duration(7200) == "2h"

    def test_zero(self):
        assert format_duration(0) == "0s"


class TestBuildtimeLogic:
    """Test the calculation logic used by /tbuildtime."""

    def test_legionista_level1_qty1(self):
        cost = TRAINING_COSTS["Legionista"]
        time_per = calc_training_time(cost["time"], 1)
        total = time_per * 1
        assert total == pytest.approx(1600 / 1.1)

    def test_legionista_level10_qty5(self):
        cost = TRAINING_COSTS["Legionista"]
        time_per = calc_training_time(cost["time"], 10)
        total = time_per * 5
        assert total == pytest.approx(1600 / 2.0 * 5)

    def test_total_resources_multiplied(self):
        cost = TRAINING_COSTS["Legionista"]
        qty = 10
        assert cost["lumber"] * qty == 1200
        assert cost["clay"] * qty == 1000
        assert cost["iron"] * qty == 1500
        assert cost["crop"] * qty == 300

    def test_all_units_have_required_fields(self):
        required = {"lumber", "clay", "iron", "crop", "time", "building"}
        for name, data in TRAINING_COSTS.items():
            assert required.issubset(data.keys()), f"{name} missing fields"

    def test_building_types(self):
        valid_buildings = {"Koszary", "Stajnia"}
        for name, data in TRAINING_COSTS.items():
            assert data["building"] in valid_buildings, f"{name} has unknown building"

    def test_unknown_unit(self):
        assert TRAINING_COSTS.get("Nieistniejąca") is None
