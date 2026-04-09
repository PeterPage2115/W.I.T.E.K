"""Testy dla systemu alertów map.sql."""

import json
import pytest
from app import create_app
from app.database import db as _db
from app.models import Snapshot, Village, Alert
from app.map_sql.alerts import detect_alerts, torus_distance, validate_snapshot_pair


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


def _config(our_alliances=None, threshold=15, radius=30, map_size=401):
    return {
        "TRAVIAN_OUR_ALLIANCES": our_alliances or [1, 2],
        "POP_DROP_THRESHOLD": threshold,
        "NEW_VILLAGE_RADIUS": radius,
        "TRAVIAN_MAP_SIZE": map_size,
    }


# ------------------------------------------------------------------ #
# Torus distance
# ------------------------------------------------------------------ #
class TestTorusDistance:
    def test_same_point(self):
        assert torus_distance(0, 0, 0, 0) == 0.0

    def test_simple_distance(self):
        d = torus_distance(0, 0, 3, 4)
        assert abs(d - 5.0) < 0.01

    def test_wraps_around(self):
        d = torus_distance(-200, 0, 200, 0, map_size=401)
        assert abs(d - 1.0) < 0.01

    def test_diagonal_wrap(self):
        d = torus_distance(-200, -200, 200, 200, map_size=401)
        expected = (1 ** 2 + 1 ** 2) ** 0.5
        assert abs(d - expected) < 0.01


# ------------------------------------------------------------------ #
# Pop drop detection
# ------------------------------------------------------------------ #
class TestPopDrops:
    def test_detects_significant_drop(self, app, db_session):
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Gracz w naszym sojuszu — snapshot 1: pop 1000, snapshot 2: pop 500
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=1000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=500))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(threshold=15))
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 1
        assert pop_drops[0]["player_name"] == "Gracz1"
        assert pop_drops[0]["drop_pct"] == 50.0

    def test_ignores_small_drop(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Spadek 5% — poniżej progu 15%
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=1000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=950))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(threshold=15))
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 0

    def test_detects_player_disappearance(self, app, db_session):
        """Gracz znika ze snapshotu — populacja → 0."""
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Nasz gracz który znika
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=1000))
        # Inna wioska obecna w obu (snapshot nie jest obcięty)
        db_session.add(_make_village(2, s1.id, uid=20, player_name="Inny",
                                     aid=1, alliance_name="NASI", population=200, x=5, y=5))
        db_session.add(_make_village(2, s2.id, uid=20, player_name="Inny",
                                     aid=1, alliance_name="NASI", population=200, x=5, y=5))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(threshold=15))
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 1
        assert pop_drops[0]["new_pop"] == 0
        assert pop_drops[0]["drop_pct"] == 100.0

    def test_ignores_unrelated_enemy(self, app, db_session):
        """Wróg daleko od naszych wiosek — nie alertuj."""
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Nasza wioska na (0,0)
        db_session.add(_make_village(1, s1.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500, x=0, y=0))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500, x=0, y=0))

        # Wróg daleko (100, 100) — spadek 50%
        db_session.add(_make_village(2, s1.id, uid=20, player_name="DalekiWróg",
                                     aid=99, alliance_name="WRÓG", population=1000, x=100, y=100))
        db_session.add(_make_village(2, s2.id, uid=20, player_name="DalekiWróg",
                                     aid=99, alliance_name="WRÓG", population=500, x=100, y=100))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(threshold=15))
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        # Powinien być alert tylko dla NaszGracz NIE (bo nie spadł)
        # DalekiWróg daleko — nie powinien być alertowany
        enemy_drops = [d for d in pop_drops if d["player_name"] == "DalekiWróg"]
        assert len(enemy_drops) == 0

    def test_multi_village_aggregation(self, app, db_session):
        """Populacja jest sumą z wielu wiosek."""
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Gracz z 2 wioskami w s1 (pop 600+400=1000), 1 w s2 (pop 300)
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=600, vid=101))
        db_session.add(_make_village(2, s1.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=400, vid=102))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Gracz1",
                                     aid=1, alliance_name="NASI", population=300, vid=101))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(threshold=15))
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 1
        assert pop_drops[0]["old_pop"] == 1000
        assert pop_drops[0]["new_pop"] == 300
        assert pop_drops[0]["drop_pct"] == 70.0


