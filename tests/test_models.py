"""Dedicated unit tests for SQLAlchemy models in app/models.py."""

import json
import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.database import db as _db
from app.models import (
    Snapshot, Village, Player, Alliance, User, AttackReport,
    DefenseThread, VillageTroops, TroopSupport, BattleReport,
    Alert, MonitorSettings, PersonalAlert, DiplomaticRelation,
    SpyReport, NightWatchSetting,
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
def db(app):
    """Shortcut to the db session within app context."""
    with app.app_context():
        yield _db


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

class TestSnapshot:
    def test_create_and_read(self, db):
        s = Snapshot(village_count=100)
        db.session.add(s)
        db.session.commit()
        assert s.id is not None
        assert s.village_count == 100

    def test_default_fetched_at(self, db):
        s = Snapshot(village_count=1)
        db.session.add(s)
        db.session.commit()
        assert s.fetched_at is not None
        assert isinstance(s.fetched_at, datetime)

    def test_delete(self, db):
        s = Snapshot(village_count=5)
        db.session.add(s)
        db.session.commit()
        db.session.delete(s)
        db.session.commit()
        assert Snapshot.query.count() == 0


# ---------------------------------------------------------------------------
# Village
# ---------------------------------------------------------------------------

class TestVillage:
    def test_create_with_snapshot_relationship(self, db):
        s = Snapshot(village_count=1)
        db.session.add(s)
        db.session.commit()
        v = Village(map_id=1, snapshot_id=s.id, x=10, y=-20,
                    tid=3, vid=100, name="TestVillage",
                    uid=5, player_name="TestPlayer", aid=1,
                    alliance_name="TestAlliance", population=500)
        db.session.add(v)
        db.session.commit()
        assert v.snapshot.id == s.id
        assert s.villages.count() == 1

    def test_missing_required_x(self, db):
        s = Snapshot(village_count=1)
        db.session.add(s)
        db.session.commit()
        v = Village(map_id=1, snapshot_id=s.id, y=0)
        db.session.add(v)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_composite_primary_key(self, db):
        s = Snapshot(village_count=2)
        db.session.add(s)
        db.session.commit()
        v1 = Village(map_id=1, snapshot_id=s.id, x=0, y=0)
        v2 = Village(map_id=2, snapshot_id=s.id, x=1, y=1)
        db.session.add_all([v1, v2])
        db.session.commit()
        assert Village.query.filter_by(snapshot_id=s.id).count() == 2


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

class TestPlayer:
    def test_create_and_defaults(self, db):
        p = Player(uid=1, name="Hero")
        db.session.add(p)
        db.session.commit()
        assert p.total_pop == 0
        assert p.village_count == 0
        assert p.first_seen_at is not None

    def test_missing_name_raises(self, db):
        p = Player(uid=2)
        db.session.add(p)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_update_population(self, db):
        p = Player(uid=3, name="Grower")
        db.session.add(p)
        db.session.commit()
        p.total_pop = 5000
        db.session.commit()
        fetched = Player.query.get(3)
        assert fetched.total_pop == 5000


# ---------------------------------------------------------------------------
# Alliance
# ---------------------------------------------------------------------------

class TestAlliance:
    def test_create_and_defaults(self, db):
        a = Alliance(aid=10, name="UFOLODZY")
        db.session.add(a)
        db.session.commit()
        assert a.member_count == 0
        assert a.total_pop == 0
        assert a.first_seen_at is not None

    def test_missing_name_raises(self, db):
        a = Alliance(aid=11)
        db.session.add(a)
        with pytest.raises(IntegrityError):
            db.session.commit()


# ---------------------------------------------------------------------------
# User (Discord OAuth)
# ---------------------------------------------------------------------------

class TestUser:
    def test_create_and_defaults(self, db):
        u = User(discord_id=123456789012345678, discord_name="Gucio#1234")
        db.session.add(u)
        db.session.commit()
        assert u.role == "member"
        assert u.travian_uid is None
        assert u.linked_at is not None
        assert u.created_at is not None

    def test_discord_id_unique(self, db):
        u1 = User(discord_id=111, discord_name="A")
        u2 = User(discord_id=111, discord_name="B")
        db.session.add(u1)
        db.session.commit()
        db.session.add(u2)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_discord_id_required(self, db):
        u = User(discord_name="NoDiscord")
        db.session.add(u)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_link_travian_player(self, db):
        u = User(discord_id=222, discord_name="Linker")
        db.session.add(u)
        db.session.commit()
        u.travian_uid = 42
        u.travian_name = "TravianHero"
        db.session.commit()
        fetched = User.query.filter_by(discord_id=222).first()
        assert fetched.travian_uid == 42
        assert fetched.travian_name == "TravianHero"


# ---------------------------------------------------------------------------
# AttackReport — status transitions
# ---------------------------------------------------------------------------

class TestAttackReport:
    def test_create_and_defaults(self, db):
        ar = AttackReport(reported_by_discord="123", defender_x=10, defender_y=20)
        db.session.add(ar)
        db.session.commit()
        assert ar.status == "reported"
        assert ar.auto_resolved is False
        assert ar.created_at is not None

    def test_status_transition(self, db):
        ar = AttackReport(reported_by_discord="456")
        db.session.add(ar)
        db.session.commit()
        ar.status = "defending"
        db.session.commit()
        assert ar.status == "defending"
        ar.status = "resolved"
        ar.resolved_at = datetime.now(timezone.utc)
        db.session.commit()
        assert ar.status == "resolved"
        assert ar.resolved_at is not None

    def test_required_reported_by(self, db):
        ar = AttackReport()
        db.session.add(ar)
        with pytest.raises(IntegrityError):
            db.session.commit()


# ---------------------------------------------------------------------------
# Alert — notified flag
# ---------------------------------------------------------------------------

class TestAlert:
    def test_create_and_defaults(self, db):
        s = Snapshot(village_count=10)
        db.session.add(s)
        db.session.commit()
        a = Alert(snapshot_id=s.id, alert_type="pop_drop",
                  data=json.dumps({"player": "X", "drop": 20}))
        db.session.add(a)
        db.session.commit()
        assert a.notified is False
        assert a.created_at is not None

    def test_mark_notified(self, db):
        a = Alert(alert_type="new_village", data="{}")
        db.session.add(a)
        db.session.commit()
        a.notified = True
        db.session.commit()
        assert Alert.query.get(a.id).notified is True

    def test_snapshot_fk(self, db):
        s = Snapshot(village_count=1)
        db.session.add(s)
        db.session.commit()
        a = Alert(snapshot_id=s.id, alert_type="alliance_change")
        db.session.add(a)
        db.session.commit()
        assert a.snapshot_id == s.id


# ---------------------------------------------------------------------------
# DiplomaticRelation — active/inactive, relation types
# ---------------------------------------------------------------------------

class TestDiplomaticRelation:
    def test_create_and_defaults(self, db):
        dr = DiplomaticRelation(
            relation_type="ally",
            target_alliance_id=99,
            target_alliance_name="Friends",
        )
        db.session.add(dr)
        db.session.commit()
        assert dr.active is True
        assert dr.created_at is not None

    def test_deactivate(self, db):
        dr = DiplomaticRelation(relation_type="nap", target_alliance_id=50)
        db.session.add(dr)
        db.session.commit()
        dr.active = False
        db.session.commit()
        assert DiplomaticRelation.query.get(dr.id).active is False

    def test_relation_types(self, db):
        for rtype in ("ally", "pact", "nap", "war"):
            dr = DiplomaticRelation(relation_type=rtype, target_alliance_id=rtype.__hash__() % 1000)
            db.session.add(dr)
        db.session.commit()
        assert DiplomaticRelation.query.count() == 4

    def test_required_relation_type(self, db):
        dr = DiplomaticRelation(target_alliance_id=1)
        db.session.add(dr)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_required_target_alliance_id(self, db):
        dr = DiplomaticRelation(relation_type="war")
        db.session.add(dr)
        with pytest.raises(IntegrityError):
            db.session.commit()


# ---------------------------------------------------------------------------
# SpyReport — JSON fields, coordinate bounds
# ---------------------------------------------------------------------------

class TestSpyReport:
    def test_create_with_json_fields(self, db):
        troops = {"Legionnaire": 100, "Praetorian": 50}
        buildings = {"wall": 10, "earth_wall": 0}
        sr = SpyReport(
            spy_type="both",
            target_x=-50, target_y=150,
            troops=json.dumps(troops),
            defense_buildings=json.dumps(buildings),
            resources_lumber=1000, resources_clay=2000,
            resources_iron=1500, resources_crop=3000,
        )
        db.session.add(sr)
        db.session.commit()
        fetched = SpyReport.query.get(sr.id)
        assert json.loads(fetched.troops) == troops
        assert json.loads(fetched.defense_buildings) == buildings

    def test_required_spy_type(self, db):
        sr = SpyReport(target_x=0, target_y=0)
        db.session.add(sr)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_required_coordinates(self, db):
        sr = SpyReport(spy_type="resources")
        db.session.add(sr)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_negative_coordinates(self, db):
        sr = SpyReport(spy_type="troops", target_x=-200, target_y=-200)
        db.session.add(sr)
        db.session.commit()
        assert sr.target_x == -200
        assert sr.target_y == -200

    def test_empty_json_fields(self, db):
        sr = SpyReport(spy_type="resources", target_x=0, target_y=0,
                       troops=json.dumps({}), defense_buildings=json.dumps({}))
        db.session.add(sr)
        db.session.commit()
        assert json.loads(sr.troops) == {}

    def test_snapshot_fk_relationship(self, db):
        s = Snapshot(village_count=1)
        db.session.add(s)
        db.session.commit()
        sr = SpyReport(spy_type="both", target_x=10, target_y=20, snapshot_id=s.id)
        db.session.add(sr)
        db.session.commit()
        assert sr.snapshot_id == s.id


# ---------------------------------------------------------------------------
# NightWatchSetting — time window, defaults
# ---------------------------------------------------------------------------

class TestNightWatchSetting:
    def test_create_and_defaults(self, db):
        nw = NightWatchSetting(discord_id=999)
        db.session.add(nw)
        db.session.commit()
        assert nw.enabled is True
        assert nw.start_hour == 22
        assert nw.start_minute == 0
        assert nw.end_hour == 6
        assert nw.end_minute == 0
        assert nw.dm_count == 0

    def test_custom_time_window(self, db):
        nw = NightWatchSetting(discord_id=888, start_hour=23, start_minute=30,
                               end_hour=5, end_minute=45)
        db.session.add(nw)
        db.session.commit()
        assert nw.start_hour == 23
        assert nw.end_minute == 45

    def test_discord_id_unique(self, db):
        nw1 = NightWatchSetting(discord_id=777)
        nw2 = NightWatchSetting(discord_id=777)
        db.session.add(nw1)
        db.session.commit()
        db.session.add(nw2)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_discord_id_required(self, db):
        nw = NightWatchSetting()
        db.session.add(nw)
        with pytest.raises(IntegrityError):
            db.session.commit()


# ---------------------------------------------------------------------------
# DefenseThread
# ---------------------------------------------------------------------------

class TestDefenseThread:
    def test_create_and_defaults(self, db):
        dt = DefenseThread(forum_thread_id=12345678, defender_x=0, defender_y=0)
        db.session.add(dt)
        db.session.commit()
        assert dt.status == "active"
        assert dt.created_at is not None

    def test_resolve(self, db):
        dt = DefenseThread(forum_thread_id=11111, defender_x=5, defender_y=5)
        db.session.add(dt)
        db.session.commit()
        dt.status = "resolved"
        db.session.commit()
        assert DefenseThread.query.get(dt.id).status == "resolved"


# ---------------------------------------------------------------------------
# MonitorSettings
# ---------------------------------------------------------------------------

class TestMonitorSettings:
    def test_create_and_defaults(self, db):
        ms = MonitorSettings(discord_id=55555)
        db.session.add(ms)
        db.session.commit()
        assert ms.enabled is True
        assert ms.pop_drop_threshold == 50
        assert ms.neighbor_radius == 15
        assert ms.enemy_radius == 20

    def test_discord_id_unique(self, db):
        ms1 = MonitorSettings(discord_id=66666)
        ms2 = MonitorSettings(discord_id=66666)
        db.session.add(ms1)
        db.session.commit()
        db.session.add(ms2)
        with pytest.raises(IntegrityError):
            db.session.commit()


# ---------------------------------------------------------------------------
# TroopSupport — status defaults
# ---------------------------------------------------------------------------

class TestTroopSupport:
    def test_create_and_defaults(self, db):
        ts = TroopSupport(
            from_x=0, from_y=0, to_x=10, to_y=10,
            player_discord_id="123", troops=json.dumps({"Phalanx": 200}),
        )
        db.session.add(ts)
        db.session.commit()
        assert ts.status == "in_transit"

    def test_status_change(self, db):
        ts = TroopSupport(
            from_x=1, from_y=1, to_x=2, to_y=2,
            player_discord_id="456", troops="{}",
        )
        db.session.add(ts)
        db.session.commit()
        ts.status = "arrived"
        db.session.commit()
        assert TroopSupport.query.get(ts.id).status == "arrived"


# ---------------------------------------------------------------------------
# PersonalAlert
# ---------------------------------------------------------------------------

class TestPersonalAlert:
    def test_create_and_defaults(self, db):
        pa = PersonalAlert(discord_id=111222, alert_type="pop_drop",
                           data=json.dumps({"village": "X"}))
        db.session.add(pa)
        db.session.commit()
        assert pa.notified is False
        assert pa.created_at is not None

    def test_required_alert_type(self, db):
        pa = PersonalAlert(discord_id=333444)
        db.session.add(pa)
        with pytest.raises(IntegrityError):
            db.session.commit()


# ---------------------------------------------------------------------------
# BattleReport
# ---------------------------------------------------------------------------

class TestBattleReport:
    def test_create_with_json(self, db):
        br = BattleReport(
            attacker_name="Attacker",
            defender_name="Defender",
            attacker_troops=json.dumps({"Clubswinger": 500}),
            attacker_losses=json.dumps({"Clubswinger": 100}),
            defender_troops=json.dumps({"Phalanx": 300}),
            defender_losses=json.dumps({"Phalanx": 50}),
            result="wygrana_obrony",
        )
        db.session.add(br)
        db.session.commit()
        assert br.is_manual is False
        fetched = BattleReport.query.get(br.id)
        assert json.loads(fetched.attacker_troops)["Clubswinger"] == 500


# ---------------------------------------------------------------------------
# VillageTroops
# ---------------------------------------------------------------------------

class TestVillageTroops:
    def test_required_fields(self, db):
        vt = VillageTroops(village_x=5, village_y=5)
        db.session.add(vt)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_create(self, db):
        vt = VillageTroops(village_x=10, village_y=-10,
                           player_discord_id="789",
                           troops=json.dumps({"Legionnaire": 50}))
        db.session.add(vt)
        db.session.commit()
        assert vt.id is not None
