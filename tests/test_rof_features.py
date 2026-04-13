"""Tests for RoF (Return of the Founders) server feature support."""

import math

import pytest


class TestTribeChoices:
    """Verify _DEF_UNITS covers all 7 RoF tribes."""

    def test_def_units_has_all_tribes(self):
        from bot.cogs.attacks import Attacks
        expected = {1, 2, 3, 6, 7, 8, 9}
        assert set(Attacks._DEF_UNITS.keys()) == expected

    def test_def_units_value_shape(self):
        from bot.cogs.attacks import Attacks
        for tid, val in Attacks._DEF_UNITS.items():
            assert isinstance(val, tuple), f"tid={tid} should be a tuple"
            assert len(val) == 4, f"tid={tid} should have 4 elements"
            name_inf, speed_inf, name_cav, speed_cav = val
            assert isinstance(name_inf, str), f"tid={tid} inf name should be str"
            assert isinstance(speed_inf, int), f"tid={tid} inf speed should be int"
            assert isinstance(name_cav, str), f"tid={tid} cav name should be str"
            assert isinstance(speed_cav, int), f"tid={tid} cav speed should be int"


class TestFlatDistance:
    """Verify torus_distance wrap parameter works correctly."""

    def test_classic_pythagoras_wrap(self):
        from bot.utils import torus_distance
        assert torus_distance(0, 0, 3, 4, wrap=True) == 5.0

    def test_classic_pythagoras_flat(self):
        from bot.utils import torus_distance
        assert torus_distance(0, 0, 3, 4, wrap=False) == 5.0

    def test_edge_wrapping_vs_flat(self):
        from bot.utils import torus_distance
        # Wrapping: |(-200) - 200| = 400, min(400, 401-400) = 1 → dist=1.0
        d_wrap = torus_distance(-200, 0, 200, 0, map_size=401, wrap=True)
        assert d_wrap == pytest.approx(1.0)

        # Flat: no wrapping → 400.0
        d_flat = torus_distance(-200, 0, 200, 0, map_size=401, wrap=False)
        assert d_flat == pytest.approx(400.0)

    def test_diagonal_edge_wrapping_vs_flat(self):
        from bot.utils import torus_distance
        d_wrap = torus_distance(-200, -200, 200, 200, map_size=401, wrap=True)
        assert d_wrap == pytest.approx(math.sqrt(2), abs=0.01)

        d_flat = torus_distance(-200, -200, 200, 200, map_size=401, wrap=False)
        assert d_flat == pytest.approx(math.sqrt(400**2 + 400**2), abs=0.1)


class TestLegionnaireRebalance:
    """Verify apply_legionnaire_rebalance() logic."""

    def test_function_exists(self):
        from bot.tribes import apply_legionnaire_rebalance
        assert callable(apply_legionnaire_rebalance)

    def test_legionnaire_rebalance_applies(self, monkeypatch):
        from bot import tribes

        original = tribes.TRIBES[1]
        try:
            # Reset to original build first
            tribes.TRIBES.update(tribes._build_tribes())
            monkeypatch.setattr(
                tribes, '_load_server_profile',
                lambda: {"legionnaire_rebalanced": True},
            )
            tribes.apply_legionnaire_rebalance()

            leg = tribes.TRIBES[1].units[0]
            assert leg.def_cav == 70
            assert leg.speed == 7
        finally:
            tribes.TRIBES[1] = original

    def test_legionnaire_no_rebalance(self, monkeypatch):
        from bot import tribes

        original = tribes.TRIBES[1]
        try:
            tribes.TRIBES.update(tribes._build_tribes())
            monkeypatch.setattr(
                tribes, '_load_server_profile',
                lambda: {"legionnaire_rebalanced": False},
            )
            tribes.apply_legionnaire_rebalance()

            leg = tribes.TRIBES[1].units[0]
            assert leg.def_cav == 50
            assert leg.speed == 6
        finally:
            tribes.TRIBES[1] = original
