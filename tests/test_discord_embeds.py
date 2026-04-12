"""Testy embeddów Discord — sortowanie, limity, overflow, discord_eligible."""

import json

import pytest
from app import create_app
from app.database import db as _db
from app.models import Alert, Snapshot, Village
from app.map_sql.alerts import detect_alerts
from bot.cogs.alerts import _build_embed, _embed_pop_drops


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TRAVIAN_SERVER_URL = "https://test.travian.com"
    TRAVIAN_MAP_SIZE = 401
    TRAVIAN_OUR_ALLIANCES = [1, 2]
    POP_DROP_THRESHOLD = 25
    NEW_VILLAGE_RADIUS = 30
    MAX_ALERTS_PER_TYPE = 10
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
                  population, x=0, y=0):
    return Village(
        map_id=map_id, snapshot_id=snapshot_id, x=x, y=y, tid=1,
        vid=map_id, name="Wioska", uid=uid, player_name=player_name,
        aid=aid, alliance_name=alliance_name, population=population,
    )


class TestPopDropSortBySeverity:
    def test_sorted_by_drop_pct_descending(self):
        items = [
            {"player_name": "A", "alliance_name": "X", "old_pop": 1000, "new_pop": 700, "drop_pct": 30.0},
            {"player_name": "B", "alliance_name": "X", "old_pop": 1000, "new_pop": 200, "drop_pct": 80.0},
            {"player_name": "C", "alliance_name": "X", "old_pop": 1000, "new_pop": 500, "drop_pct": 50.0},
        ]
        embed = _embed_pop_drops(items, max_items=10)
        lines = embed.description.split("\n")
        assert "**B**" in lines[0]
        assert "**C**" in lines[1]
        assert "**A**" in lines[2]


class TestBuildEmbedMaxItems:
    def test_caps_at_max_items(self):
        items = [
            {"player_name": f"P{i}", "alliance_name": "", "old_pop": 1000,
             "new_pop": 500, "drop_pct": 50.0}
            for i in range(15)
        ]
        embed = _build_embed("pop_drop", items, max_items=5)
        content_lines = [l for l in embed.description.split("\n") if l.startswith("**")]
        assert len(content_lines) == 5

    def test_no_overflow_when_under_limit(self):
        items = [
            {"player_name": "P1", "alliance_name": "", "old_pop": 1000,
             "new_pop": 500, "drop_pct": 50.0},
        ]
        embed = _build_embed("pop_drop", items, max_items=10)
        assert "więcej" not in embed.description


class TestOverflowMessage:
    def test_overflow_message_appears(self):
        items = [
            {"player_name": f"P{i}", "alliance_name": "", "old_pop": 1000,
             "new_pop": 500, "drop_pct": 50.0}
            for i in range(8)
        ]
        embed = _build_embed("pop_drop", items, max_items=3)
        assert "… i 5 więcej — sprawdź /alerts na dashboardzie" in embed.description

    def test_overflow_new_villages(self):
        items = [
            {"village_name": f"V{i}", "x": i, "y": i, "player_name": "P",
             "alliance_name": "A", "distance": 10.0}
            for i in range(5)
        ]
        embed = _build_embed("new_village", items, max_items=2)
        assert "… i 3 więcej" in embed.description

    def test_overflow_alliance_changes(self):
        items = [
            {"player_name": f"P{i}", "total_pop": 1000, "old_alliance_name": "A",
             "new_alliance_name": "B", "change_type": "switch"}
            for i in range(4)
        ]
        embed = _build_embed("alliance_change", items, max_items=2)
        assert "… i 2 więcej" in embed.description


class TestTimestampInFooter:
    def test_footer_has_timestamp(self):
        items = [{"player_name": "P", "alliance_name": "", "old_pop": 1000,
                  "new_pop": 500, "drop_pct": 50.0}]
        embed = _embed_pop_drops(items, max_items=10)
        assert "W.I.T.E.K" in embed.footer.text
        assert "•" in embed.footer.text


