"""Tests for battle report parser and troop tracking utilities."""

import pytest
from bot.cogs.defense import parse_battle_report, parse_troop_list, ReportParseError
from bot.utils import normalize_unit_name, calc_crop_consumption


# ------------------------------------------------------------------ #
# Unit name normalization
# ------------------------------------------------------------------ #
class TestNormalizeUnitName:
    def test_singular(self):
        assert normalize_unit_name("Pałkarz") == "Pałkarz"
        assert normalize_unit_name("Falangita") == "Falangita"

    def test_plural(self):
        assert normalize_unit_name("Falangi") == "Falangita"
        assert normalize_unit_name("Topornicy") == "Topornik"
        assert normalize_unit_name("Miecznicy") == "Miecznik"

    def test_case_insensitive(self):
        assert normalize_unit_name("pałkarz") == "Pałkarz"
        assert normalize_unit_name("FALANGI") == "Falangita"

    def test_unknown(self):
        assert normalize_unit_name("NieistniejącaJednostka") is None
        assert normalize_unit_name("") is None

    def test_hero(self):
        assert normalize_unit_name("Bohater") == "Bohater"

    def test_nature(self):
        assert normalize_unit_name("Szczury") == "Szczur"
        assert normalize_unit_name("Tygrys") == "Tygrys"

    def test_cavalry(self):
        assert normalize_unit_name("Gromy Teutatesa") == "Grom Teutatesa"
        assert normalize_unit_name("Tropiciele") == "Tropiciel"
        assert normalize_unit_name("Jeźdźcy druidzcy") == "Jeździec druidzki"


# ------------------------------------------------------------------ #
# Crop consumption
# ------------------------------------------------------------------ #
class TestCropConsumption:
    def test_basic(self):
        troops = {"Pałkarz": 80, "Topornik": 150}
        assert calc_crop_consumption(troops) == 80 + 150  # all 1 crop

    def test_mixed_cavalry(self):
        troops = {"Falangita": 100, "Grom Teutatesa": 50, "Haeduan": 30}
        # 100*1 + 50*2 + 30*3 = 100+100+90 = 290
        assert calc_crop_consumption(troops) == 290

    def test_with_hero(self):
        troops = {"Pałkarz": 10, "Bohater": 1}
        assert calc_crop_consumption(troops) == 10 + 6

    def test_siege(self):
        troops = {"Taran": 20, "Katapulta": 5}
        # 20*3 + 5*6 = 60+30 = 90
        assert calc_crop_consumption(troops) == 90

    def test_user_report_scenario(self):
        """Verify against user's actual report: 80 clubs + 150 axes after trapping."""
        troops = {"Pałkarz": 67, "Topornik": 128}
        assert calc_crop_consumption(troops) == 195


# ------------------------------------------------------------------ #
# Troop list parser
# ------------------------------------------------------------------ #
class TestParseToopList:
    def test_tab_separated(self):
        raw = "Falangi\t510\tFalangi\nMiecznicy\t200\tMiecznicy"
        troops = parse_troop_list(raw)
        assert troops == {"Falangita": 510, "Miecznik": 200}

    def test_two_column(self):
        raw = "Falangi\t300\nTopornicy\t150"
        troops = parse_troop_list(raw)
        assert troops == {"Falangita": 300, "Topornik": 150}

    def test_colon_format(self):
        raw = "Falangi: 100\nMiecznicy: 50"
        troops = parse_troop_list(raw)
        assert troops == {"Falangita": 100, "Miecznik": 50}

    def test_empty(self):
        assert parse_troop_list("") == {}
        assert parse_troop_list("   \n  \n") == {}

    def test_skips_unknown(self):
        raw = "Falangi\t100\tFalangi\nJakisNieznany\t50\tJakisNieznany"
        troops = parse_troop_list(raw)
        assert troops == {"Falangita": 100}

    def test_zero_count_skipped(self):
        raw = "Falangi\t0\tFalangi\nMiecznicy\t200\tMiecznicy"
        troops = parse_troop_list(raw)
        assert troops == {"Miecznik": 200}


# ------------------------------------------------------------------ #
# Battle report parser
# ------------------------------------------------------------------ #
SAMPLE_REPORT = """Kurwiszew grabi Kangaro
08.04.26, 21:11:02
Napastnik
[UFO] Bokiczownik z osady Kurwiszew
Pałkarz\tWłócznik\tTopornik\tZwiadowca\tPaladyn\tGermański rycerz\tTaran\tKatapulta\tWódz\tOsadnik
80\t0\t150\t0\t0\t0\t0\t0\t0\t0
0\t0\t0\t0\t0\t0\t0\t0\t0\t0
13\t0\t22\t0\t0\t0\t0\t0\t0\t0
zdobycz\t97980\t82241\t700\t4728/10420
Obrońca
[TT] Kangaro z osady Kangaro Village
Falangita\tMiecznik\tTropiciel\tGrom Teutatesa\tJeździec druidzki\tHaeduan\tTaran\tTrebusz\tWódz\tOsadnik
50\t0\t0\t0\t0\t0\t0\t0\t0\t0
50\t0\t0\t0\t0\t0\t0\t0\t0\t0
Statystyki
Napastnik\tObrońca
Siła w walce\t10623\t252"""


