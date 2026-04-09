"""Tests for smart_parse_report() multi-strategy parser and web report routes."""

import json
import pytest

from bot.cogs.defense import (
    parse_battle_report,
    smart_parse_report,
    _parse_condensed_report,
    _normalize_tabular_whitespace,
    ReportParseError,
)
from app import create_app
from app.database import db as _db
from app.models import BattleReport, Snapshot


# ------------------------------------------------------------------ #
# Sample reports for testing
# ------------------------------------------------------------------ #

# Standard tab-separated (same format as existing tests)
TAB_REPORT = """Player1 grabi Player2
08.04.26, 21:11:02
Napastnik
[UFO] Player1 z osady Wioska1
Pałkarz\tTopornik\tZwiadowca
80\t150\t0
5\t10\t0
Obrońca
[TT] Player2 z osady Wioska2
Falangita\tMiecznik
50\t30
50\t30
Statystyki
Napastnik\tObrońca
Siła w walce\t5000\t1200"""

# Space-separated (clipboard paste — 2+ spaces between columns)
SPACE_REPORT = """Player1 grabi Player2
08.04.26, 21:11:02
Napastnik
[UFO] Player1 z osady Wioska1
Pałkarz  Topornik  Zwiadowca
80  150  0
5  10  0
Obrońca
[TT] Player2 z osady Wioska2
Falangita  Miecznik
50  30
50  30
Statystyki
Napastnik  Obrońca
Siła w walce  5000  1200"""

# Mixed whitespace (tabs and spaces)
MIXED_REPORT = """Player1 grabi Player2
08.04.26, 21:11:02
Napastnik
[UFO] Player1 z osady Wioska1
Pałkarz\t  Topornik   Zwiadowca
80\t  150   0
5   10\t0
Obrońca
[TT] Player2 z osady Wioska2
Falangita   Miecznik
50   30
50   30"""

# Condensed format
CONDENSED_REPORT = """Player1 grabi Player2
Napastnik: Player1 [UFO] z wioski Wioska1
Pałkarz: 80, Topornik: 150
Straty: Pałkarz: 5, Topornik: 10
Obrońca: Player2 [TT] z wioski Wioska2
Falangita: 50, Miecznik: 30
Straty: Falangita: 50, Miecznik: 30"""

# Condensed without defender
CONDENSED_ATK_ONLY = """Raport szpiegowski
Napastnik: Szpieg [SPY] z wioski Baza
Zwiadowca: 100"""


# ------------------------------------------------------------------ #
# smart_parse_report tests
# ------------------------------------------------------------------ #
class TestSmartParseReport:
    """Test multi-strategy parsing wrapper."""

    def test_tab_separated_passthrough(self):
        """Strategy 1: standard tab-separated works directly."""
        parsed = smart_parse_report(TAB_REPORT)
        assert parsed["attacker"]["player"] == "Player1"
        assert parsed["attacker"]["alliance"] == "UFO"
        assert parsed["defender"]["player"] == "Player2"
        assert parsed["attacker"]["troops"][0] == 80  # Pałkarz
        assert parsed["attacker"]["troops"][1] == 150  # Topornik

    def test_space_separated(self):
        """Strategy 2: space-separated gets normalized to tabs."""
        parsed = smart_parse_report(SPACE_REPORT)
        assert parsed["attacker"]["player"] == "Player1"
        assert parsed["attacker"]["troops"][0] == 80
        assert parsed["attacker"]["troops"][1] == 150
        assert parsed["defender"]["troops"][0] == 50

    def test_mixed_whitespace(self):
        """Strategy 2: mixed tabs/spaces normalized."""
        parsed = smart_parse_report(MIXED_REPORT)
        assert parsed["attacker"]["player"] == "Player1"
        assert parsed["attacker"]["troops"][0] == 80
        assert parsed["attacker"]["troops"][1] == 150

    def test_condensed_format(self):
        """Strategy 3: condensed key:value format."""
        parsed = smart_parse_report(CONDENSED_REPORT)
        assert parsed["attacker"]["player"] == "Player1"
        assert parsed["attacker"]["alliance"] == "UFO"
        assert parsed["defender"]["player"] == "Player2"
        assert "Pałkarz" in parsed["attacker"]["unit_names"]
        assert "Topornik" in parsed["attacker"]["unit_names"]

    def test_all_strategies_fail(self):
        """All strategies fail → ReportParseError with count."""
        with pytest.raises(ReportParseError, match="Próbowano"):
            smart_parse_report("this is not a report at all")

    def test_hash_from_original(self):
        """Hash is always computed from original raw text."""
        parsed_tab = smart_parse_report(TAB_REPORT)
        parsed_space = smart_parse_report(SPACE_REPORT)
        # Different inputs should produce different hashes
        assert parsed_tab["raw_hash"] != parsed_space["raw_hash"]

    def test_hash_deterministic(self):
        """Same input always produces same hash."""
        h1 = smart_parse_report(TAB_REPORT)["raw_hash"]
        h2 = smart_parse_report(TAB_REPORT)["raw_hash"]
        assert h1 == h2

    def test_fallback_chain(self):
        """If strategy 1 fails but strategy 2 succeeds, we get a result."""
        # Space-separated should fail strategy 1 but succeed strategy 2
        parsed = smart_parse_report(SPACE_REPORT)
        assert parsed is not None
        assert "attacker" in parsed

    def test_stats_preserved(self):
        """Stats section is preserved through smart parser."""
        parsed = smart_parse_report(TAB_REPORT)
        assert parsed["stats"]["power_atk"] == 5000
        assert parsed["stats"]["power_def"] == 1200

    def test_bounty_preserved(self):
        """Bounty section is preserved when available."""
        report_with_bounty = """Player1 grabi Player2
Napastnik
[A] Player1 z osady V1
Pałkarz\tTopornik
80\t150
5\t10
0\t0
zdobycz\t1000\t2000\t3000\t500/5000
Obrońca
[B] Player2 z osady V2
Falangita\tMiecznik
50\t30
50\t30"""
        parsed = smart_parse_report(report_with_bounty)
        assert parsed["bounty"] is not None
        assert parsed["bounty"]["wood"] == 1000


