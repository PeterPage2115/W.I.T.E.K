"""Testy dla tygodniowego digestu sojuszu — /tdigest (S5.7)."""

import pytest
from datetime import datetime, timedelta, timezone

from app import create_app
from app.database import db as _db
from app.models import AttackReport, Snapshot, Village

from bot.cogs.digest import (
    _gather_digest_data,
    _get_alliance_villages,
    _player_populations,
    _fmt_pop,
    build_digest_embed,
)


class TestConfig:
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
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield _db.session


class FakeBot:
    """Minimal bot stand-in for tests that only need flask_app."""

    def __init__(self, flask_app):
        self.flask_app = flask_app


def _make_village(map_id, snapshot_id, uid, player_name, aid, alliance_name,
                  population, x=0, y=0, vid=None, name="Wioska"):
    return Village(
        map_id=map_id,
        snapshot_id=snapshot_id,
        x=x, y=y, tid=1,
        vid=vid if vid is not None else map_id,
        name=name,
        uid=uid,
        player_name=player_name,
        aid=aid,
        alliance_name=alliance_name,
        population=population,
    )


def _make_snapshot(db_session, fetched_at, village_count=100):
    snap = Snapshot(fetched_at=fetched_at, village_count=village_count)
    db_session.add(snap)
    db_session.flush()
    return snap


# ------------------------------------------------------------------ #
# _fmt_pop — Polish thousands separator
# ------------------------------------------------------------------ #

class TestFmtPop:
    def test_small_number(self):
        assert _fmt_pop(123) == "123"

    def test_thousands(self):
        assert _fmt_pop(1234) == "1 234"

    def test_millions(self):
        assert _fmt_pop(1234567) == "1 234 567"

    def test_zero(self):
        assert _fmt_pop(0) == "0"

    def test_negative(self):
        assert _fmt_pop(-1500) == "-1 500"


# ------------------------------------------------------------------ #
# _player_populations
# ------------------------------------------------------------------ #

class TestPlayerPopulations:
    def test_single_village(self):
        villages = [{"uid": 10, "population": 500}]
        result = _player_populations(villages)
        assert result == {10: 500}

    def test_multiple_villages_same_player(self):
        villages = [
            {"uid": 10, "population": 500},
            {"uid": 10, "population": 300},
        ]
        result = _player_populations(villages)
        assert result == {10: 800}

    def test_filters_zero_uid(self):
        villages = [
            {"uid": 0, "population": 1000},
            {"uid": 10, "population": 500},
        ]
        result = _player_populations(villages)
        assert 0 not in result
        assert result == {10: 500}

    def test_filters_none_uid(self):
        villages = [{"uid": None, "population": 1000}]
        result = _player_populations(villages)
        assert result == {}


# ------------------------------------------------------------------ #
# _get_alliance_villages
# ------------------------------------------------------------------ #

class TestGetAllianceVillages:
    def test_returns_plain_dicts(self, db_session):
        now = datetime.now(timezone.utc)
        snap = _make_snapshot(db_session, now, village_count=5)
        db_session.add(_make_village(1, snap.id, 10, "Player1", 1, "UFOL", 500))
        db_session.add(_make_village(2, snap.id, 20, "Enemy", 99, "ENEMY", 300))
        db_session.commit()

        result = _get_alliance_villages(snap.id, [1])
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["player_name"] == "Player1"
        assert result[0]["population"] == 500

    def test_filters_uid_zero(self, db_session):
        now = datetime.now(timezone.utc)
        snap = _make_snapshot(db_session, now, village_count=5)
        db_session.add(_make_village(1, snap.id, 0, "Natatar", 1, "UFOL", 100))
        db_session.add(_make_village(2, snap.id, 10, "Player1", 1, "UFOL", 500))
        db_session.commit()

        result = _get_alliance_villages(snap.id, [1])
        assert len(result) == 1
        assert result[0]["uid"] == 10

    def test_multiple_alliances(self, db_session):
        now = datetime.now(timezone.utc)
        snap = _make_snapshot(db_session, now, village_count=5)
        db_session.add(_make_village(1, snap.id, 10, "P1", 1, "UFOL", 500))
        db_session.add(_make_village(2, snap.id, 20, "P2", 2, "UFOL2", 300))
        db_session.add(_make_village(3, snap.id, 30, "P3", 99, "ENEMY", 200))
        db_session.commit()

        result = _get_alliance_villages(snap.id, [1, 2])
        assert len(result) == 2


# ------------------------------------------------------------------ #
# _gather_digest_data
# ------------------------------------------------------------------ #