class TestFetchPendingAlertsEligibility:
    """discord_eligible=False alerts should not be fetched for Discord."""

    def test_only_eligible_alerts_fetched(self, app, db_session):
        s = Snapshot(village_count=1)
        db_session.add(s)
        db_session.flush()

        # Eligible alert (pop_drop)
        a1 = Alert(
            snapshot_id=s.id, alert_type="pop_drop",
            data=json.dumps({"type": "pop_drop", "player_name": "A"}),
            discord_eligible=True, notified=False,
        )
        # Non-eligible alert (new_village)
        a2 = Alert(
            snapshot_id=s.id, alert_type="new_village",
            data=json.dumps({"type": "new_village", "village_name": "V"}),
            discord_eligible=False, notified=False,
        )
        # Already notified eligible alert
        a3 = Alert(
            snapshot_id=s.id, alert_type="pop_drop",
            data=json.dumps({"type": "pop_drop", "player_name": "B"}),
            discord_eligible=True, notified=True,
        )
        db_session.add_all([a1, a2, a3])
        db_session.commit()

        rows = (
            Alert.query
            .filter_by(notified=False, discord_eligible=True)
            .order_by(Alert.created_at.asc())
            .limit(50)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].alert_type == "pop_drop"
        data = json.loads(rows[0].data)
        assert data["player_name"] == "A"


class TestDiscordEligibleInDetectAlerts:
    """detect_alerts() sets discord_eligible correctly per alert type."""

    def test_pop_drop_is_eligible(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="Nasz",
                                     aid=1, alliance_name="NASI", population=1000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Nasz",
                                     aid=1, alliance_name="NASI", population=500))
        db_session.commit()

        config = {
            "TRAVIAN_OUR_ALLIANCES": [1, 2],
            "POP_DROP_THRESHOLD": 25,
            "NEW_VILLAGE_RADIUS": 30,
            "TRAVIAN_MAP_SIZE": 401,
            "MIN_POP_FOR_ALERTS": 500,
            "ALERT_COOLDOWN_HOURS": 0,
        }
        alerts = detect_alerts(s2.id, s1.id, config)
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) >= 1
        assert pop_drops[0]["discord_eligible"] is True

    def test_new_village_not_eligible(self, app, db_session):
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=3)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Allied village in both snapshots (anchor for radius check)
        db_session.add(_make_village(1, s1.id, uid=20, player_name="Nasz",
                                     aid=1, alliance_name="NASI", population=500, x=0, y=0))
        db_session.add(_make_village(1, s2.id, uid=20, player_name="Nasz",
                                     aid=1, alliance_name="NASI", population=500, x=0, y=0))
        # Enemy existing village
        db_session.add(_make_village(2, s1.id, uid=30, player_name="Wróg",
                                     aid=99, alliance_name="ZŁI", population=200, x=5, y=5))
        db_session.add(_make_village(2, s2.id, uid=30, player_name="Wróg",
                                     aid=99, alliance_name="ZŁI", population=200, x=5, y=5))
        # NEW enemy village close to us (only in s2)
        db_session.add(_make_village(3, s2.id, uid=30, player_name="Wróg",
                                     aid=99, alliance_name="ZŁI", population=100, x=1, y=1))
        db_session.commit()

        config = {
            "TRAVIAN_OUR_ALLIANCES": [1, 2],
            "POP_DROP_THRESHOLD": 25,
            "NEW_VILLAGE_RADIUS": 30,
            "TRAVIAN_MAP_SIZE": 401,
            "MIN_POP_FOR_ALERTS": 500,
            "ALERT_COOLDOWN_HOURS": 0,
        }
        alerts = detect_alerts(s2.id, s1.id, config)
        new_villages = [a for a in alerts if a["type"] == "new_village"]
        assert len(new_villages) >= 1
        assert new_villages[0]["discord_eligible"] is False

    def test_alliance_change_not_eligible(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Player switches from our alliance to enemy
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Zdrajca",
                                     aid=1, alliance_name="NASI", population=500))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Zdrajca",
                                     aid=99, alliance_name="ZŁI", population=500))
        db_session.commit()

        config = {
            "TRAVIAN_OUR_ALLIANCES": [1, 2],
            "POP_DROP_THRESHOLD": 25,
            "NEW_VILLAGE_RADIUS": 30,
            "TRAVIAN_MAP_SIZE": 401,
            "MIN_POP_FOR_ALERTS": 500,
            "ALERT_COOLDOWN_HOURS": 0,
        }
        alerts = detect_alerts(s2.id, s1.id, config)
        changes = [a for a in alerts if a["type"] == "alliance_change"]
        assert len(changes) >= 1
        assert changes[0]["discord_eligible"] is False
