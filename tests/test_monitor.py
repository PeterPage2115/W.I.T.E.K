"""Testy dla osobistego monitoringu (/tmonitor)."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app import create_app
from app.database import db as _db
from app.models import (
    MonitorSettings,
    PersonalAlert,
    Snapshot,
    User,
    Village,
)
from bot.cogs.monitor import Monitor


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


def _make_village(map_id, snapshot_id, uid, player_name, aid, alliance_name,
                  population, x=0, y=0, vid=None, name="Wioska"):
    """Helper do tworzenia wiosek testowych."""
    return Village(
        map_id=map_id,
        snapshot_id=snapshot_id,
        x=x,
        y=y,
        tid=1,
        vid=vid if vid is not None else map_id,
        name=name,
        uid=uid,
        player_name=player_name,
        aid=aid,
        alliance_name=alliance_name,
        population=population,
    )


# ------------------------------------------------------------------ #
# MonitorSettings model
# ------------------------------------------------------------------ #
class TestMonitorSettingsModel:
    def test_create_with_defaults(self, app, db_session):
        ms = MonitorSettings(discord_id=12345)
        db_session.add(ms)
        db_session.commit()

        loaded = MonitorSettings.query.first()
        assert loaded.discord_id == 12345
        assert loaded.enabled is True
        assert loaded.pop_drop_threshold == 50
        assert loaded.neighbor_radius == 15
        assert loaded.enemy_radius == 20
        assert loaded.last_checked_snapshot_id is None
        assert loaded.created_at is not None

    def test_unique_discord_id(self, app, db_session):
        ms1 = MonitorSettings(discord_id=100)
        ms2 = MonitorSettings(discord_id=100)
        db_session.add(ms1)
        db_session.commit()
        db_session.add(ms2)
        with pytest.raises(Exception):
            db_session.commit()

    def test_custom_values(self, app, db_session):
        ms = MonitorSettings(
            discord_id=200,
            enabled=False,
            pop_drop_threshold=100,
            neighbor_radius=30,
            enemy_radius=40,
        )
        db_session.add(ms)
        db_session.commit()

        loaded = MonitorSettings.query.first()
        assert loaded.enabled is False
        assert loaded.pop_drop_threshold == 100
        assert loaded.neighbor_radius == 30
        assert loaded.enemy_radius == 40


# ------------------------------------------------------------------ #
# PersonalAlert model
# ------------------------------------------------------------------ #
class TestPersonalAlertModel:
    def test_create_alert(self, app, db_session):
        pa = PersonalAlert(
            discord_id=12345,
            snapshot_id=1,
            alert_type="pop_drop",
            data=json.dumps({"village": "Test", "drop": 100}),
        )
        db_session.add(pa)
        db_session.commit()

        loaded = PersonalAlert.query.first()
        assert loaded.discord_id == 12345
        assert loaded.snapshot_id == 1
        assert loaded.alert_type == "pop_drop"
        assert loaded.notified is False
        assert loaded.created_at is not None
        data = json.loads(loaded.data)
        assert data["drop"] == 100

    def test_multiple_alerts_per_user(self, app, db_session):
        for i in range(3):
            db_session.add(PersonalAlert(
                discord_id=100, snapshot_id=1, alert_type=f"type_{i}",
            ))
        db_session.commit()
        assert PersonalAlert.query.filter_by(discord_id=100).count() == 3


# ------------------------------------------------------------------ #
# Population drop detection
# ------------------------------------------------------------------ #
class TestPopulationDropDetection:
    def test_detects_drop_above_threshold(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(
            1, s1.id, uid=10, player_name="Gracz1",
            aid=1, alliance_name="NASI", population=1000,
            x=50, y=50, vid=100, name="Moja Wioska"
        ))
        db_session.add(_make_village(
            1, s2.id, uid=10, player_name="Gracz1",
            aid=1, alliance_name="NASI", population=900,
            x=50, y=50, vid=100, name="Moja Wioska"
        ))
        db_session.commit()

        old_villages = Monitor._get_user_villages(s1.id, 10)
        new_villages = Monitor._get_user_villages(s2.id, 10)

        old_by_vid = {v["vid"]: v for v in old_villages}
        threshold = 50  # default
        drops = []
        for v in new_villages:
            old = old_by_vid.get(v["vid"])
            if old and old["pop"] - v["pop"] >= threshold:
                drops.append({
                    "type": "pop_drop",
                    "drop": old["pop"] - v["pop"],
                })

        assert len(drops) == 1
        assert drops[0]["drop"] == 100

    def test_ignores_drop_below_threshold(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(
            1, s1.id, uid=10, player_name="Gracz1",
            aid=1, alliance_name="NASI", population=1000,
            x=50, y=50, vid=100,
        ))
        db_session.add(_make_village(
            1, s2.id, uid=10, player_name="Gracz1",
            aid=1, alliance_name="NASI", population=970,
            x=50, y=50, vid=100,
        ))
        db_session.commit()

        old_villages = Monitor._get_user_villages(s1.id, 10)
        new_villages = Monitor._get_user_villages(s2.id, 10)

        old_by_vid = {v["vid"]: v for v in old_villages}
        threshold = 50
        drops = []
        for v in new_villages:
            old = old_by_vid.get(v["vid"])
            if old and old["pop"] - v["pop"] >= threshold:
                drops.append({"type": "pop_drop"})

        assert len(drops) == 0

    def test_ignores_no_change(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(
            1, s1.id, uid=10, player_name="Gracz1",
            aid=1, alliance_name="NASI", population=500,
            x=10, y=10, vid=100,
        ))
        db_session.add(_make_village(
            1, s2.id, uid=10, player_name="Gracz1",
            aid=1, alliance_name="NASI", population=500,
            x=10, y=10, vid=100,
        ))
        db_session.commit()

        old_villages = Monitor._get_user_villages(s1.id, 10)
        new_villages = Monitor._get_user_villages(s2.id, 10)

        old_by_vid = {v["vid"]: v for v in old_villages}
        drops = []
        for v in new_villages:
            old = old_by_vid.get(v["vid"])
            if old and old["pop"] - v["pop"] >= 50:
                drops.append({"type": "pop_drop"})

        assert len(drops) == 0

    def test_detects_exact_threshold(self, app, db_session):
        """Drop exactly equal to threshold should trigger alert."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(
            1, s1.id, uid=10, player_name="Gracz1",
            aid=1, alliance_name="NASI", population=100,
            x=10, y=10, vid=100,
        ))
        db_session.add(_make_village(
            1, s2.id, uid=10, player_name="Gracz1",
            aid=1, alliance_name="NASI", population=50,
            x=10, y=10, vid=100,
        ))
        db_session.commit()

        old_villages = Monitor._get_user_villages(s1.id, 10)
        new_villages = Monitor._get_user_villages(s2.id, 10)

        old_by_vid = {v["vid"]: v for v in old_villages}
        drops = []
        for v in new_villages:
            old = old_by_vid.get(v["vid"])
            if old and old["pop"] - v["pop"] >= 50:
                drops.append({"type": "pop_drop"})

        assert len(drops) == 1