# ------------------------------------------------------------------ #
# New village detection
# ------------------------------------------------------------------ #
class TestNewVillages:
    def test_detects_new_enemy_village_nearby(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Nasza wioska (0, 0)
        db_session.add(_make_village(1, s1.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=0, y=0, vid=100))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=0, y=0, vid=100))

        # Nowa wroga wioska (5, 5) — blisko!
        db_session.add(_make_village(2, s2.id, uid=20, player_name="Wróg",
                                     aid=99, alliance_name="ZŁI", population=50,
                                     x=5, y=5, vid=200, name="Nowa Wioska"))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(radius=30))
        new_villages = [a for a in alerts if a["type"] == "new_village"]
        assert len(new_villages) == 1
        assert new_villages[0]["village_name"] == "Nowa Wioska"
        assert new_villages[0]["player_name"] == "Wróg"
        assert new_villages[0]["distance"] < 30

    def test_ignores_new_village_far_away(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=0, y=0, vid=100))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=0, y=0, vid=100))

        # Daleka wioska (100, 100)
        db_session.add(_make_village(2, s2.id, uid=20, player_name="Wróg",
                                     aid=99, alliance_name="ZŁI", population=50,
                                     x=100, y=100, vid=200))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(radius=30))
        new_villages = [a for a in alerts if a["type"] == "new_village"]
        assert len(new_villages) == 0

    def test_ignores_allied_new_village(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=0, y=0, vid=100))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=0, y=0, vid=100))

        # Nowa wioska naszego sojusznika
        db_session.add(_make_village(2, s2.id, uid=11, player_name="NaszDrugi",
                                     aid=1, alliance_name="NASI", population=50,
                                     x=5, y=5, vid=200))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(radius=30))
        new_villages = [a for a in alerts if a["type"] == "new_village"]
        assert len(new_villages) == 0

    def test_ignores_existing_village(self, app, db_session):
        """Wioska obecna w obu snapshotach — nie jest 'nowa'."""
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=0, y=0, vid=100))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=0, y=0, vid=100))

        # Wioska wroga obecna w obu snapshotach
        db_session.add(_make_village(2, s1.id, uid=20, player_name="Wróg",
                                     aid=99, alliance_name="ZŁI", population=50,
                                     x=5, y=5, vid=200))
        db_session.add(_make_village(2, s2.id, uid=20, player_name="Wróg",
                                     aid=99, alliance_name="ZŁI", population=60,
                                     x=5, y=5, vid=200))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(radius=30))
        new_villages = [a for a in alerts if a["type"] == "new_village"]
        assert len(new_villages) == 0

    def test_torus_wrap_detection(self, app, db_session):
        """Nowa wioska blisko po owinięciu torusa."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Nasza wioska na krawędzi (-200, 0)
        db_session.add(_make_village(1, s1.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=-200, y=0, vid=100))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="NaszGracz",
                                     aid=1, alliance_name="NASI", population=500,
                                     x=-200, y=0, vid=100))

        # Wroga wioska na drugim końcu (200, 0) — dystans torusowy = 1
        db_session.add(_make_village(2, s2.id, uid=20, player_name="Wróg",
                                     aid=99, alliance_name="ZŁI", population=50,
                                     x=200, y=0, vid=200))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(radius=30))
        new_villages = [a for a in alerts if a["type"] == "new_village"]
        assert len(new_villages) == 1
        assert new_villages[0]["distance"] == 1.0


# ------------------------------------------------------------------ #
# Alliance change detection
# ------------------------------------------------------------------ #
class TestAllianceChanges:
    def test_detects_player_leaving_our_alliance(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Gracz opuścił nasz sojusz (aid 1 → aid 99)
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Zdrajca",
                                     aid=1, alliance_name="NASI", population=500))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Zdrajca",
                                     aid=99, alliance_name="WRÓG", population=500))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        changes = [a for a in alerts if a["type"] == "alliance_change"]
        assert len(changes) == 1
        assert changes[0]["player_name"] == "Zdrajca"
        assert changes[0]["change_type"] == "leave"
        assert changes[0]["old_alliance_name"] == "NASI"
        assert changes[0]["new_alliance_name"] == "WRÓG"

    def test_detects_player_joining_enemy(self, app, db_session):
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Gracz bez sojuszu dołączył do wroga — blisko naszej wioski
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Nowy",
                                     aid=0, alliance_name="", population=500, x=5, y=5))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Nowy",
                                     aid=99, alliance_name="WRÓG", population=500, x=5, y=5))
        # Nasza wioska w pobliżu
        db_session.add(_make_village(2, s1.id, uid=20, player_name="Sojusznik",
                                     aid=1, alliance_name="NASI", population=300, x=0, y=0))
        db_session.add(_make_village(2, s2.id, uid=20, player_name="Sojusznik",
                                     aid=1, alliance_name="NASI", population=300, x=0, y=0))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        changes = [a for a in alerts if a["type"] == "alliance_change"]
        assert len(changes) == 1
        assert changes[0]["change_type"] == "switch"
        assert changes[0]["new_alliance_name"] == "WRÓG"

    def test_ignores_disappeared_player(self, app, db_session):
        """Gracz znika — nie raportuj jako zmiana sojuszu."""
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="Zniknięty",
                                     aid=1, alliance_name="NASI", population=500))
        # Inna wioska obecna w obu snapshotach
        db_session.add(_make_village(2, s1.id, uid=20, player_name="Inny",
                                     aid=1, alliance_name="NASI", population=200, x=5, y=5))
        db_session.add(_make_village(2, s2.id, uid=20, player_name="Inny",
                                     aid=1, alliance_name="NASI", population=200, x=5, y=5))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        changes = [a for a in alerts if a["type"] == "alliance_change"]
        assert len(changes) == 0

    def test_ignores_same_alliance(self, app, db_session):
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="Stały",
                                     aid=1, alliance_name="NASI", population=500))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Stały",
                                     aid=1, alliance_name="NASI", population=510))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        changes = [a for a in alerts if a["type"] == "alliance_change"]
        assert len(changes) == 0

    def test_detects_switch_between_allied_alliances(self, app, db_session):
        """Zmiana między naszymi sojuszami — aid zmieniony, ale oba w our_alliances.
        Gracz opuścił nasz sojusz 1 ale dołączył do sojuszu 2 (też nasz) — nie jest joined_enemy."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="Transfer",
                                     aid=1, alliance_name="NASI-A", population=500))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Transfer",
                                     aid=2, alliance_name="NASI-B", population=500))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(our_alliances=[1, 2]))
        changes = [a for a in alerts if a["type"] == "alliance_change"]
        assert len(changes) == 1
        assert changes[0]["change_type"] == "switch"
        assert changes[0]["old_alliance_name"] == "NASI-A"
        assert changes[0]["new_alliance_name"] == "NASI-B"


