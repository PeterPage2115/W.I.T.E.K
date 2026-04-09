"""Testy symulacji walki — UNIT_COMBAT, simulate_combat, parse_army_input."""

import pytest

from bot.utils import (
    COMBAT_BY_NAME,
    UNIT_COMBAT,
    WALL_BONUS,
    normalize_unit_name,
    parse_army_input,
    simulate_combat,
)


# ------------------------------------------------------------------ #
# UNIT_COMBAT data completeness
# ------------------------------------------------------------------ #

class TestUnitCombatData:
    """Verify UNIT_COMBAT dict is complete and well-formed."""

    def test_all_tribes_present(self):
        assert set(UNIT_COMBAT.keys()) == {1, 2, 3}

    @pytest.mark.parametrize("tribe_id", [1, 2, 3])
    def test_tribe_has_units(self, tribe_id):
        assert len(UNIT_COMBAT[tribe_id]) >= 9

    @pytest.mark.parametrize("tribe_id", [1, 2, 3])
    def test_unit_fields(self, tribe_id):
        for unit in UNIT_COMBAT[tribe_id]:
            assert "name" in unit
            assert "att" in unit
            assert "def_inf" in unit
            assert "def_cav" in unit
            assert "type" in unit
            assert unit["type"] in ("inf", "cav", "siege", "special")
            assert unit["att"] >= 0
            assert unit["def_inf"] >= 0
            assert unit["def_cav"] >= 0

    @pytest.mark.parametrize("tribe_id", [1, 2, 3])
    def test_has_infantry(self, tribe_id):
        types = [u["type"] for u in UNIT_COMBAT[tribe_id]]
        assert "inf" in types

    @pytest.mark.parametrize("tribe_id", [1, 2, 3])
    def test_has_cavalry(self, tribe_id):
        types = [u["type"] for u in UNIT_COMBAT[tribe_id]]
        assert "cav" in types

    @pytest.mark.parametrize("tribe_id", [1, 2, 3])
    def test_has_siege(self, tribe_id):
        types = [u["type"] for u in UNIT_COMBAT[tribe_id]]
        assert "siege" in types

    def test_all_combat_names_resolvable(self):
        """Every unit in UNIT_COMBAT must be resolvable via normalize_unit_name."""
        for tribe_id, units in UNIT_COMBAT.items():
            for unit in units:
                canonical = normalize_unit_name(unit["name"])
                assert canonical is not None, (
                    f"UNIT_COMBAT name '{unit['name']}' (tribe {tribe_id}) "
                    f"not found in _ALIASES"
                )


class TestCombatByName:
    """Verify COMBAT_BY_NAME flat lookup."""

    def test_imperians_lookup(self):
        stats = COMBAT_BY_NAME["Imperians"]
        assert stats["att"] == 70
        assert stats["def_inf"] == 40
        assert stats["def_cav"] == 25
        assert stats["type"] == "inf"
        assert stats["tribe"] == 1

    def test_falangita_lookup(self):
        stats = COMBAT_BY_NAME["Falangita"]
        assert stats["att"] == 15
        assert stats["def_inf"] == 40
        assert stats["def_cav"] == 50
        assert stats["tribe"] == 3

    def test_germanski_rycerz_lookup(self):
        stats = COMBAT_BY_NAME["Germański rycerz"]
        assert stats["att"] == 150
        assert stats["type"] == "cav"
        assert stats["tribe"] == 2

    def test_all_units_in_lookup(self):
        for tribe_id, units in UNIT_COMBAT.items():
            for unit in units:
                name = unit["name"]
                assert name in COMBAT_BY_NAME, f"{name} missing from COMBAT_BY_NAME"

    def test_taran_in_lookup(self):
        # Taran exists for multiple tribes; last one wins in flat dict
        assert "Taran" in COMBAT_BY_NAME


class TestWallBonus:
    """Verify wall bonus table."""

    def test_wall_bonus_length(self):
        assert len(WALL_BONUS) == 21  # levels 0-20

    def test_wall_level_0(self):
        assert WALL_BONUS[0] == 0

    def test_wall_level_10(self):
        assert WALL_BONUS[10] == 40

    def test_wall_level_20(self):
        assert WALL_BONUS[20] == 138

    def test_wall_bonus_increasing(self):
        for i in range(1, len(WALL_BONUS)):
            assert WALL_BONUS[i] > WALL_BONUS[i - 1]


# ------------------------------------------------------------------ #
# Alias resolution for combat units
# ------------------------------------------------------------------ #

