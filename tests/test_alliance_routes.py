"""Testy dla tras sojuszu (app/routes/alliances.py)."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from app import create_app
from app.database import db as _db
from app.models import Snapshot, Village, Player, Alliance


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
    EXT_API_TOKEN = "test-token"
    SECRET_KEY = "test-secret"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield _db.session


class TestAllianceProfile:
    def test_nonexistent_alliance_returns_404(self, client):
        resp = client.get("/alliance/9999")
        assert resp.status_code == 404

    def test_existing_alliance_returns_200(self, client, db_session):
        alliance = Alliance(aid=1, name="UFOLODZY", total_pop=50000, member_count=10)
        db_session.add(alliance)
        db_session.commit()
        resp = client.get("/alliance/1")
        assert resp.status_code == 200
        assert b"UFOLODZY" in resp.data

    def test_alliance_with_members(self, client, db_session):
        alliance = Alliance(aid=5, name="TestSojusz", total_pop=2000, member_count=2)
        p1 = Player(uid=1, name="Czlonek1", tid=1, aid=5, total_pop=1200, village_count=3)
        p2 = Player(uid=2, name="Czlonek2", tid=2, aid=5, total_pop=800, village_count=2)
        db_session.add_all([alliance, p1, p2])
        db_session.commit()
        resp = client.get("/alliance/5")
        assert resp.status_code == 200
        assert b"Czlonek1" in resp.data
        assert b"Czlonek2" in resp.data

    def test_alliance_with_villages(self, client, db_session):
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=5)
        db_session.add(snap)
        db_session.flush()
        alliance = Alliance(aid=8, name="WioskiSojusz", total_pop=1000, member_count=1)
        p = Player(uid=1, name="GraczWioskowy", tid=1, aid=8, total_pop=500, village_count=1)
        v = Village(
            map_id=1, snapshot_id=snap.id, x=10, y=20, tid=1, vid=100,
            name="SojuszWioska", uid=1, player_name="GraczWioskowy", aid=8,
            alliance_name="WioskiSojusz", population=500,
        )
        db_session.add_all([alliance, p, v])
        db_session.commit()
        resp = client.get("/alliance/8")
        assert resp.status_code == 200
        assert b"WioskiSojusz" in resp.data
        assert b"GraczWioskowy" in resp.data

    def test_members_ordered_by_population(self, client, db_session):
        alliance = Alliance(aid=12, name="Kolejnosc", total_pop=3000, member_count=2)
        p_small = Player(uid=30, name="Mniejszy", tid=1, aid=12, total_pop=500, village_count=1)
        p_big = Player(uid=31, name="Wiekszy", tid=2, aid=12, total_pop=2500, village_count=5)
        db_session.add_all([alliance, p_small, p_big])
        db_session.commit()
        resp = client.get("/alliance/12")
        data = resp.data
        assert data.index(b"Wiekszy") < data.index(b"Mniejszy")


class TestAlliancePopulationAPI:
    def test_nonexistent_alliance_returns_404(self, client):
        resp = client.get("/api/alliance/9999/population")
        assert resp.status_code == 404

    def test_existing_alliance_returns_json(self, client, db_session):
        alliance = Alliance(aid=20, name="ApiSojusz", total_pop=5000, member_count=3)
        db_session.add(alliance)
        db_session.commit()
        resp = client.get("/api/alliance/20/population")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["alliance"] == "ApiSojusz"
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_population_history_with_snapshots(self, client, db_session):
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(hours=2), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        alliance = Alliance(aid=25, name="HistSojusz", total_pop=1500, member_count=2)
        db_session.add(alliance)

        v1 = Village(
            map_id=50, snapshot_id=snap1.id, x=0, y=0, tid=1, vid=500,
            name="V1", uid=40, player_name="P1", aid=25,
            alliance_name="HistSojusz", population=400,
        )
        v2 = Village(
            map_id=51, snapshot_id=snap1.id, x=1, y=1, tid=2, vid=501,
            name="V2", uid=41, player_name="P2", aid=25,
            alliance_name="HistSojusz", population=300,
        )
        v3 = Village(
            map_id=50, snapshot_id=snap2.id, x=0, y=0, tid=1, vid=500,
            name="V1", uid=40, player_name="P1", aid=25,
            alliance_name="HistSojusz", population=500,
        )
        v4 = Village(
            map_id=51, snapshot_id=snap2.id, x=1, y=1, tid=2, vid=501,
            name="V2", uid=41, player_name="P2", aid=25,
            alliance_name="HistSojusz", population=400,
        )
        db_session.add_all([v1, v2, v3, v4])
        db_session.commit()

        resp = client.get("/api/alliance/25/population")
        data = resp.get_json()
        assert len(data["history"]) == 2
        assert data["history"][0]["total_pop"] == 700
        assert data["history"][0]["members"] == 2
        assert data["history"][1]["total_pop"] == 900
        assert data["history"][1]["members"] == 2

    def test_population_history_empty_without_villages(self, client, db_session):
        alliance = Alliance(aid=30, name="Pusty", total_pop=0, member_count=0)
        db_session.add(alliance)
        db_session.commit()
        resp = client.get("/api/alliance/30/population")
        data = resp.get_json()
        assert data["history"] == []

    def test_population_api_date_format(self, client, db_session):
        now = datetime.now(timezone.utc)
        snap = Snapshot(fetched_at=now, village_count=1)
        db_session.add(snap)
        db_session.flush()
        alliance = Alliance(aid=35, name="DataSojusz", total_pop=100, member_count=1)
        v = Village(
            map_id=60, snapshot_id=snap.id, x=5, y=5, tid=1, vid=600,
            name="V", uid=50, player_name="P", aid=35,
            alliance_name="DataSojusz", population=100,
        )
        db_session.add_all([alliance, v])
        db_session.commit()
        resp = client.get("/api/alliance/35/population")
        data = resp.get_json()
        assert len(data["history"]) == 1
        assert "T" in data["history"][0]["date"]


class TestAllianceHistoryAPI:
    """Tests for /api/alliance/<aid>/history endpoint."""

    def test_nonexistent_alliance_returns_404(self, client):
        resp = client.get("/api/alliance/9999/history")
        assert resp.status_code == 404

    def test_returns_json_array(self, client, db_session):
        alliance = Alliance(aid=40, name="HistArr", total_pop=0, member_count=0)
        db_session.add(alliance)
        db_session.commit()
        resp = client.get("/api/alliance/40/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert data == []

    def test_history_with_snapshots(self, client, db_session):
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(hours=2), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        alliance = Alliance(aid=41, name="TrendSojusz", total_pop=900, member_count=2)
        db_session.add(alliance)

        for snap, p1pop, p2pop in [(snap1, 400, 300), (snap2, 500, 400)]:
            db_session.add(Village(
                map_id=50, snapshot_id=snap.id, x=0, y=0, tid=1, vid=500,
                name="V1", uid=60, player_name="P1", aid=41,
                alliance_name="TrendSojusz", population=p1pop,
            ))
            db_session.add(Village(
                map_id=51, snapshot_id=snap.id, x=1, y=1, tid=2, vid=501,
                name="V2", uid=61, player_name="P2", aid=41,
                alliance_name="TrendSojusz", population=p2pop,
            ))
        db_session.commit()

        resp = client.get("/api/alliance/41/history")
        data = resp.get_json()
        assert len(data) == 2
        assert data[0]["total_pop"] == 700
        assert data[0]["player_count"] == 2
        assert data[1]["total_pop"] == 900
        assert data[1]["player_count"] == 2

    def test_history_date_format(self, client, db_session):
        now = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        snap = Snapshot(fetched_at=now, village_count=1)
        db_session.add(snap)
        db_session.flush()
        alliance = Alliance(aid=42, name="DateSojusz", total_pop=100, member_count=1)
        db_session.add(alliance)
        db_session.add(Village(
            map_id=70, snapshot_id=snap.id, x=0, y=0, tid=1, vid=700,
            name="V", uid=70, player_name="P", aid=42,
            alliance_name="DateSojusz", population=100,
        ))
        db_session.commit()
        resp = client.get("/api/alliance/42/history")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["date"] == "2024-06-15 14:30"

    def test_history_has_correct_keys(self, client, db_session):
        now = datetime.now(timezone.utc)
        snap = Snapshot(fetched_at=now, village_count=1)
        db_session.add(snap)
        db_session.flush()
        alliance = Alliance(aid=43, name="Keys", total_pop=100, member_count=1)
        db_session.add(alliance)
        db_session.add(Village(
            map_id=80, snapshot_id=snap.id, x=0, y=0, tid=1, vid=800,
            name="V", uid=80, player_name="P", aid=43,
            alliance_name="Keys", population=100,
        ))
        db_session.commit()
        resp = client.get("/api/alliance/43/history")
        data = resp.get_json()
        assert set(data[0].keys()) == {"date", "total_pop", "player_count"}


class TestAllianceMemberPopChange:
    """Tests for member pop change indicators on alliance profile."""

    def test_pop_change_positive(self, client, db_session):
        """Member with population increase shows ▲."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(hours=2), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        alliance = Alliance(aid=50, name="ChangeUp", total_pop=500, member_count=1)
        p = Player(uid=90, name="Rosnacy", tid=1, aid=50, total_pop=500, village_count=1)
        db_session.add_all([alliance, p])

        db_session.add(Village(
            map_id=90, snapshot_id=snap1.id, x=0, y=0, tid=1, vid=900,
            name="V1", uid=90, player_name="Rosnacy", aid=50,
            alliance_name="ChangeUp", population=300,
        ))
        db_session.add(Village(
            map_id=90, snapshot_id=snap2.id, x=0, y=0, tid=1, vid=900,
            name="V1", uid=90, player_name="Rosnacy", aid=50,
            alliance_name="ChangeUp", population=500,
        ))
        db_session.commit()

        resp = client.get("/alliance/50")
        html = resp.data.decode()
        assert "▲" in html
        assert "+200" in html

    def test_pop_change_negative(self, client, db_session):
        """Member with population decrease shows ▼."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(hours=2), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        alliance = Alliance(aid=51, name="ChangeDown", total_pop=200, member_count=1)
        p = Player(uid=91, name="Spadajacy", tid=2, aid=51, total_pop=200, village_count=1)
        db_session.add_all([alliance, p])

        db_session.add(Village(
            map_id=91, snapshot_id=snap1.id, x=1, y=1, tid=2, vid=901,
            name="V1", uid=91, player_name="Spadajacy", aid=51,
            alliance_name="ChangeDown", population=500,
        ))
        db_session.add(Village(
            map_id=91, snapshot_id=snap2.id, x=1, y=1, tid=2, vid=901,
            name="V1", uid=91, player_name="Spadajacy", aid=51,
            alliance_name="ChangeDown", population=200,
        ))
        db_session.commit()

        resp = client.get("/alliance/51")
        html = resp.data.decode()
        assert "▼" in html
        assert "-300" in html

    def test_no_change_shows_dash(self, client, db_session):
        """Member with no population change shows dash."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(hours=2), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        alliance = Alliance(aid=52, name="NoChange", total_pop=300, member_count=1)
        p = Player(uid=92, name="Stabilny", tid=3, aid=52, total_pop=300, village_count=1)
        db_session.add_all([alliance, p])

        for snap in [snap1, snap2]:
            db_session.add(Village(
                map_id=92, snapshot_id=snap.id, x=2, y=2, tid=3, vid=902,
                name="V1", uid=92, player_name="Stabilny", aid=52,
                alliance_name="NoChange", population=300,
            ))
        db_session.commit()

        resp = client.get("/alliance/52")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "Stabilny" in html

    def test_single_snapshot_no_pop_change(self, client, db_session):
        """With only one snapshot, no pop change indicators appear."""
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=5)
        db_session.add(snap)
        db_session.flush()

        alliance = Alliance(aid=53, name="SingleSnap", total_pop=100, member_count=1)
        p = Player(uid=93, name="NowyGracz", tid=1, aid=53, total_pop=100, village_count=1)
        db_session.add_all([alliance, p])
        db_session.add(Village(
            map_id=93, snapshot_id=snap.id, x=3, y=3, tid=1, vid=903,
            name="V1", uid=93, player_name="NowyGracz", aid=53,
            alliance_name="SingleSnap", population=100,
        ))
        db_session.commit()

        resp = client.get("/alliance/53")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "NowyGracz" in html
        assert "▲" not in html
        assert "▼" not in html

    def test_chart_canvas_rendered(self, client, db_session):
        """Alliance page renders both chart canvases."""
        alliance = Alliance(aid=54, name="ChartTest", total_pop=0, member_count=0)
        db_session.add(alliance)
        db_session.commit()
        resp = client.get("/alliance/54")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'id="popChart"' in html
        assert 'id="membersChart"' in html
        assert "/api/alliance/54/history" in html or "aid + '/history'" in html