# ------------------------------------------------------------------ #
# Integration: detect_alerts with no prior data
# ------------------------------------------------------------------ #
class TestDetectAlertsEdgeCases:
    def test_no_villages(self, app, db_session):
        s1 = Snapshot(village_count=0)
        s2 = Snapshot(village_count=0)
        db_session.add_all([s1, s2])
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        assert alerts == []

    def test_no_our_alliances(self, app, db_session):
        """Bez skonfigurowanych sojuszów — brak alertów pop/new_village."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="G",
                                     aid=99, alliance_name="X", population=1000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="G",
                                     aid=99, alliance_name="X", population=100))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(our_alliances=[]))
        # Pop drop: gracz nie w naszym sojuszu, brak ally_positions → nie bliski
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 0


# ------------------------------------------------------------------ #
# Alert model
# ------------------------------------------------------------------ #
class TestAlertModel:
    def test_create_and_query(self, app, db_session):
        s = Snapshot(village_count=0)
        db_session.add(s)
        db_session.flush()

        alert = Alert(
            snapshot_id=s.id,
            alert_type="pop_drop",
            data=json.dumps({"player": "test"}),
        )
        db_session.add(alert)
        db_session.commit()

        result = Alert.query.filter_by(notified=False).all()
        assert len(result) == 1
        assert result[0].alert_type == "pop_drop"
        assert json.loads(result[0].data)["player"] == "test"

    def test_mark_notified(self, app, db_session):
        s = Snapshot(village_count=0)
        db_session.add(s)
        db_session.flush()

        alert = Alert(snapshot_id=s.id, alert_type="test", data="{}")
        db_session.add(alert)
        db_session.commit()

        alert.notified = True
        db_session.commit()

        pending = Alert.query.filter_by(notified=False).count()
        assert pending == 0


# ------------------------------------------------------------------ #
# Snapshot validation
# ------------------------------------------------------------------ #
class TestSnapshotValidation:
    def test_truncated_snapshot_suppresses_alerts(self, app, db_session):
        """Snapshot z < 50% wiosek poprzedniego → brak alertów."""
        s1 = Snapshot(village_count=1000)
        s2 = Snapshot(village_count=100)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Gracz z ogromnym spadkiem — normalnie byłby alert
        db_session.add(_make_village(1, s1.id, uid=10, player_name="Gracz",
                                      aid=1, alliance_name="NASI", population=5000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Gracz",
                                      aid=1, alliance_name="NASI", population=100))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        assert alerts == []

    def test_valid_snapshot_allows_alerts(self, app, db_session):
        """Snapshot z >= 50% wiosek → alerty przechodzą normalnie."""
        s1 = Snapshot(village_count=1000)
        s2 = Snapshot(village_count=900)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="Gracz",
                                      aid=1, alliance_name="NASI", population=1000))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Gracz",
                                      aid=1, alliance_name="NASI", population=500))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config(threshold=15))
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        assert len(pop_drops) == 1

    def test_validate_returns_false_for_missing_snapshot(self, app, db_session):
        """Brak snapshotu → validate zwraca False."""
        assert validate_snapshot_pair(999, 998) is False

    def test_validate_prev_zero_count(self, app, db_session):
        """Poprzedni snapshot z 0 wiosek → brak bazy porównawczej → True."""
        s1 = Snapshot(village_count=0)
        s2 = Snapshot(village_count=100)
        db_session.add_all([s1, s2])
        db_session.commit()

        assert validate_snapshot_pair(s2.id, s1.id) is True


# ------------------------------------------------------------------ #
# Alliance change — neutral handling
# ------------------------------------------------------------------ #
class TestAllianceNeutralHandling:
    def test_switch_to_neutral_ignored_for_non_ally(self, app, db_session):
        """Gracz obcy przechodzi z wroga na neutralny (aid=0) — nie alertuj."""
        s1 = Snapshot(village_count=2)
        s2 = Snapshot(village_count=2)
        db_session.add_all([s1, s2])
        db_session.flush()

        # Gracz wroga przechodzi na neutralny — blisko nas
        db_session.add(_make_village(1, s1.id, uid=10, player_name="ExWróg",
                                      aid=99, alliance_name="WRÓG", population=500,
                                      x=5, y=5))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="ExWróg",
                                      aid=0, alliance_name="", population=500,
                                      x=5, y=5))
        # Nasza wioska w pobliżu
        db_session.add(_make_village(2, s1.id, uid=20, player_name="Nasz",
                                      aid=1, alliance_name="NASI", population=300,
                                      x=0, y=0))
        db_session.add(_make_village(2, s2.id, uid=20, player_name="Nasz",
                                      aid=1, alliance_name="NASI", population=300,
                                      x=0, y=0))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        changes = [a for a in alerts if a["type"] == "alliance_change"]
        assert len(changes) == 0

    def test_leave_our_alliance_to_neutral_detected(self, app, db_session):
        """Gracz opuszcza NASZ sojusz na neutralny (aid=0) — alertuj jako leave."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="Odchodzący",
                                      aid=1, alliance_name="NASI", population=500))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Odchodzący",
                                      aid=0, alliance_name="", population=500))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        changes = [a for a in alerts if a["type"] == "alliance_change"]
        assert len(changes) == 1
        assert changes[0]["change_type"] == "leave"
        assert changes[0]["old_alliance_name"] == "NASI"

    def test_join_our_alliance_from_neutral(self, app, db_session):
        """Gracz dołącza do NASZEGO sojuszu z neutralnego — alertuj jako join."""
        s1 = Snapshot(village_count=1)
        s2 = Snapshot(village_count=1)
        db_session.add_all([s1, s2])
        db_session.flush()

        db_session.add(_make_village(1, s1.id, uid=10, player_name="Nowy",
                                      aid=0, alliance_name="", population=500))
        db_session.add(_make_village(1, s2.id, uid=10, player_name="Nowy",
                                      aid=1, alliance_name="NASI", population=500))
        db_session.commit()

        alerts = detect_alerts(s2.id, s1.id, _config())
        changes = [a for a in alerts if a["type"] == "alliance_change"]
        assert len(changes) == 1
        assert changes[0]["change_type"] == "join"
        assert changes[0]["new_alliance_name"] == "NASI"