# ------------------------------------------------------------------ #
# _parse_condensed_report tests
# ------------------------------------------------------------------ #
class TestParseCondensedReport:
    """Test condensed format parser."""

    def test_basic(self):
        parsed = _parse_condensed_report(CONDENSED_REPORT)
        atk = parsed["attacker"]
        assert atk["alliance"] == "UFO"
        assert atk["player"] == "Player1"
        assert atk["village"] == "Wioska1"
        assert "Pałkarz" in atk["unit_names"]
        idx = atk["unit_names"].index("Pałkarz")
        assert atk["troops"][idx] == 80
        assert atk["losses"][idx] == 5

    def test_defender(self):
        parsed = _parse_condensed_report(CONDENSED_REPORT)
        dfn = parsed["defender"]
        assert dfn["alliance"] == "TT"
        assert dfn["player"] == "Player2"
        assert "Falangita" in dfn["unit_names"]
        idx = dfn["unit_names"].index("Falangita")
        assert dfn["troops"][idx] == 50
        assert dfn["losses"][idx] == 50

    def test_no_defender(self):
        parsed = _parse_condensed_report(CONDENSED_ATK_ONLY)
        assert parsed["defender"] is None
        assert parsed["attacker"]["alliance"] == "SPY"

    def test_too_short(self):
        with pytest.raises(ReportParseError):
            _parse_condensed_report("just one line")

    def test_no_attacker_section(self):
        with pytest.raises(ReportParseError, match="Napastnik"):
            _parse_condensed_report("line1\nline2\nline3")

    def test_no_units_found(self):
        with pytest.raises(ReportParseError, match="jednostek"):
            _parse_condensed_report("Title\nNapastnik: Player\nno units here")

    def test_result_structure(self):
        """Condensed parser returns same top-level keys as standard parser."""
        parsed = _parse_condensed_report(CONDENSED_REPORT)
        assert "title" in parsed
        assert "attacker" in parsed
        assert "defender" in parsed
        assert "bounty" in parsed
        assert "stats" in parsed
        assert "raw_hash" in parsed

    def test_side_structure(self):
        """Each side has required keys for downstream processing."""
        parsed = _parse_condensed_report(CONDENSED_REPORT)
        for side_key in ("attacker", "defender"):
            side = parsed[side_key]
            assert "alliance" in side
            assert "player" in side
            assert "village" in side
            assert "unit_names" in side
            assert "troops" in side
            assert "losses" in side
            assert "trapped" in side
            assert len(side["troops"]) == len(side["unit_names"])
            assert len(side["losses"]) == len(side["unit_names"])

    def test_village_with_coords(self):
        """Village name extracted even when coords are present."""
        report = """Title
Napastnik: Gracz [S] z wioski Moja Wioska (100|50)
Pałkarz: 80"""
        parsed = _parse_condensed_report(report)
        assert parsed["attacker"]["village"] == "Moja Wioska"
        assert parsed["attacker"]["player"] == "Gracz"

    def test_osady_variant(self):
        """'z osady' works too (alternative to 'z wioski')."""
        report = """Title
Napastnik: Gracz z osady Forteca
Pałkarz: 80"""
        parsed = _parse_condensed_report(report)
        assert parsed["attacker"]["village"] == "Forteca"


# ------------------------------------------------------------------ #
# _normalize_tabular_whitespace tests
# ------------------------------------------------------------------ #
class TestNormalizeWhitespace:
    def test_preserves_single_spaces(self):
        """Single spaces in village/player names are preserved."""
        text = "Grom Teutatesa\t100\t200"
        assert _normalize_tabular_whitespace(text) == text

    def test_collapses_multiple_spaces_in_data_rows(self):
        """Multiple spaces between data columns become tabs."""
        text = "Pałkarz  Topornik  Zwiadowca"
        result = _normalize_tabular_whitespace(text)
        assert "\t" in result
        parts = result.split("\t")
        assert "Pałkarz" in parts
        assert "Topornik" in parts

    def test_preserves_header_lines(self):
        """Non-tabular header lines are left intact."""
        text = "Player1 grabi Player2"
        assert _normalize_tabular_whitespace(text) == text

    def test_mixed_content(self):
        """Multi-line with both header and data rows."""
        text = "Title line\n[UFO] Player z osady Village\n80  150  0"
        result = _normalize_tabular_whitespace(text)
        lines = result.split("\n")
        assert lines[0] == "Title line"
        assert lines[1] == "[UFO] Player z osady Village"
        # Number line should be normalized
        assert "80" in lines[2]
        assert "150" in lines[2]