class TestCombatAliases:
    """Verify that common unit aliases resolve to canonical names in COMBAT_BY_NAME."""

    def test_rycerz_teutonski_resolves(self):
        canonical = normalize_unit_name("Rycerz Teutoński")
        assert canonical == "Germański rycerz"
        assert canonical in COMBAT_BY_NAME

    def test_druid_resolves(self):
        canonical = normalize_unit_name("Druid")
        assert canonical == "Jeździec druidzki"
        assert canonical in COMBAT_BY_NAME

    def test_piorun_teutatesa_resolves(self):
        canonical = normalize_unit_name("Piorun Teutatesa")
        assert canonical == "Grom Teutatesa"
        assert canonical in COMBAT_BY_NAME

    def test_falanga_resolves(self):
        canonical = normalize_unit_name("Falanga")
        assert canonical == "Falangita"
        assert canonical in COMBAT_BY_NAME


# ------------------------------------------------------------------ #
# parse_army_input
# ------------------------------------------------------------------ #

class TestParseArmyInput:
    """Test parsing of user input for army composition."""

    def test_basic_colon_format(self):
        army, errors = parse_army_input("Imperians:500")
        assert army == {"Imperians": 500}
        assert errors == []

    def test_multiple_comma_separated(self):
        army, errors = parse_army_input("Imperians:500, Legionista:200")
        assert army == {"Imperians": 500, "Legionista": 200}
        assert errors == []

    def test_newline_separated(self):
        army, errors = parse_army_input("Imperians:500\nLegionista:200")
        assert army == {"Imperians": 500, "Legionista": 200}
        assert errors == []

    def test_space_separated_count(self):
        army, errors = parse_army_input("Imperians 500")
        assert army == {"Imperians": 500}
        assert errors == []

    def test_abbreviation_ec(self):
        army, errors = parse_army_input("EC:200")
        assert army == {"Equites Caesaris": 200}
        assert errors == []

    def test_abbreviation_imp(self):
        army, errors = parse_army_input("imp:100")
        assert army == {"Imperians": 100}
        assert errors == []

    def test_abbreviation_jd(self):
        army, errors = parse_army_input("JD:50")
        assert army == {"Jeździec druidzki": 50}
        assert errors == []

    def test_alias_rycerz(self):
        army, errors = parse_army_input("Rycerz Teutoński:100")
        assert army == {"Germański rycerz": 100}
        assert errors == []

    def test_unknown_unit(self):
        army, errors = parse_army_input("Smok:100")
        assert army == {}
        assert len(errors) == 1
        assert "Smok" in errors[0]

    def test_mixed_valid_invalid(self):
        army, errors = parse_army_input("Imperians:500, Smok:100, Legionista:200")
        assert army == {"Imperians": 500, "Legionista": 200}
        assert len(errors) == 1

    def test_duplicate_units_summed(self):
        army, errors = parse_army_input("Imperians:300, Imperians:200")
        assert army == {"Imperians": 500}
        assert errors == []

    def test_empty_input(self):
        army, errors = parse_army_input("")
        assert army == {}
        assert errors == []

    def test_bad_format(self):
        army, errors = parse_army_input("just some random text")
        assert army == {}
        assert len(errors) >= 1

    def test_equals_separator(self):
        army, errors = parse_army_input("Imperians=500")
        assert army == {"Imperians": 500}
        assert errors == []

    def test_zero_count_ignored(self):
        army, errors = parse_army_input("Imperians:0")
        assert army == {}
        assert errors == []


# ------------------------------------------------------------------ #
# simulate_combat
# ------------------------------------------------------------------ #