class TestGatherDigestData:
    def test_no_snapshots_returns_none(self, app, db_session):
        bot = FakeBot(app)
        result = _gather_digest_data(bot, 7)
        assert result is None

    def test_single_snapshot(self, app, db_session):
        bot = FakeBot(app)
        now = datetime.now(timezone.utc)
        snap = _make_snapshot(db_session, now, village_count=100)
        db_session.add(_make_village(1, snap.id, 10, "P1", 1, "UFOL", 500))
        db_session.commit()

        result = _gather_digest_data(bot, 7)
        assert result is not None
        assert result["single_snapshot"] is True
        assert result["pop_new"] == 500
        assert result["village_count_new"] == 1
        assert result["member_count_new"] == 1

    def test_population_change(self, app, db_session):
        bot = FakeBot(app)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=8)

        snap_old = _make_snapshot(db_session, old_time, village_count=100)
        snap_new = _make_snapshot(db_session, now, village_count=110)

        # Old state: player with 500 pop
        db_session.add(_make_village(1, snap_old.id, 10, "P1", 1, "UFOL", 500))
        # New state: player grew to 800 pop
        db_session.add(_make_village(1, snap_new.id, 10, "P1", 1, "UFOL", 800))
        db_session.commit()

        result = _gather_digest_data(bot, 7)
        assert result is not None
        assert result["single_snapshot"] is False
        assert result["pop_old"] == 500
        assert result["pop_new"] == 800
        assert result["pop_change"] == 300
        assert result["pop_change_pct"] == 60.0

    def test_top_growers(self, app, db_session):
        bot = FakeBot(app)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=8)

        snap_old = _make_snapshot(db_session, old_time, village_count=100)
        snap_new = _make_snapshot(db_session, now, village_count=110)

        # Three players with different growth
        for uid, name, old_pop, new_pop in [
            (10, "BigGrower", 500, 1000),
            (20, "MedGrower", 400, 600),
            (30, "SmallGrower", 300, 350),
        ]:
            db_session.add(_make_village(uid, snap_old.id, uid, name, 1, "UFOL", old_pop))
            db_session.add(_make_village(uid, snap_new.id, uid, name, 1, "UFOL", new_pop))
        db_session.commit()

        result = _gather_digest_data(bot, 7)
        growers = result["top_growers"]
        assert len(growers) == 3
        assert growers[0][0] == "BigGrower"
        assert growers[0][1] == 500  # +500
        assert growers[1][0] == "MedGrower"
        assert growers[1][1] == 200  # +200

    def test_top_decliners(self, app, db_session):
        bot = FakeBot(app)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=8)

        snap_old = _make_snapshot(db_session, old_time, village_count=100)
        snap_new = _make_snapshot(db_session, now, village_count=100)

        db_session.add(_make_village(10, snap_old.id, 10, "Loser", 1, "UFOL", 1000))
        db_session.add(_make_village(10, snap_new.id, 10, "Loser", 1, "UFOL", 700))
        db_session.commit()

        result = _gather_digest_data(bot, 7)
        decliners = result["top_decliners"]
        assert len(decliners) == 1
        assert decliners[0][0] == "Loser"
        assert decliners[0][1] == -300

    def test_member_changes(self, app, db_session):
        bot = FakeBot(app)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=8)

        snap_old = _make_snapshot(db_session, old_time, village_count=100)
        snap_new = _make_snapshot(db_session, now, village_count=100)

        # Old: P1 and P2 in alliance
        db_session.add(_make_village(1, snap_old.id, 10, "P1", 1, "UFOL", 500))
        db_session.add(_make_village(2, snap_old.id, 20, "P2", 1, "UFOL", 400))

        # New: P1 stayed, P2 left, P3 joined
        db_session.add(_make_village(1, snap_new.id, 10, "P1", 1, "UFOL", 600))
        db_session.add(_make_village(3, snap_new.id, 30, "P3", 1, "UFOL", 350))
        db_session.commit()

        result = _gather_digest_data(bot, 7)
        assert "P3" in result["new_members"]
        assert "P2" in result["lost_members"]
        assert result["member_count_old"] == 2
        assert result["member_count_new"] == 2

    def test_new_villages_detected(self, app, db_session):
        bot = FakeBot(app)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=8)

        snap_old = _make_snapshot(db_session, old_time, village_count=100)
        snap_new = _make_snapshot(db_session, now, village_count=110)

        # Old: one village
        db_session.add(_make_village(1, snap_old.id, 10, "P1", 1, "UFOL", 500, x=10, y=20))
        # New: same village + new village
        db_session.add(_make_village(1, snap_new.id, 10, "P1", 1, "UFOL", 600, x=10, y=20))
        db_session.add(_make_village(99, snap_new.id, 10, "P1", 1, "UFOL", 50, x=30, y=40, name="Nowa"))
        db_session.commit()

        result = _gather_digest_data(bot, 7)
        assert len(result["new_villages"]) == 1
        nv = result["new_villages"][0]
        assert nv["player_name"] == "P1"
        assert nv["x"] == 30
        assert nv["y"] == 40

    def test_attack_reports_counted(self, app, db_session):
        bot = FakeBot(app)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=8)

        snap_old = _make_snapshot(db_session, old_time, village_count=100)
        snap_new = _make_snapshot(db_session, now, village_count=100)
        db_session.add(_make_village(1, snap_old.id, 10, "P1", 1, "UFOL", 500))
        db_session.add(_make_village(1, snap_new.id, 10, "P1", 1, "UFOL", 600))

        # Add attack reports — 2 in range (1 resolved), 1 outside range
        db_session.add(AttackReport(
            reported_by_discord="123", status="reported",
            created_at=now - timedelta(days=3),
        ))
        db_session.add(AttackReport(
            reported_by_discord="456", status="resolved",
            created_at=now - timedelta(days=2),
        ))
        db_session.add(AttackReport(
            reported_by_discord="789", status="reported",
            created_at=now - timedelta(days=10),
        ))
        db_session.commit()

        result = _gather_digest_data(bot, 7)
        assert result["attacks_total"] == 2
        assert result["attacks_resolved"] == 1

    def test_no_alliances_configured(self, app, db_session):
        app.config["TRAVIAN_OUR_ALLIANCES"] = []
        bot = FakeBot(app)
        now = datetime.now(timezone.utc)
        _make_snapshot(db_session, now, village_count=100)
        db_session.commit()

        result = _gather_digest_data(bot, 7)
        assert result is None

    def test_multiple_alliances(self, app, db_session):
        app.config["TRAVIAN_OUR_ALLIANCES"] = [1, 2]
        bot = FakeBot(app)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=8)

        snap_old = _make_snapshot(db_session, old_time, village_count=100)
        snap_new = _make_snapshot(db_session, now, village_count=100)

        db_session.add(_make_village(1, snap_old.id, 10, "P1", 1, "UFOL", 500))
        db_session.add(_make_village(2, snap_old.id, 20, "P2", 2, "UFOL2", 300))
        db_session.add(_make_village(1, snap_new.id, 10, "P1", 1, "UFOL", 600))
        db_session.add(_make_village(2, snap_new.id, 20, "P2", 2, "UFOL2", 400))
        db_session.commit()

        result = _gather_digest_data(bot, 7)
        assert result["pop_old"] == 800
        assert result["pop_new"] == 1000
        assert "UFOL" in result["alliance_name"]
        assert "UFOL2" in result["alliance_name"]

    def test_player_with_multiple_villages(self, app, db_session):
        bot = FakeBot(app)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=8)

        snap_old = _make_snapshot(db_session, old_time, village_count=100)
        snap_new = _make_snapshot(db_session, now, village_count=100)

        # Player has 2 villages in old, 2 in new
        db_session.add(_make_village(1, snap_old.id, 10, "P1", 1, "UFOL", 300))
        db_session.add(_make_village(2, snap_old.id, 10, "P1", 1, "UFOL", 200))
        db_session.add(_make_village(1, snap_new.id, 10, "P1", 1, "UFOL", 400))
        db_session.add(_make_village(2, snap_new.id, 10, "P1", 1, "UFOL", 300))
        db_session.commit()

        result = _gather_digest_data(bot, 7)
        assert result["pop_old"] == 500
        assert result["pop_new"] == 700
        assert result["top_growers"][0][0] == "P1"
        assert result["top_growers"][0][1] == 200

    def test_snapshot_selection_picks_closest_to_cutoff(self, app, db_session):
        """Baseline should be the latest snapshot before the cutoff."""
        bot = FakeBot(app)
        now = datetime.now(timezone.utc)

        # 3 snapshots: 10 days ago, 6 days ago, now
        snap_10d = _make_snapshot(db_session, now - timedelta(days=10), village_count=100)
        snap_6d = _make_snapshot(db_session, now - timedelta(days=6), village_count=100)
        snap_now = _make_snapshot(db_session, now, village_count=100)

        for snap in [snap_10d, snap_6d, snap_now]:
            db_session.add(_make_village(1, snap.id, 10, "P1", 1, "UFOL", 500))
        db_session.commit()

        # Request 7 days — cutoff is 7 days ago
        # Latest snapshot before cutoff is snap_10d
        result = _gather_digest_data(bot, 7)
        assert result is not None
        assert result["single_snapshot"] is False


