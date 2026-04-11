"""Testy dla komend ataku — /tatak, /tdodaj, /tataki, /trozwiaz."""

import asyncio
import json
from datetime import datetime, timezone

import pytest
from app import create_app
from app.database import db as _db
from app.models import (
    Alliance, AttackReport, DefenseThread, Player, Snapshot,
    TroopSupport, Village, VillageTroops,
)
from bot.cogs.attacks import _get_coord_lock, _get_thread_lock


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TRAVIAN_SERVER_URL = "https://test.travian.com"
    TRAVIAN_MAP_SIZE = 401
    TRAVIAN_OUR_ALLIANCES = [1, 2]
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


def _make_village(map_id, snapshot_id, x, y, uid, player_name,
                  aid=0, alliance_name="", population=100,
                  tid=1, vid=None, name="Wioska"):
    return Village(
        map_id=map_id, snapshot_id=snapshot_id,
        x=x, y=y, tid=tid, vid=vid or map_id, name=name,
        uid=uid, player_name=player_name,
        aid=aid, alliance_name=alliance_name,
        population=population,
    )


# ------------------------------------------------------------------ #
# Lock management
# ------------------------------------------------------------------ #


class TestThreadLocks:
    """Test per-thread lock management."""

    def test_same_thread_returns_same_lock(self):
        """Same thread_id should return the same asyncio.Lock instance."""
        lock1 = _get_thread_lock(12345)
        lock2 = _get_thread_lock(12345)
        assert lock1 is lock2

    def test_different_threads_return_different_locks(self):
        """Different thread_ids should return different locks."""
        lock1 = _get_thread_lock(111)
        lock2 = _get_thread_lock(222)
        assert lock1 is not lock2

    def test_lock_is_asyncio_lock(self):
        """Should return an asyncio.Lock."""
        lock = _get_thread_lock(999)
        assert isinstance(lock, asyncio.Lock)


class TestCoordLocks:
    """Test per-coordinate lock management."""

    def test_same_coords_return_same_lock(self):
        """Same (x,y) should return the same lock."""
        lock1 = _get_coord_lock(10, 20)
        lock2 = _get_coord_lock(10, 20)
        assert lock1 is lock2

    def test_different_coords_return_different_locks(self):
        """Different coordinates should return different locks."""
        lock1 = _get_coord_lock(10, 20)
        lock2 = _get_coord_lock(30, 40)
        assert lock1 is not lock2

    def test_coord_lock_is_asyncio_lock(self):
        """Should return an asyncio.Lock."""
        lock = _get_coord_lock(5, 5)
        assert isinstance(lock, asyncio.Lock)


# ------------------------------------------------------------------ #
# AttackReport model — creation & queries
# ------------------------------------------------------------------ #


class TestAttackReportModel:
    """Test AttackReport creation and querying."""

    def test_create_attack_report(self, db_session):
        """Should create an attack report with all fields."""
        report = AttackReport(
            reported_by_discord="123456789",
            reported_by_name="testuser",
            attacker_name="Attacker",
            attacker_alliance="EVIL",
            attacker_x=50, attacker_y=60,
            defender_name="Defender",
            defender_village="Village1",
            defender_x=10, defender_y=20,
            attack_time="14:30",
            attack_unix=1700000000,
            wall_level=15,
            crop_amount=5000,
            crop_production=200,
            notes="Duża armia",
            status="reported",
        )
        db_session.add(report)
        db_session.commit()

        saved = AttackReport.query.get(report.id)
        assert saved.attacker_name == "Attacker"
        assert saved.defender_x == 10
        assert saved.defender_y == 20
        assert saved.wall_level == 15
        assert saved.status == "reported"

    def test_default_status_is_reported(self, db_session):
        """Default status should be 'reported'."""
        report = AttackReport(
            reported_by_discord="111",
            defender_x=0, defender_y=0,
        )
        db_session.add(report)
        db_session.commit()

        assert report.status == "reported"

    def test_query_active_attacks(self, db_session):
        """Should filter active (non-resolved) attacks."""
        db_session.add_all([
            AttackReport(
                reported_by_discord="111",
                attacker_name="A1",
                defender_x=10, defender_y=10,
                attack_unix=1700000100,
                status="reported",
            ),
            AttackReport(
                reported_by_discord="111",
                attacker_name="A2",
                defender_x=20, defender_y=20,
                attack_unix=1700000200,
                status="resolved",
            ),
            AttackReport(
                reported_by_discord="111",
                attacker_name="A3",
                defender_x=30, defender_y=30,
                attack_unix=1700000300,
                status="defending",
            ),
        ])
        db_session.commit()

        active = AttackReport.query.filter(
            AttackReport.status != "resolved"
        ).all()
        names = {a.attacker_name for a in active}
        assert "A1" in names
        assert "A3" in names
        assert "A2" not in names

    def test_query_attacks_ordered_by_time(self, db_session):
        """Attacks should be orderable by attack_unix ascending."""
        db_session.add_all([
            AttackReport(reported_by_discord="1", attacker_name="Late",
                         defender_x=0, defender_y=0, attack_unix=1700000300),
            AttackReport(reported_by_discord="1", attacker_name="Early",
                         defender_x=0, defender_y=0, attack_unix=1700000100),
            AttackReport(reported_by_discord="1", attacker_name="Mid",
                         defender_x=0, defender_y=0, attack_unix=1700000200),
        ])
        db_session.commit()

        ordered = AttackReport.query.order_by(AttackReport.attack_unix.asc()).all()
        assert [a.attacker_name for a in ordered] == ["Early", "Mid", "Late"]