# ------------------------------------------------------------------ #
# Web route tests
# ------------------------------------------------------------------ #
class _TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TRAVIAN_SERVER_URL = "https://test.travian.com"
    TRAVIAN_MAP_SIZE = 401
    TRAVIAN_OUR_ALLIANCES = [1]
    POP_DROP_THRESHOLD = 15
    NEW_VILLAGE_RADIUS = 30
    DISCORD_TOKEN = ""
    DISCORD_GUILD_ID = None
    DISCORD_ALERTS_CHANNEL_ID = None
    DISCORD_DEFENSE_FORUM_ID = None
    DISCORD_DEF_ROLE_ID = None
    ALLIANCE_PASSWORD = ""


@pytest.fixture
def app():
    app = create_app(_TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_report(app):
    """Create a sample BattleReport in the database."""
    with app.app_context():
        report = BattleReport(
            attacker_name="Attacker1",
            attacker_alliance="UFO",
            attacker_village="AttackVillage",
            attacker_troops=json.dumps({"Pałkarz": 80, "Topornik": 150}),
            attacker_losses=json.dumps({"Pałkarz": 5, "Topornik": 10}),
            defender_name="Defender1",
            defender_alliance="TT",
            defender_village="DefendVillage",
            defender_troops=json.dumps({"Falangita": 50}),
            defender_losses=json.dumps({"Falangita": 50}),
            bounty=json.dumps({"wood": 1000, "clay": 2000, "iron": 3000, "crop": "500/5000"}),
            battle_power_atk=5000,
            battle_power_def=1200,
            raw_text="abc123",
            reported_by_discord="12345",
        )
        _db.session.add(report)
        _db.session.commit()
        yield report.id


@pytest.fixture
def manual_report(app):
    """Create a manual BattleReport (is_manual=True) in the database."""
    with app.app_context():
        report = BattleReport(
            attacker_name="ManualAttacker",
            defender_name="ManualDefender",
            result="wygrana_obrony",
            is_manual=True,
            raw_text="Ręcznie dodany raport",
            reported_by_discord="99999",
        )
        _db.session.add(report)
        _db.session.commit()
        yield report.id


class TestReportListRoute:
    def test_empty_list(self, client):
        """Empty report list returns 200."""
        resp = client.get("/reports")
        assert resp.status_code == 200
        assert "Brak raportów" in resp.data.decode()

    def test_list_with_data(self, client, sample_report):
        """Report list shows report data."""
        resp = client.get("/reports")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Attacker1" in html
        assert "Defender1" in html

    def test_filter_by_player(self, client, sample_report):
        """Filter by player name works."""
        resp = client.get("/reports?player=Attacker1")
        assert resp.status_code == 200
        assert "Attacker1" in resp.data.decode()

    def test_filter_no_results(self, client, sample_report):
        """Filter with no matches shows empty state."""
        resp = client.get("/reports?player=NonExistent")
        assert resp.status_code == 200
        assert "Brak raportów" in resp.data.decode()

    def test_mixed_auto_and_manual(self, client, sample_report, manual_report):
        """Both auto-parsed and manual reports appear in the list."""
        resp = client.get("/reports")
        html = resp.data.decode()
        assert "Attacker1" in html
        assert "ManualAttacker" in html


class TestReportDetailRoute:
    def test_detail_page(self, client, sample_report):
        """Detail page for existing report returns 200."""
        resp = client.get(f"/reports/{sample_report}")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Attacker1" in html
        assert "Defender1" in html
        assert "Pałkarz" in html

    def test_detail_404(self, client):
        """Non-existent report returns 404."""
        resp = client.get("/reports/99999")
        assert resp.status_code == 404

    def test_detail_shows_bounty(self, client, sample_report):
        """Detail page shows bounty data."""
        resp = client.get(f"/reports/{sample_report}")
        html = resp.data.decode()
        assert "1,000" in html or "1000" in html  # wood value

    def test_detail_shows_battle_power(self, client, sample_report):
        """Detail page shows battle power."""
        resp = client.get(f"/reports/{sample_report}")
        html = resp.data.decode()
        assert "5,000" in html or "5000" in html  # power_atk

    def test_manual_report_detail(self, client, manual_report):
        """Manual report detail page works."""
        resp = client.get(f"/reports/{manual_report}")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "ManualAttacker" in html
        assert "Ręczny" in html


class TestNavLink:
    def test_reports_nav_visible(self, client):
        """Reports nav link is visible on the page."""
        resp = client.get("/reports")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'href="/reports"' in html
        assert "📜 Raporty" in html
