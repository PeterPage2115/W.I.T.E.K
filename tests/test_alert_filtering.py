"""Testy filtrowania alertów pop_drop — tylko nasi, min_pop, cooldown."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from app import create_app
from app.database import db as _db
from app.models import Alert, Snapshot, Village
from app.map_sql.alerts import detect_alerts


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TRAVIAN_SERVER_URL = "https://test.travian.com"
    TRAVIAN_MAP_SIZE = 401
    TRAVIAN_OUR_ALLIANCES = [1, 2]
    POP_DROP_THRESHOLD = 25
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
    return Village(
        map_id=map_id,
        snapshot_id=snapshot_id,
        x=x, y=y,
        tid=1,
        vid=vid if vid is not None else map_id,
        name=name,
        uid=uid,
        player_name=player_name,
        aid=aid,
        alliance_name=alliance_name,
        population=population,
    )


def _config(our_alliances=None, threshold=25, radius=30, map_size=401,
            min_pop=500, cooldown_hours=0):
    return {
        "TRAVIAN_OUR_ALLIANCES": our_alliances or [1, 2],
        "POP_DROP_THRESHOLD": threshold,
        "NEW_VILLAGE_RADIUS": radius,
        "TRAVIAN_MAP_SIZE": map_size,
        "MIN_POP_FOR_ALERTS": min_pop,
        "ALERT_COOLDOWN_HOURS": cooldown_hours,
    }


class TestPopDropOnlyOurAlliance:
    def test_pop_drop_only_our_alliance(self, app, db_session):
        """Wróg z ogromnym spadkiem pop NIE generuje alertu."""
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Wróg — spadek 80%
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Wróg",
                                     aid=99, alliance_name="ZŁI", population=5000,
                                     x=5, y=5))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Wróg",
                                     aid=99, alliance_name="ZŁI", population=1000,
                                     x=5, y=5))
        # Nasza wioska blisko (żeby upewnić się, że proximity NIE wpływa)
        db_session.add(_make_village(2, s1.id, uid=20, player_name="Nasz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=0, y=0))
        db_session.add(_make_village(2, s2.id, uid=20, player_name="Nasz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=0, y=0))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        enemy_drops = [d for d in pop_drops if d["player_name"] == "Wróg"]
        assert len(enemy_drops) == 0


class TestPopDropMinPopFilter:
    def test_pop_drop_min_pop_filter(self, app, db_session):
        """Gracz z pop < 500 jest pomijany nawet przy dużym spadku."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Nasz gracz z pop 300 — spadek 50%
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Mały",
                                     aid=1, alliance_name="NASI", population=300))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Mały",
                                     aid=1, alliance_name="NASI", population=150))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(min_pop=500))
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 0

    def test_pop_above_min_generates_alert(self, app, db_session):
        """Gracz z pop >= 500 generuje alert normalnie."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="Duży",
                                     aid=1, alliance_name="NASI", population=1000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Duży",
                                     aid=1, alliance_name="NASI", population=500))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(min_pop=500))
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 1


class TestPopDropCooldown:
    def test_pop_drop_cooldown_dedup(self, app, db_session):
        """Istniejący alert w oknie cooldown blokuje ponowny alert."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Istniejący alert sprzed 2h (w oknie 6h cooldown)
        recent_alert = Alert(
            snapshot_id=s1.id,
            alert_type="pop_drop",
            data=json.dumps({"uid": 10, "player_name": "Gracz1"}),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db_session.add(recent_alert)

        db_session.add(_make_village(1, s1.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=1000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=500))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(cooldown_hours=6))
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 0

    def test_pop_drop_cooldown_expired(self, app, db_session):
        """Alert starszy niż cooldown — nowy alert generowany normalnie."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Alert sprzed 8h (poza oknem 6h cooldown)
        old_alert = Alert(
            snapshot_id=s1.id,
            alert_type="pop_drop",
            data=json.dumps({"uid": 10, "player_name": "Gracz1"}),
            created_at=datetime.now(timezone.utc) - timedelta(hours=8),
        )
        db_session.add(old_alert)

        db_session.add(_make_village(1, s1.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=1000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=500))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(cooldown_hours=6))
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 1


class TestPopDropBothSnapshotAllianceCheck:
    def test_pop_drop_both_snapshot_alliance_check(self, app, db_session):
        """Gracz w naszym sojuszu w prev ale nie w new — nadal alertowany."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Gracz opuścił nasz sojusz i stracił pop
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Odchodzący",
                                     aid=1, alliance_name="NASI", population=1000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Odchodzący",
                                     aid=99, alliance_name="WRÓG", population=500))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 1
        assert pop_drops[0]["player_name"] == "Odchodzący"

    def test_player_joined_our_alliance_in_new(self, app, db_session):
        """Gracz dołączył do naszego sojuszu w nowym snapshot — alertowany."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="NowyNasz",
                                     aid=99, alliance_name="WRÓG", population=1000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="NowyNasz",
                                     aid=1, alliance_name="NASI", population=500))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 1
        assert pop_drops[0]["player_name"] == "NowyNasz"


class TestPopDropCooldownPrefixCollision:
    def test_cooldown_does_not_suppress_different_uid_with_prefix(self, app, db_session):
        """Alert for uid=1 must NOT suppress uid=10 (prefix collision guard)."""
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Existing cooldown alert for uid=1
        recent_alert = Alert(
            snapshot_id=s1.id,
            alert_type="pop_drop",
            data=json.dumps({"uid": 1, "player_name": "Gracz1", "old_pop": 1000,
                             "new_pop": 500, "drop_pct": 50.0}),
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(recent_alert)

        # uid=10 (different player) with big pop drop — should NOT be suppressed
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Gracz10",
                                     aid=1, alliance_name="NASI", population=1000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Gracz10",
                                     aid=1, alliance_name="NASI", population=500))
        # uid=1 also present to keep snapshot valid
        db_session.add(_make_village(2, s1.id, uid=1, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=800, x=5, y=5))
        db_session.add(_make_village(2, s2.id, uid=1, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=800, x=5, y=5))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(cooldown_hours=6))
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        # uid=10 should generate an alert (not suppressed by uid=1's cooldown)
        uid10_drops = [d for d in pop_drops if d["uid"] == 10]
        assert len(uid10_drops) == 1