# ------------------------------------------------------------------ #
# Embed builder
# ------------------------------------------------------------------ #

class TestBuildDigestEmbed:
    def test_none_data_returns_error_embed(self):
        embed = build_digest_embed(None, 7)
        assert "brak danych" in embed.title.lower()
        assert embed.footer.text == "⚔️ WITEK — Na cześć H2P_Gucio"

    def test_single_snapshot_embed(self):
        data = {
            "single_snapshot": True,
            "alliance_name": "UFOL",
            "snapshot_date": "09.04.2026",
            "pop_new": 456789,
            "village_count_new": 120,
            "member_count_new": 45,
        }
        embed = build_digest_embed(data, 7)
        assert "Stan sojuszu" in embed.title
        assert "UFOL" in embed.title
        assert "456 789" in embed.description
        assert "120" in embed.description
        assert "45" in embed.description

    def test_full_digest_embed(self):
        data = {
            "single_snapshot": False,
            "period_days": 7,
            "old_date": "02.04.2026",
            "new_date": "09.04.2026",
            "alliance_name": "UFOLODZY",
            "pop_old": 456789,
            "pop_new": 478123,
            "pop_change": 21334,
            "pop_change_pct": 4.7,
            "village_count_old": 120,
            "village_count_new": 125,
            "member_count_old": 45,
            "member_count_new": 47,
            "top_growers": [("Gracz1", 5230), ("Gracz2", 3100)],
            "top_decliners": [("GraczX", -1200)],
            "new_members": ["Nowy1", "Nowy2"],
            "lost_members": ["Stary1"],
            "attacks_total": 12,
            "attacks_resolved": 8,
            "new_villages": [
                {"player_name": "Gracz1", "village_name": "Nowa", "x": 50, "y": 30},
            ],
            "new_villages_total": 1,
        }
        embed = build_digest_embed(data, 7)
        desc = embed.description

        # Title
        assert "UFOLODZY" in embed.title

        # Period
        assert "02.04.2026" in desc
        assert "09.04.2026" in desc

        # Population
        assert "456 789" in desc
        assert "478 123" in desc
        assert "+21 334" in desc
        assert "4.7%" in desc

        # Villages
        assert "120" in desc
        assert "125" in desc

        # Members
        assert "45" in desc
        assert "47" in desc

        # Top growers
        assert "Gracz1" in desc
        assert "+5 230" in desc

        # Decliners
        assert "GraczX" in desc
        assert "-1 200" in desc

        # Member changes
        assert "Nowy1" in desc
        assert "Stary1" in desc

        # Attacks
        assert "12 zgłoszonych" in desc
        assert "8 rozwiązanych" in desc

        # New villages
        assert "50|30" in desc

        # Footer
        assert embed.footer.text == "⚔️ WITEK — Na cześć H2P_Gucio"

    def test_no_attacks_section_when_zero(self):
        data = {
            "single_snapshot": False,
            "period_days": 7,
            "old_date": "02.04.2026",
            "new_date": "09.04.2026",
            "alliance_name": "UFOL",
            "pop_old": 1000,
            "pop_new": 1100,
            "pop_change": 100,
            "pop_change_pct": 10.0,
            "village_count_old": 10,
            "village_count_new": 11,
            "member_count_old": 5,
            "member_count_new": 5,
            "top_growers": [],
            "top_decliners": [],
            "new_members": [],
            "lost_members": [],
            "attacks_total": 0,
            "attacks_resolved": 0,
            "new_villages": [],
            "new_villages_total": 0,
        }
        embed = build_digest_embed(data, 7)
        assert "Ataki" not in embed.description

    def test_population_decrease_shows_correct_arrow(self):
        data = {
            "single_snapshot": False,
            "period_days": 7,
            "old_date": "01.01.2026",
            "new_date": "08.01.2026",
            "alliance_name": "UFOL",
            "pop_old": 1000,
            "pop_new": 900,
            "pop_change": -100,
            "pop_change_pct": -10.0,
            "village_count_old": 10,
            "village_count_new": 9,
            "member_count_old": 5,
            "member_count_new": 5,
            "top_growers": [],
            "top_decliners": [("Loser", -100)],
            "new_members": [],
            "lost_members": [],
            "attacks_total": 0,
            "attacks_resolved": 0,
            "new_villages": [],
            "new_villages_total": 0,
        }
        embed = build_digest_embed(data, 7)
        assert "📉" in embed.description
        assert "-10.0%" in embed.description
