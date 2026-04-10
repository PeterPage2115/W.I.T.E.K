"""Tests for crop balance calculation."""

from bot.utils import calc_crop_consumption, HERO_CROP


class TestCropBalance:
    def test_simple_army(self):
        troops = {"Legionista": 100, "Imperians": 50}
        # Legionista=1crop, Imperians=1crop → 150
        assert calc_crop_consumption(troops) == 150

    def test_mixed_cavalry(self):
        troops = {"Equites Caesaris": 10, "Equites Imperatoris": 20}
        # EC=4crop*10=40, EI=3crop*20=60 → 100
        assert calc_crop_consumption(troops) == 100

    def test_hero_crop_constant(self):
        assert HERO_CROP == 6

    def test_new_tribe_units(self):
        troops = {"Marauder": 10, "Corinthian Crusher": 5}
        # Marauder=3crop*10=30, CC=3crop*5=15 → 45
        assert calc_crop_consumption(troops) == 45

    def test_empty_army(self):
        assert calc_crop_consumption({}) == 0
