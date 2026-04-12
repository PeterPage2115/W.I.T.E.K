"""Tests for bot.tribes — unified tribe definitions."""

import pytest
from unittest.mock import patch

from bot.tribes import UnitDef, TribeDef, TRIBES


class TestUnitDef:
    def test_frozen_dataclass(self):
        u = UnitDef(name="Test", att=10, def_inf=20, def_cav=30,
                    speed=5, crop=1, unit_type="inf")
        assert u.name == "Test"
        assert u.speed_name == ""  # default empty
        assert u.aliases == ()     # default empty tuple

    def test_speed_name_override(self):
        u = UnitDef(name="Falangita", att=15, def_inf=40, def_cav=50,
                    speed=7, crop=1, unit_type="inf", speed_name="Falanga")
        assert u.speed_name == "Falanga"

    def test_immutable(self):
        u = UnitDef(name="Test", att=10, def_inf=20, def_cav=30,
                    speed=5, crop=1, unit_type="inf")
        with pytest.raises(AttributeError):
            u.att = 99


class TestTribeDef:
    def test_basic_structure(self):
        unit = UnitDef(name="Test", att=10, def_inf=20, def_cav=30,
                       speed=5, crop=1, unit_type="inf")
        tribe = TribeDef(tid=99, name_pl="Test", name_en="Test",
                         emoji="🧪", wall_type="Test Wall", units=(unit,),
                         icon_slug="test")
        assert tribe.tid == 99
        assert len(tribe.units) == 1
        assert tribe.settler_name == "Osadnik"
        assert tribe.chief_idx == 8
        assert tribe.icon_slug == "test"


class TestExistingTribes:
    """Verify Romans, Teutons, Gauls data matches corrected kirilloid values."""

    def test_tribes_registry_has_base_tribes(self):
        assert 1 in TRIBES  # Romans
        assert 2 in TRIBES  # Teutons
        assert 3 in TRIBES  # Gauls

    def test_romans_unit_count(self):
        assert len(TRIBES[1].units) == 10  # 9 combat + settler

    def test_romans_metadata(self):
        r = TRIBES[1]
        assert r.name_pl == "Rzymianie"
        assert r.name_en == "Romans"
        assert r.emoji == "🏛️"
        assert r.wall_type == "City Wall"

    # --- Bugfix verifications ---
    def test_bugfix_theutates_thunder_att(self):
        """Grom Teutatesa attack should be 100, not 90."""
        gauls = TRIBES[3]
        tt = gauls.units[3]  # index 3 = Theutates Thunder
        assert tt.name == "Grom Teutatesa"
        assert tt.att == 100

    def test_bugfix_gaul_ram_def_cav(self):
        """Gaul Ram def_cav should be 105, not 70."""
        gauls = TRIBES[3]
        ram = gauls.units[6]  # index 6 = Ram
        assert ram.name == "Taran"
        assert ram.def_cav == 105

    def test_bugfix_equites_legati_crop(self):
        """Equites Legati crop should be 2, not 3."""
        romans = TRIBES[1]
        el = romans.units[3]  # index 3 = Equites Legati
        assert el.name == "Equites Legati"
        assert el.crop == 2

    def test_bugfix_teuton_chief_crop(self):
        """Teuton Wódz crop should be 4, not 5."""
        teutons = TRIBES[2]
        chief = teutons.units[8]  # index 8 = chief
        assert chief.name == "Wódz"
        assert chief.crop == 4

    def test_bugfix_gaul_chief_crop(self):
        """Gaul Wódz crop should be 4, not 5."""
        gauls = TRIBES[3]
        chief = gauls.units[8]
        assert chief.name == "Wódz"
        assert chief.crop == 4

    def test_legionista_full_stats(self):
        """Spot-check full stats for one Roman unit."""
        leg = TRIBES[1].units[0]
        assert leg.name == "Legionista"
        assert leg.att == 40
        assert leg.def_inf == 35
        assert leg.def_cav == 50
        assert leg.speed == 6
        assert leg.crop == 1
        assert leg.unit_type == "inf"

    def test_speed_name_legacy(self):
        """Units with different UNIT_SPEEDS names must have speed_name set."""
        gauls = TRIBES[3]
        falangita = gauls.units[0]
        assert falangita.name == "Falangita"
        assert falangita.speed_name == "Falanga"

        tt = gauls.units[3]
        assert tt.name == "Grom Teutatesa"
        assert tt.speed_name == "Piorun Teutatesa"

        druid = gauls.units[4]
        assert druid.name == "Jeździec druidzki"
        assert druid.speed_name == "Druid"