class TestParseBattleReport:
    def test_basic_parse(self):
        parsed = parse_battle_report(SAMPLE_REPORT)
        assert parsed["title"] == "Kurwiszew grabi Kangaro"
        assert parsed["date"] == "08.04.26, 21:11:02"

    def test_attacker(self):
        parsed = parse_battle_report(SAMPLE_REPORT)
        atk = parsed["attacker"]
        assert atk["alliance"] == "UFO"
        assert atk["player"] == "Bokiczownik"
        assert atk["village"] == "Kurwiszew"
        assert atk["troops"][0] == 80   # Pałkarz
        assert atk["troops"][2] == 150  # Topornik

    def test_attacker_trapped(self):
        parsed = parse_battle_report(SAMPLE_REPORT)
        atk = parsed["attacker"]
        assert atk["trapped"] is not None
        assert atk["trapped"][0] == 13  # Pałkarz trapped
        assert atk["trapped"][2] == 22  # Topornik trapped

    def test_defender(self):
        parsed = parse_battle_report(SAMPLE_REPORT)
        dfn = parsed["defender"]
        assert dfn["alliance"] == "TT"
        assert dfn["player"] == "Kangaro"
        assert dfn["village"] == "Kangaro Village"
        assert dfn["troops"][0] == 50   # Falangita
        assert dfn["losses"][0] == 50   # All killed

    def test_bounty(self):
        parsed = parse_battle_report(SAMPLE_REPORT)
        bounty = parsed["bounty"]
        assert bounty["wood"] == 97980
        assert bounty["clay"] == 82241
        assert bounty["iron"] == 700

    def test_stats(self):
        parsed = parse_battle_report(SAMPLE_REPORT)
        stats = parsed["stats"]
        assert stats["power_atk"] == 10623
        assert stats["power_def"] == 252

    def test_hash_deterministic(self):
        p1 = parse_battle_report(SAMPLE_REPORT)
        p2 = parse_battle_report(SAMPLE_REPORT)
        assert p1["raw_hash"] == p2["raw_hash"]

    def test_too_short_report(self):
        with pytest.raises(ReportParseError):
            parse_battle_report("too short")

    def test_no_attacker_section(self):
        with pytest.raises(ReportParseError):
            parse_battle_report("line1\nline2\nline3\nline4\nline5\nline6\nline7")

    def test_report_without_trapped(self):
        """Report without trapped row should still parse."""
        report = """Player1 atakuje Player2
01.01.26, 12:00:00
Napastnik
[A] Player1 z osady Village1
Pałkarz\tTopornik
100\t50
10\t5
Obrońca
[B] Player2 z osady Village2
Falangita\tMiecznik
200\t100
20\t10"""
        parsed = parse_battle_report(report)
        assert parsed["attacker"]["troops"] == [100, 50]
        assert parsed["attacker"]["losses"] == [10, 5]
        assert parsed["attacker"]["trapped"] is None


# ------------------------------------------------------------------ #
# Kill cost parsing
# ------------------------------------------------------------------ #
class TestKillCostParsing:
    """Test extraction of 'Koszt zabitych' from battle reports."""

    def test_parse_kill_cost_basic(self):
        report_text = (
            "Atakujący\tOrzel\n"
            "08.04.26, 21:11:02\n"
            "Napastnik\n"
            "[UFO] Orzel z osady Osada\n"
            "Pałkarz\n"
            "100\n"
            "50\n"
            "Obrońca\n"
            "[TT] Knight z osady Zamek\n"
            "Falangita\n"
            "200\n"
            "30\n"
            "Koszt zabitych\n"
            "Drewno\t5000\tDrewno\t3000\n"
            "Glina\t4000\tGlina\t2500\n"
            "Żelazo\t6000\tŻelazo\t4000\n"
            "Zboże\t2000\tZboże\t1500\n"
        )
        result = parse_battle_report(report_text)
        assert result["kill_cost_atk"] == {
            "Drewno": 5000, "Glina": 4000, "Żelazo": 6000, "Zboże": 2000
        }
        assert result["kill_cost_def"] == {
            "Drewno": 3000, "Glina": 2500, "Żelazo": 4000, "Zboże": 1500
        }

    def test_parse_no_kill_cost(self):
        report_text = (
            "Atakujący\tOrzel\n"
            "08.04.26, 21:11:02\n"
            "Napastnik\n"
            "[UFO] Orzel z osady Osada\n"
            "Pałkarz\n"
            "100\n"
            "50\n"
            "Obrońca\n"
            "[TT] Knight z osady Zamek\n"
            "Falangita\n"
            "200\n"
            "30\n"
        )
        result = parse_battle_report(report_text)
        assert result.get("kill_cost_atk") is None
        assert result.get("kill_cost_def") is None