# ------------------------------------------------------------------ #
# DefenseThread model
# ------------------------------------------------------------------ #


class TestDefenseThreadModel:
    """Test DefenseThread creation and queries."""

    def test_create_defense_thread(self, db_session):
        """Should create a defense thread record."""
        dt = DefenseThread(
            forum_thread_id=9876543210,
            defender_x=10, defender_y=20,
            defender_village="Capital",
            defender_player="Defender",
            wall_level=18,
            crop_amount=8000,
            crop_production=500,
            status="active",
        )
        db_session.add(dt)
        db_session.commit()

        saved = DefenseThread.query.filter_by(forum_thread_id=9876543210).first()
        assert saved is not None
        assert saved.defender_village == "Capital"
        assert saved.wall_level == 18
        assert saved.status == "active"

    def test_find_active_thread_by_coords(self, db_session):
        """Should find active defense thread by coordinates."""
        db_session.add_all([
            DefenseThread(forum_thread_id=100, defender_x=10, defender_y=20, status="active"),
            DefenseThread(forum_thread_id=200, defender_x=10, defender_y=20, status="resolved"),
            DefenseThread(forum_thread_id=300, defender_x=30, defender_y=40, status="active"),
        ])
        db_session.commit()

        dt = DefenseThread.query.filter_by(
            defender_x=10, defender_y=20, status="active",
        ).first()
        assert dt is not None
        assert dt.forum_thread_id == 100

    def test_no_active_thread(self, db_session):
        """When all threads are resolved, should return None."""
        db_session.add(DefenseThread(
            forum_thread_id=100, defender_x=10, defender_y=20, status="resolved",
        ))
        db_session.commit()

        dt = DefenseThread.query.filter_by(
            defender_x=10, defender_y=20, status="active",
        ).first()
        assert dt is None


# ------------------------------------------------------------------ #
# Resolve logic
# ------------------------------------------------------------------ #