class TestNewTribes:
    """Verify Egyptians, Huns, Vikings, Spartans data from kirilloid.ru."""

    def test_all_nine_tribes_present(self):
        for tid in [1, 2, 3, 6, 7, 8, 9]:
            assert tid in TRIBES, f"Missing tribe {tid}"

    # --- Egyptians (tid=6) ---
    def test_egyptians_metadata(self):
        t = TRIBES[6]
        assert t.name_pl == "Egipcjanie"
        assert t.emoji == "🏺"
        assert t.wall_type == "Stone Wall"

    def test_egyptians_unit_count(self):
        assert len(TRIBES[6].units) == 10

    def test_egyptians_resheph_chariot(self):
        rc = TRIBES[6].units[5]
        assert rc.name == "Resheph Chariot"
        assert rc.att == 110
        assert rc.def_inf == 120
        assert rc.def_cav == 150
        assert rc.speed == 10
        assert rc.crop == 3

    # --- Huns (tid=7) ---
    def test_huns_metadata(self):
        t = TRIBES[7]
        assert t.name_pl == "Hunowie"
        assert t.emoji == "🐎"

    def test_huns_mercenary_speed(self):
        """Mercenary speed=7 (official table, not kirilloid's 6)."""
        merc = TRIBES[7].units[0]
        assert merc.name == "Mercenary"
        assert merc.speed == 7

    def test_huns_marauder(self):
        mar = TRIBES[7].units[5]
        assert mar.name == "Marauder"
        assert mar.att == 180
        assert mar.speed == 14

    # --- Spartans (tid=8) ---
    def test_spartans_metadata(self):
        t = TRIBES[8]
        assert t.name_pl == "Spartanie"
        assert t.emoji == "🛡️"

    def test_spartans_corinthian_crusher(self):
        cc = TRIBES[8].units[5]
        assert cc.name == "Corinthian Crusher"
        assert cc.att == 195
        assert cc.speed == 9
        assert cc.crop == 3

    def test_spartans_four_infantry(self):
        """Spartans are unique: 4 infantry units."""
        s = TRIBES[8]
        inf_count = sum(1 for u in s.units if u.unit_type == "inf")
        assert inf_count == 4

    # --- Vikings (tid=9) ---
    def test_vikings_metadata(self):
        t = TRIBES[9]
        assert t.name_pl == "Wikingowie"
        assert t.emoji == "⛵"
        assert t.wall_type == "Barricade"

    def test_vikings_ram_crop(self):
        """Viking Ram crop=3 (official wiki, not kirilloid's 2)."""
        ram = TRIBES[9].units[6]
        assert ram.name == "Ram"
        assert ram.crop == 3

    def test_vikings_valkyrie(self):
        vb = TRIBES[9].units[5]
        assert vb.name == "Valkyrie's Blessing"
        assert vb.att == 160
        assert vb.speed == 9


class TestCrossTribeConsistency:
    """Cross-tribe data integrity checks."""

    def test_all_tribes_have_ram(self):
        for tid in [1, 2, 3, 6, 7, 8, 9]:
            rams = [u for u in TRIBES[tid].units if u.name in ("Taran", "Ram")]
            assert len(rams) == 1, f"Tribe {tid} missing ram"

    def test_all_tribes_have_catapult(self):
        for tid in [1, 2, 3, 6, 7, 8, 9]:
            cats = [u for u in TRIBES[tid].units
                    if u.name in ("Katapulta", "Katapulta ognista", "Trebusz", "Catapult")]
            assert len(cats) == 1, f"Tribe {tid} missing catapult"

    def test_all_tribes_have_10_units(self):
        for tid in [1, 2, 3, 6, 7, 8, 9]:
            assert len(TRIBES[tid].units) == 10, f"Tribe {tid} has {len(TRIBES[tid].units)} units"

    def test_all_chiefs_crop_4_or_5(self):
        for tid in [1, 2, 3, 6, 7, 8, 9]:
            tribe = TRIBES[tid]
            chief = tribe.units[tribe.chief_idx]
            assert chief.crop in (4, 5), f"Tribe {tid} chief crop={chief.crop}"
            assert chief.unit_type == "special"


class TestConfigHelpers:
    def test_get_speed_multiplier_default(self):
        from bot.tribes import get_speed_multiplier
        with patch("bot.tribes._load_server_profile", return_value={}):
            assert get_speed_multiplier() == 2  # fallback

    def test_get_speed_multiplier_from_config(self):
        from bot.tribes import get_speed_multiplier
        with patch("bot.tribes._load_server_profile",
                   return_value={"troop_speed_multiplier": 1}):
            assert get_speed_multiplier() == 1

    def test_get_available_tribes_default(self):
        from bot.tribes import get_available_tribes
        with patch("bot.tribes._load_server_profile", return_value={}):
            assert get_available_tribes() == [1, 2, 3]

    def test_get_available_tribes_from_config(self):
        from bot.tribes import get_available_tribes
        with patch("bot.tribes._load_server_profile",
                   return_value={"tribes": [1, 3, 6, 7, 8, 9]}):
            result = get_available_tribes()
            assert result == [1, 3, 6, 7, 8, 9]

    def test_get_available_tribes_filters_invalid(self):
        from bot.tribes import get_available_tribes
        with patch("bot.tribes._load_server_profile",
                   return_value={"tribes": [1, 2, 99, 3]}):
            result = get_available_tribes()
            assert 99 not in result
            assert 1 in result