class TestSimulateCombat:
    """Test combat simulation with various scenarios."""

    def test_overwhelming_attacker(self):
        """Strong attacker vs weak defender → att wins, low att losses."""
        result = simulate_combat(
            {"Imperians": 1000},
            {"Falangita": 50},
        )
        assert result["result"] == "att_wins"
        assert result["att_losses_pct"] < 20
        assert result["def_losses_pct"] == 100
        # Most attackers survive
        assert result["att_remaining"]["Imperians"] > 800

    def test_overwhelming_defender(self):
        """Weak attacker vs strong defender → def wins, low def losses."""
        result = simulate_combat(
            {"Pałkarz": 50},
            {"Pretorianin": 1000},
        )
        assert result["result"] == "def_wins"
        assert result["att_losses_pct"] == 100
        assert result["def_losses_pct"] < 20
        assert result["att_remaining"]["Pałkarz"] == 0

    def test_even_match(self):
        """Same units same count → draw, both lose ~100%."""
        result = simulate_combat(
            {"Imperians": 500},
            {"Imperians": 500},
        )
        # With imp att=70, def_inf=40 per unit:
        # total_att = 500*70 = 35000
        # def_inf = 500*40 = 20000 → attacker wins
        assert result["result"] == "att_wins"

    def test_truly_even(self):
        """Construct exact equality: att == def → draw."""
        # Imperians: att=70, def_inf=40
        # We need att*count_att == def_inf*count_def
        # 70*400 = 28000, def_inf for Pretorianin = 65
        # 65 * 430 = 27950 ≈ not exact. Let me pick exact:
        # att power = 70 * 400 = 28000
        # def_inf of Legionista = 35 → 35 * 800 = 28000
        result = simulate_combat(
            {"Imperians": 400},
            {"Legionista": 800},
        )
        assert result["result"] == "draw"
        assert result["att_losses_pct"] == 100
        assert result["def_losses_pct"] == 100

    def test_wall_effect(self):
        """Wall increases defense → changes outcome."""
        attackers = {"Topornik": 500}
        defenders = {"Falangita": 300}

        result_no_wall = simulate_combat(attackers, defenders, wall_level=0)
        result_with_wall = simulate_combat(attackers, defenders, wall_level=20)

        # Wall should increase defense
        assert result_with_wall["effective_def"] > result_no_wall["effective_def"]
        # Attacker should lose more with wall
        assert result_with_wall["att_losses_pct"] >= result_no_wall["att_losses_pct"]

    def test_wall_level_clamped(self):
        """Wall level > 20 is clamped to 20."""
        result = simulate_combat(
            {"Imperians": 100},
            {"Falangita": 100},
            wall_level=25,
        )
        assert result["wall_bonus_pct"] == 138  # level 20

    def test_wall_level_negative_clamped(self):
        """Wall level < 0 is clamped to 0."""
        result = simulate_combat(
            {"Imperians": 100},
            {"Falangita": 100},
            wall_level=-5,
        )
        assert result["wall_bonus_pct"] == 0

    def test_empty_attackers(self):
        """No attackers → defender wins trivially."""
        result = simulate_combat(
            {},
            {"Falangita": 100},
        )
        assert result["result"] == "def_wins"
        assert result["att_losses_pct"] == 100
        assert result["def_losses_pct"] == 0

    def test_empty_defenders(self):
        """No defenders → attacker wins trivially."""
        result = simulate_combat(
            {"Imperians": 100},
            {},
        )
        assert result["result"] == "att_wins"
        assert result["att_losses_pct"] == 0
        assert result["def_losses_pct"] == 100

    def test_both_empty(self):
        """No units on either side → draw, no losses."""
        result = simulate_combat({}, {})
        assert result["result"] == "draw"
        assert result["att_losses_pct"] == 0
        assert result["def_losses_pct"] == 0

    def test_cavalry_attack_type(self):
        """Cavalry-dominant army should be typed as cavalry."""
        result = simulate_combat(
            {"Equites Caesaris": 500},  # pure cav, att=180 each
            {"Falangita": 300},
        )
        assert result["att_type"] == "cav"

    def test_infantry_attack_type(self):
        """Infantry-dominant army should be typed as infantry."""
        result = simulate_combat(
            {"Imperians": 500},  # pure inf
            {"Falangita": 300},
        )
        assert result["att_type"] == "inf"

    def test_mixed_army_attack_type(self):
        """Mixed army — type determined by majority of att points."""
        # Imperians: att=70 (inf), 300 units = 21000
        # EC: att=180 (cav), 200 units = 36000 → cav wins
        result = simulate_combat(
            {"Imperians": 300, "Equites Caesaris": 200},
            {"Falangita": 500},
        )
        assert result["att_type"] == "cav"

    def test_result_keys(self):
        """Check that result dict has all expected keys."""
        result = simulate_combat(
            {"Imperians": 100},
            {"Falangita": 100},
        )
        expected_keys = {
            "inf_att", "cav_att", "total_att",
            "def_power_inf", "def_power_cav",
            "def_power_inf_wall", "def_power_cav_wall",
            "wall_bonus_pct", "att_type", "effective_def",
            "att_losses_pct", "def_losses_pct", "result",
            "att_remaining", "def_remaining",
        }
        assert set(result.keys()) == expected_keys

    def test_remaining_floor(self):
        """Surviving troop count should be floor (int)."""
        result = simulate_combat(
            {"Imperians": 1000},
            {"Falangita": 100},
        )
        for count in result["att_remaining"].values():
            assert isinstance(count, int)
        for count in result["def_remaining"].values():
            assert isinstance(count, int)

    def test_defense_against_cavalry(self):
        """When attack is cavalry, defense should use def_cav."""
        # EC: att=180 (cav)
        result = simulate_combat(
            {"Equites Caesaris": 100},
            {"Falangita": 100},  # def_cav=50
        )
        assert result["att_type"] == "cav"
        assert result["effective_def"] == 100 * 50  # def_cav of Falangita

    def test_wall_10_bonus_40pct(self):
        """Wall level 10 gives 40% bonus."""
        result = simulate_combat(
            {"Imperians": 100},
            {"Falangita": 100},  # def_inf=40
            wall_level=10,
        )
        base_def = 100 * 40
        assert result["def_power_inf"] == base_def
        assert result["def_power_inf_wall"] == pytest.approx(base_def * 1.4)

    def test_scouts_zero_attack(self):
        """Units with 0 attack contribute nothing offensively."""
        result = simulate_combat(
            {"Equites Legati": 1000},  # att=0
            {"Falangita": 100},
        )
        assert result["total_att"] == 0
        assert result["result"] == "def_wins"