class TestResolveAttack:
    """Test attack resolution logic."""

    def test_resolve_single_report(self, db_session):
        """Resolving a single report should set status='resolved'."""
        report = AttackReport(
            reported_by_discord="111",
            defender_x=0, defender_y=0,
            status="reported",
        )
        db_session.add(report)
        db_session.commit()

        report.status = "resolved"
        report.resolved_at = datetime.now(timezone.utc)
        db_session.commit()

        assert AttackReport.query.get(report.id).status == "resolved"
        assert AttackReport.query.get(report.id).resolved_at is not None

    def test_resolve_closes_all_linked_reports(self, db_session):
        """Resolving one report should close all reports linked to the same thread."""
        thread_id = 555555
        db_session.add_all([
            AttackReport(reported_by_discord="1", defender_x=10, defender_y=20,
                         forum_thread_id=thread_id, status="reported"),
            AttackReport(reported_by_discord="2", defender_x=10, defender_y=20,
                         forum_thread_id=thread_id, status="defending"),
            AttackReport(reported_by_discord="3", defender_x=10, defender_y=20,
                         forum_thread_id=thread_id, status="resolved"),  # already resolved
        ])
        db_session.commit()

        now = datetime.now(timezone.utc)
        linked = AttackReport.query.filter(
            AttackReport.forum_thread_id == thread_id,
            AttackReport.status != "resolved",
        ).all()
        for r in linked:
            r.status = "resolved"
            r.resolved_at = now
        db_session.commit()

        all_reports = AttackReport.query.filter_by(forum_thread_id=thread_id).all()
        assert all(r.status == "resolved" for r in all_reports)

    def test_resolve_updates_defense_thread(self, db_session):
        """Resolving should also set DefenseThread status to 'resolved'."""
        thread_id = 666666
        db_session.add(DefenseThread(
            forum_thread_id=thread_id, defender_x=10, defender_y=20, status="active",
        ))
        db_session.add(AttackReport(
            reported_by_discord="1", defender_x=10, defender_y=20,
            forum_thread_id=thread_id, status="reported",
        ))
        db_session.commit()

        dt = DefenseThread.query.filter_by(forum_thread_id=thread_id).first()
        dt.status = "resolved"
        db_session.commit()

        assert DefenseThread.query.filter_by(forum_thread_id=thread_id).first().status == "resolved"

    def test_resolve_nonexistent_report(self, app):
        """Resolving non-existent report should find nothing."""
        with app.app_context():
            report = AttackReport.query.get(9999)
            assert report is None


# ------------------------------------------------------------------ #
# Enrichment — village/player lookup from snapshot
# ------------------------------------------------------------------ #


class TestEnrichment:
    """Test auto-enrichment of attack reports from map data."""

    def test_lookup_defender_village(self, db_session):
        """Should find defender village by coordinates in latest snapshot."""
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=1)
        db_session.add(snap)
        db_session.commit()

        db_session.add(_make_village(1, snap.id, 10, 20, 100, "Defender",
                                     name="Capital", population=500))
        db_session.commit()

        v = Village.query.filter_by(snapshot_id=snap.id, x=10, y=20).first()
        assert v is not None
        assert v.name == "Capital"
        assert v.player_name == "Defender"

    def test_lookup_attacker_village(self, db_session):
        """Should find attacker source village by coordinates."""
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=1)
        db_session.add(snap)
        db_session.commit()

        db_session.add(_make_village(1, snap.id, 50, 60, 200, "EvilPlayer",
                                     name="Warcamp", population=800))
        db_session.commit()

        v = Village.query.filter_by(snapshot_id=snap.id, x=50, y=60).first()
        assert v is not None
        assert v.player_name == "EvilPlayer"

    def test_lookup_player_by_name(self, db_session):
        """Should find attacker Player record by name."""
        db_session.add(Player(uid=200, name="EvilPlayer", tid=2,
                              aid=5, alliance_name="EVIL",
                              total_pop=3000, village_count=5))
        db_session.commit()

        p = Player.query.filter(Player.name == "EvilPlayer").first()
        assert p is not None
        assert p.alliance_name == "EVIL"
        assert p.tid == 2

    def test_enrichment_missing_village(self, db_session):
        """When village not in snapshot, should get None."""
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=0)
        db_session.add(snap)
        db_session.commit()

        v = Village.query.filter_by(snapshot_id=snap.id, x=99, y=99).first()
        assert v is None

    def test_enrichment_missing_player(self, app):
        """When player name not found, should get None."""
        with app.app_context():
            p = Player.query.filter(Player.name == "NonExistent").first()
            assert p is None


# ------------------------------------------------------------------ #
# VillageTroops & TroopSupport models
# ------------------------------------------------------------------ #


