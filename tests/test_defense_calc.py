"""Tests for defense calculator — how many defenders needed to survive."""
import pytest
from bot.utils import calc_needed_defense


class TestCalcNeededDefense:
    def test_pure_infantry_attack(self):
        """Imperians (70 att each) × 1000 = 70,000 inf att.
        Pretorianin: 65 def_inf. Need ~1077."""
        result = calc_needed_defense(
            attackers={"Imperians": 1000},
            defender_unit="Pretorianin",
            wall_level=0,
        )
        assert result is not None
        assert "count" in result
        assert 900 < result["count"] < 1200

    def test_pure_cavalry_attack(self):
        """EC (180 att) × 500 = 90,000 cav att.
        Włócznik: 40 def_cav → need would be huge; 60 def_cav. Need ~1500."""
        result = calc_needed_defense(
            attackers={"Equites Caesaris": 500},
            defender_unit="Włócznik",
            wall_level=0,
        )
        assert result is not None
        assert result["count"] > 0

    def test_wall_reduces_needed_defense(self):
        no_wall = calc_needed_defense({"Imperians": 1000}, "Pretorianin", 0)
        with_wall = calc_needed_defense({"Imperians": 1000}, "Pretorianin", 20)
        assert with_wall["count"] < no_wall["count"]

    def test_mixed_attack(self):
        """Mixed inf+cav: majority type determines which def stat."""
        result = calc_needed_defense(
            {"Imperians": 500, "Equites Imperatoris": 500},
            "Pretorianin", 0,
        )
        assert result is not None
        assert result["att_type"] in ("inf", "cav")

    def test_unknown_unit_returns_none(self):
        result = calc_needed_defense({"Imperians": 100}, "NieistniejącaJednostka", 0)
        assert result is None

    def test_empty_attackers(self):
        result = calc_needed_defense({}, "Pretorianin", 0)
        assert result is not None
        assert result["count"] == 0

    def test_result_includes_crop_cost(self):
        result = calc_needed_defense({"Imperians": 1000}, "Pretorianin", 0)
        assert "crop_per_hour" in result
        assert result["crop_per_hour"] > 0