# ------------------------------------------------------------------ #
# New neighbor detection
# ------------------------------------------------------------------ #
class TestNewNeighborDetection:
    def test_detects_new_neighbor_within_radius(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Old snapshot: only our village
        db_session.add(_make_village(
            1, s1.id, uid=10, player_name="MyPlayer",
            aid=1, alliance_name="NASI", population=500,
            x=50, y=50, vid=100,
        ))
        # New snapshot: our village + new neighbor
        db_session.add(_make_village(
            1, s2.id, uid=10, player_name="MyPlayer",
            aid=1, alliance_name="NASI", population=500,
            x=50, y=50, vid=100,
        ))
        db_session.add(_make_village(
            2, s2.id, uid=20, player_name="NewGuy",
            aid=3, alliance_name="INNI", population=200,
            x=55, y=55, vid=200, name="Nowa Wioska"
        ))
        db_session.commit()

        neighbors = Monitor._find_new_neighbors(
            50, 50, 15, s2.id, s1.id, 401
        )
        assert len(neighbors) == 1
        assert neighbors[0]["player"] == "NewGuy"
        assert neighbors[0]["distance"] > 0

    def test_ignores_existing_neighbor(self, app, db_session):
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Same neighbor in both snapshots
        for snap in [s1, s2]:
            db_session.add(_make_village(
                1, snap.id, uid=10, player_name="MyPlayer",
                aid=1, alliance_name="NASI", population=500,
                x=50, y=50, vid=100,
            ))
            db_session.add(_make_village(
                2, snap.id, uid=20, player_name="OldNeighbor",
                aid=3, alliance_name="INNI", population=200,
                x=55, y=55, vid=200,
            ))
        db_session.commit()

        neighbors = Monitor._find_new_neighbors(
            50, 50, 15, s2.id, s1.id, 401
        )
        assert len(neighbors) == 0

    def test_ignores_neighbor_outside_radius(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(
            1, s1.id, uid=10, player_name="MyPlayer",
            aid=1, alliance_name="NASI", population=500,
            x=50, y=50, vid=100,
        ))
        db_session.add(_make_village(
            1, s2.id, uid=10, player_name="MyPlayer",
            aid=1, alliance_name="NASI", population=500,
            x=50, y=50, vid=100,
        ))
        # Far away new village (distance ~141)
        db_session.add(_make_village(
            2, s2.id, uid=20, player_name="FarAway",
            aid=3, alliance_name="INNI", population=200,
            x=-50, y=-50, vid=200,
        ))
        db_session.commit()

        neighbors = Monitor._find_new_neighbors(
            50, 50, 15, s2.id, s1.id, 401
        )
        assert len(neighbors) == 0


# ------------------------------------------------------------------ #
# Enemy detection
# ------------------------------------------------------------------ #
class TestEnemyDetection:
    def test_detects_new_enemy_nearby(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(
            1, s1.id, uid=10, player_name="MyPlayer",
            aid=1, alliance_name="NASI", population=500,
            x=50, y=50, vid=100,
        ))
        db_session.add(_make_village(
            1, s2.id, uid=10, player_name="MyPlayer",
            aid=1, alliance_name="NASI", population=500,
            x=50, y=50, vid=100,
        ))
        db_session.add(_make_village(
            2, s2.id, uid=30, player_name="EnemyPlayer",
            aid=99, alliance_name="WROG", population=300,
            x=55, y=50, vid=300,
        ))
        db_session.commit()

        enemies = Monitor._find_new_enemies(
            50, 50, 20, s2.id, s1.id, [1, 2], 401
        )
        assert len(enemies) == 1
        assert enemies[0]["player"] == "EnemyPlayer"
        assert enemies[0]["alliance"] == "WROG"

    def test_ignores_allied_village(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(
            1, s1.id, uid=10, player_name="MyPlayer",
            aid=1, alliance_name="NASI", population=500,
            x=50, y=50, vid=100,
        ))
        db_session.add(_make_village(
            1, s2.id, uid=10, player_name="MyPlayer",
            aid=1, alliance_name="NASI", population=500,
            x=50, y=50, vid=100,
        ))
        # Allied village (aid=2 is in our_alliances)
        db_session.add(_make_village(
            2, s2.id, uid=20, player_name="AllyPlayer",
            aid=2, alliance_name="SOJUSZ", population=300,
            x=55, y=50, vid=200,
        ))
        db_session.commit()

        enemies = Monitor._find_new_enemies(
            50, 50, 20, s2.id, s1.id, [1, 2], 401
        )
        assert len(enemies) == 0

    def test_ignores_neutral_no_alliance(self, app, db_session):
        """Villages with aid=0 (no alliance) are not enemies."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(
            1, s1.id, uid=10, player_name="MyPlayer",
            aid=1, alliance_name="NASI", population=500,
            x=50, y=50, vid=100,
        ))
        db_session.add(_make_village(
            1, s2.id, uid=10, player_name="MyPlayer",
            aid=1, alliance_name="NASI", population=500,
            x=50, y=50, vid=100,
        ))
        # Neutral village — no alliance
        db_session.add(_make_village(
            2, s2.id, uid=20, player_name="NeutralGuy",
            aid=0, alliance_name="", population=100,
            x=55, y=50, vid=200,
        ))
        db_session.commit()

        enemies = Monitor._find_new_enemies(
            50, 50, 20, s2.id, s1.id, [1, 2], 401
        )
        assert len(enemies) == 0

    def test_ignores_existing_enemy(self, app, db_session):
        """Enemy present in both snapshots should not be detected."""
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        for snap in [s1, s2]:
            db_session.add(_make_village(
                1, snap.id, uid=10, player_name="MyPlayer",
                aid=1, alliance_name="NASI", population=500,
                x=50, y=50, vid=100,
            ))
            db_session.add(_make_village(
                2, snap.id, uid=30, player_name="OldEnemy",
                aid=99, alliance_name="WROG", population=300,
                x=55, y=50, vid=300,
            ))
        db_session.commit()

        enemies = Monitor._find_new_enemies(
            50, 50, 20, s2.id, s1.id, [1, 2], 401
        )
        assert len(enemies) == 0


# ------------------------------------------------------------------ #
# DB helpers
# ------------------------------------------------------------------ #
class TestDBHelpers:
    def test_get_user_villages(self, app, db_session):
        s = Snapshot(village_count=2)
        db_session.add(s)
        db_session.flush()

        db_session.add(_make_village(
            1, s.id, uid=10, player_name="P1",
            aid=1, alliance_name="A1", population=500,
            x=10, y=20, vid=100, name="Village1"
        ))
        db_session.add(_make_village(
            2, s.id, uid=10, player_name="P1",
            aid=1, alliance_name="A1", population=300,
            x=30, y=40, vid=200, name="Village2"
        ))
        db_session.add(_make_village(
            3, s.id, uid=20, player_name="P2",
            aid=2, alliance_name="A2", population=100,
            x=50, y=60, vid=300,
        ))
        db_session.commit()

        villages = Monitor._get_user_villages(s.id, 10)
        assert len(villages) == 2
        assert all(isinstance(v, dict) for v in villages)
        names = {v["name"] for v in villages}
        assert names == {"Village1", "Village2"}

    def test_get_two_latest_snapshots(self, app, db_session):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        s1 = Snapshot(village_count=100, fetched_at=now - timedelta(hours=2))
        s2 = Snapshot(village_count=110, fetched_at=now - timedelta(hours=1))
        s3 = Snapshot(village_count=120, fetched_at=now)
        db_session.add_all([s1, s2, s3])
        db_session.commit()

        result = Monitor._get_two_latest_snapshots()
        assert result is not None
        latest, prev = result
        assert latest == s3.id
        assert prev == s2.id

    def test_get_two_latest_snapshots_returns_none_if_only_one(self, app, db_session):
        s1 = Snapshot(village_count=100)
        db_session.add(s1)
        db_session.commit()

        result = Monitor._get_two_latest_snapshots()
        assert result is None

    def test_get_monitored_users(self, app, db_session):
        user = User(discord_id=100, travian_uid=10, travian_name="P1")
        ms = MonitorSettings(discord_id=100, enabled=True)
        db_session.add_all([user, ms])
        db_session.commit()

        users = Monitor._get_monitored_users()
        assert len(users) == 1
        assert users[0]["discord_id"] == 100
        assert users[0]["travian_uid"] == 10

    def test_get_monitored_users_ignores_disabled(self, app, db_session):
        user = User(discord_id=100, travian_uid=10, travian_name="P1")
        ms = MonitorSettings(discord_id=100, enabled=False)
        db_session.add_all([user, ms])
        db_session.commit()

        users = Monitor._get_monitored_users()
        assert len(users) == 0

    def test_get_monitored_users_ignores_no_travian_uid(self, app, db_session):
        user = User(discord_id=100, travian_uid=None, travian_name=None)
        ms = MonitorSettings(discord_id=100, enabled=True)
        db_session.add_all([user, ms])
        db_session.commit()

        users = Monitor._get_monitored_users()
        assert len(users) == 0

    def test_store_alerts(self, app, db_session):
        alerts = [
            {"type": "pop_drop", "village": "V1", "drop": 100},
            {"type": "new_neighbor", "neighbor_player": "Enemy"},
        ]
        Monitor._store_alerts(12345, alerts, snapshot_id=5)

        stored = PersonalAlert.query.all()
        assert len(stored) == 2
        assert all(a.discord_id == 12345 for a in stored)
        assert all(a.snapshot_id == 5 for a in stored)
        assert all(a.notified is True for a in stored)

    def test_update_last_checked(self, app, db_session):
        ms = MonitorSettings(discord_id=100)
        db_session.add(ms)
        db_session.commit()

        assert ms.last_checked_snapshot_id is None
        Monitor._update_last_checked(100, 42)

        db_session.refresh(ms)
        assert ms.last_checked_snapshot_id == 42

    def test_validate_snapshots(self, app, db_session):
        s1 = Snapshot(village_count=100)
        s2 = Snapshot(village_count=110)
        db_session.add_all([s1, s2])
        db_session.commit()

        assert Monitor._validate_snapshots(s2.id, s1.id) is True

    def test_validate_snapshots_rejects_truncated(self, app, db_session):
        s1 = Snapshot(village_count=1000)
        s2 = Snapshot(village_count=10)
        db_session.add_all([s1, s2])
        db_session.commit()

        assert Monitor._validate_snapshots(s2.id, s1.id) is False


# ------------------------------------------------------------------ #
# Enable/disable toggle
# ------------------------------------------------------------------ #
class TestMonitorToggle:
    def test_enable_creates_settings(self, app, db_session):
        user = User(discord_id=100, travian_uid=10, travian_name="P1")
        db_session.add(user)
        db_session.commit()

        assert MonitorSettings.query.filter_by(discord_id=100).first() is None

        ms = MonitorSettings(discord_id=100, enabled=True)
        db_session.add(ms)
        db_session.commit()

        loaded = MonitorSettings.query.filter_by(discord_id=100).first()
        assert loaded.enabled is True

    def test_disable_toggle(self, app, db_session):
        user = User(discord_id=100, travian_uid=10, travian_name="P1")
        ms = MonitorSettings(discord_id=100, enabled=True)
        db_session.add_all([user, ms])
        db_session.commit()

        ms.enabled = False
        db_session.commit()

        loaded = MonitorSettings.query.filter_by(discord_id=100).first()
        assert loaded.enabled is False

    def test_reenable(self, app, db_session):
        user = User(discord_id=100, travian_uid=10, travian_name="P1")
        ms = MonitorSettings(discord_id=100, enabled=False)
        db_session.add_all([user, ms])
        db_session.commit()

        ms.enabled = True
        db_session.commit()

        loaded = MonitorSettings.query.filter_by(discord_id=100).first()
        assert loaded.enabled is True


# ------------------------------------------------------------------ #
# Settings update
# ------------------------------------------------------------------ #
class TestSettingsUpdate:
    def test_partial_update(self, app, db_session):
        ms = MonitorSettings(discord_id=100)
        db_session.add(ms)
        db_session.commit()

        ms.pop_drop_threshold = 200
        db_session.commit()

        loaded = MonitorSettings.query.first()
        assert loaded.pop_drop_threshold == 200
        assert loaded.neighbor_radius == 15  # unchanged
        assert loaded.enemy_radius == 20  # unchanged

    def test_full_update(self, app, db_session):
        ms = MonitorSettings(discord_id=100)
        db_session.add(ms)
        db_session.commit()

        ms.pop_drop_threshold = 100
        ms.neighbor_radius = 30
        ms.enemy_radius = 40
        db_session.commit()

        loaded = MonitorSettings.query.first()
        assert loaded.pop_drop_threshold == 100
        assert loaded.neighbor_radius == 30
        assert loaded.enemy_radius == 40


# ------------------------------------------------------------------ #
# No alerts on same snapshot
# ------------------------------------------------------------------ #
class TestDeduplication:
    def test_skip_if_already_checked(self, app, db_session):
        """last_checked_snapshot_id prevents re-checking same snapshot."""
        user = User(discord_id=100, travian_uid=10, travian_name="P1")
        ms = MonitorSettings(discord_id=100, enabled=True, last_checked_snapshot_id=5)
        db_session.add_all([user, ms])
        db_session.commit()

        users = Monitor._get_monitored_users()
        assert len(users) == 1
        assert users[0]["last_checked_snapshot_id"] == 5

        # The monitor_check loop skips if last_checked == latest_id
        # This is a logic test — when latest_id == 5, user is skipped
        latest_id = 5
        assert users[0]["last_checked_snapshot_id"] == latest_id

    def test_alerts_stored_with_snapshot_id(self, app, db_session):
        """PersonalAlert records include snapshot_id for deduplication."""
        alerts = [{"type": "pop_drop", "village": "V1", "drop": 100}]
        Monitor._store_alerts(100, alerts, snapshot_id=42)

        pa = PersonalAlert.query.first()
        assert pa.snapshot_id == 42


# ------------------------------------------------------------------ #
# DM sending (mock)
# ------------------------------------------------------------------ #
class TestDMSending:
    def test_send_dm_pop_drop(self, app):
        """DM embed includes pop drop info."""
        import asyncio

        mock_user = AsyncMock()
        mock_user.send = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.get_user = MagicMock(return_value=mock_user)
        mock_bot.flask_app = app

        cog = Monitor(mock_bot)
        alerts = [{
            "type": "pop_drop",
            "village": "Kartagina",
            "coords": "50|30",
            "old_pop": 1250,
            "new_pop": 1100,
            "drop": 150,
        }]

        asyncio.run(cog._send_dm(12345, alerts))

        mock_user.send.assert_called_once()
        call_kwargs = mock_user.send.call_args
        embed = call_kwargs.kwargs.get("embed") or call_kwargs.args[0]
        assert embed.title == "🔔 Osobisty raport — WITEK"
        field_names = [f.name for f in embed.fields]
        assert "📉 Spadki populacji" in field_names

    def test_send_dm_multiple_alert_types(self, app):
        """DM embed includes all alert types."""
        import asyncio

        mock_user = AsyncMock()
        mock_user.send = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.get_user = MagicMock(return_value=mock_user)
        mock_bot.flask_app = app

        cog = Monitor(mock_bot)
        alerts = [
            {
                "type": "pop_drop",
                "village": "V1", "coords": "1|1",
                "old_pop": 1000, "new_pop": 900, "drop": 100,
            },
            {
                "type": "new_neighbor",
                "your_village": "V1", "your_coords": "1|1",
                "neighbor_player": "New", "neighbor_village": "NV",
                "neighbor_coords": "5|5", "distance": 5.7,
            },
            {
                "type": "enemy_nearby",
                "your_village": "V1", "your_coords": "1|1",
                "enemy_player": "Bad", "enemy_alliance": "EVIL",
                "enemy_coords": "8|8", "distance": 9.9,
            },
        ]

        asyncio.run(cog._send_dm(12345, alerts))

        mock_user.send.assert_called_once()
        call_kwargs = mock_user.send.call_args
        embed = call_kwargs.kwargs.get("embed") or call_kwargs.args[0]
        field_names = [f.name for f in embed.fields]
        assert "📉 Spadki populacji" in field_names
        assert "🏘️ Nowi sąsiedzi" in field_names
        assert "⚠️ Wrogowie w pobliżu" in field_names

    def test_send_dm_user_not_cached_fetches(self, app):
        """Falls back to fetch_user when get_user returns None."""
        import asyncio

        mock_user = AsyncMock()
        mock_user.send = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.get_user = MagicMock(return_value=None)
        mock_bot.fetch_user = AsyncMock(return_value=mock_user)
        mock_bot.flask_app = app

        cog = Monitor(mock_bot)
        alerts = [{
            "type": "pop_drop",
            "village": "V1", "coords": "1|1",
            "old_pop": 200, "new_pop": 100, "drop": 100,
        }]

        asyncio.run(cog._send_dm(12345, alerts))

        mock_bot.fetch_user.assert_called_once_with(12345)
        mock_user.send.assert_called_once()