class TestDefenseModels:
    """Test garrison and support troop models."""

    def test_village_troops_creation(self, db_session):
        """Should store village garrison troops as JSON."""
        troops = {"Pretorianin": 500, "Legionista": 200}
        vt = VillageTroops(
            village_x=10, village_y=20,
            village_name="Capital",
            player_discord_id="111",
            player_name="Defender",
            troops=json.dumps(troops),
            crop_consumption=350,
        )
        db_session.add(vt)
        db_session.commit()

        saved = VillageTroops.query.first()
        assert saved.village_x == 10
        parsed = json.loads(saved.troops)
        assert parsed["Pretorianin"] == 500

    def test_troop_support_creation(self, db_session):
        """Should store support troop records."""
        troops = {"Falanga": 300}
        ts = TroopSupport(
            from_x=5, from_y=5, to_x=10, to_y=20,
            player_discord_id="222",
            player_name="Helper",
            troops=json.dumps(troops),
            crop_consumption=150,
            forum_thread_id=123456,
            status="in_transit",
        )
        db_session.add(ts)
        db_session.commit()

        saved = TroopSupport.query.first()
        assert saved.from_x == 5
        assert saved.to_x == 10
        assert saved.status == "in_transit"

    def test_query_garrison_for_village(self, db_session):
        """Should find garrison troops by village coordinates."""
        db_session.add_all([
            VillageTroops(village_x=10, village_y=20, player_discord_id="1",
                          troops='{"A": 100}'),
            VillageTroops(village_x=30, village_y=40, player_discord_id="2",
                          troops='{"B": 200}'),
        ])
        db_session.commit()

        garrison = VillageTroops.query.filter_by(village_x=10, village_y=20).first()
        assert garrison is not None
        assert json.loads(garrison.troops)["A"] == 100

    def test_query_support_for_thread(self, db_session):
        """Should find support troops by forum thread ID."""
        db_session.add_all([
            TroopSupport(from_x=1, from_y=1, to_x=10, to_y=20,
                         player_discord_id="1", troops='{"X": 50}',
                         forum_thread_id=111),
            TroopSupport(from_x=2, from_y=2, to_x=10, to_y=20,
                         player_discord_id="2", troops='{"Y": 75}',
                         forum_thread_id=111),
            TroopSupport(from_x=3, from_y=3, to_x=50, to_y=50,
                         player_discord_id="3", troops='{"Z": 25}',
                         forum_thread_id=222),
        ])
        db_session.commit()

        supports = TroopSupport.query.filter_by(forum_thread_id=111).all()
        assert len(supports) == 2


# ------------------------------------------------------------------ #
# Attack report linking to threads
# ------------------------------------------------------------------ #


class TestAttackThreadLinking:
    """Test linking attack reports to defense threads."""

    def test_link_report_to_existing_thread(self, db_session):
        """Attack report should be linked to existing active defense thread."""
        dt = DefenseThread(
            forum_thread_id=777, defender_x=10, defender_y=20, status="active",
        )
        db_session.add(dt)
        db_session.commit()

        report = AttackReport(
            reported_by_discord="111",
            defender_x=10, defender_y=20,
            status="reported",
        )
        db_session.add(report)
        db_session.commit()

        # Simulate linking
        active_dt = DefenseThread.query.filter_by(
            defender_x=10, defender_y=20, status="active",
        ).first()
        report.forum_thread_id = active_dt.forum_thread_id
        db_session.commit()

        assert report.forum_thread_id == 777

    def test_no_thread_for_unmatched_coords(self, db_session):
        """No thread should be found for different coordinates."""
        db_session.add(DefenseThread(
            forum_thread_id=777, defender_x=10, defender_y=20, status="active",
        ))
        db_session.commit()

        dt = DefenseThread.query.filter_by(
            defender_x=99, defender_y=99, status="active",
        ).first()
        assert dt is None

    def test_multiple_reports_same_thread(self, db_session):
        """Multiple attack reports can be linked to the same thread."""
        thread_id = 888
        db_session.add(DefenseThread(
            forum_thread_id=thread_id, defender_x=10, defender_y=20, status="active",
        ))
        db_session.add_all([
            AttackReport(reported_by_discord="1", defender_x=10, defender_y=20,
                         forum_thread_id=thread_id, status="reported",
                         attacker_name="A1", attack_unix=1700000100),
            AttackReport(reported_by_discord="2", defender_x=10, defender_y=20,
                         forum_thread_id=thread_id, status="reported",
                         attacker_name="A2", attack_unix=1700000200),
            AttackReport(reported_by_discord="3", defender_x=10, defender_y=20,
                         forum_thread_id=thread_id, status="reported",
                         attacker_name="A3", attack_unix=1700000300),
        ])
        db_session.commit()

        reports = AttackReport.query.filter_by(forum_thread_id=thread_id).all()
        assert len(reports) == 3
