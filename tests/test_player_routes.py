"""Testy dla tras gracza (app/routes/players.py)."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from app import create_app
from app.database import db as _db
from app.models import Snapshot, Village, Player


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


class TestPlayerProfile:
    def test_nonexistent_player_returns_404(self, client):
        resp = client.get("/player/9999")
        assert resp.status_code == 404

    def test_existing_player_returns_200(self, client, db_session):
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=10)
        db_session.add(snap)
        db_session.flush()
        player = Player(uid=1, name="TestGracz", tid=3, total_pop=500, village_count=2)
        db_session.add(player)
        db_session.commit()
        resp = client.get("/player/1")
        assert resp.status_code == 200
        assert b"TestGracz" in resp.data

    def test_player_with_villages(self, client, db_session):
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=10)
        db_session.add(snap)
        db_session.flush()
        player = Player(uid=5, name="Wioska", tid=1, total_pop=800, village_count=2)
        v1 = Village(
            map_id=1, snapshot_id=snap.id, x=10, y=20, tid=1, vid=100,
            name="Wioska1", uid=5, player_name="Wioska", aid=1,
            alliance_name="ALI", population=500,
        )
        v2 = Village(
            map_id=2, snapshot_id=snap.id, x=11, y=21, tid=1, vid=101,
            name="Wioska2", uid=5, player_name="Wioska", aid=1,
            alliance_name="ALI", population=300,
        )
        db_session.add_all([player, v1, v2])
        db_session.commit()
        resp = client.get("/player/5")
        assert resp.status_code == 200
        assert b"Wioska1" in resp.data
        assert b"Wioska2" in resp.data

    def test_player_shows_tribe_name(self, client, db_session):
        player = Player(uid=7, name="Galijski", tid=3, total_pop=100, village_count=1)
        db_session.add(player)
        db_session.commit()
        resp = client.get("/player/7")
        assert resp.status_code == 200


class TestPlayerPopulationAPI:
    def test_nonexistent_player_returns_404(self, client):
        resp = client.get("/api/player/9999/population")
        assert resp.status_code == 404

    def test_existing_player_returns_json(self, client, db_session):
        player = Player(uid=10, name="ApiGracz", tid=2, total_pop=1000, village_count=1)
        db_session.add(player)
        db_session.commit()
        resp = client.get("/api/player/10/population")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["player"] == "ApiGracz"
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_population_history_with_snapshots(self, client, db_session):
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(hours=2), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        player = Player(uid=15, name="Historia", tid=1, total_pop=700, village_count=2)
        db_session.add(player)

        v1 = Village(
            map_id=10, snapshot_id=snap1.id, x=0, y=0, tid=1, vid=200,
            name="V1", uid=15, player_name="Historia", aid=1,
            alliance_name="A", population=300,
        )
        v2 = Village(
            map_id=11, snapshot_id=snap1.id, x=1, y=1, tid=1, vid=201,
            name="V2", uid=15, player_name="Historia", aid=1,
            alliance_name="A", population=200,
        )
        v3 = Village(
            map_id=10, snapshot_id=snap2.id, x=0, y=0, tid=1, vid=200,
            name="V1", uid=15, player_name="Historia", aid=1,
            alliance_name="A", population=400,
        )
        v4 = Village(
            map_id=11, snapshot_id=snap2.id, x=1, y=1, tid=1, vid=201,
            name="V2", uid=15, player_name="Historia", aid=1,
            alliance_name="A", population=300,
        )
        db_session.add_all([v1, v2, v3, v4])
        db_session.commit()

        resp = client.get("/api/player/15/population")
        data = resp.get_json()
        assert len(data["history"]) == 2
        assert data["history"][0]["total_pop"] == 500
        assert data["history"][0]["villages"] == 2
        assert data["history"][1]["total_pop"] == 700
        assert data["history"][1]["villages"] == 2

    def test_population_history_empty_for_player_without_villages(self, client, db_session):
        player = Player(uid=20, name="Pusty", tid=1, total_pop=0, village_count=0)
        db_session.add(player)
        db_session.commit()
        resp = client.get("/api/player/20/population")
        data = resp.get_json()
        assert data["history"] == []

    def test_population_api_returns_correct_date_format(self, client, db_session):
        now = datetime.now(timezone.utc)
        snap = Snapshot(fetched_at=now, village_count=1)
        db_session.add(snap)
        db_session.flush()
        player = Player(uid=25, name="Date", tid=1, total_pop=100, village_count=1)
        v = Village(
            map_id=30, snapshot_id=snap.id, x=5, y=5, tid=1, vid=300,
            name="V", uid=25, player_name="Date", aid=1,
            alliance_name="A", population=100,
        )
        db_session.add_all([player, v])
        db_session.commit()
        resp = client.get("/api/player/25/population")
        data = resp.get_json()
        assert len(data["history"]) == 1
        # ISO 8601 date format
        assert "T" in data["history"][0]["date"]


class TestPlayerActivity:
    """Tests for player activity detection on profile page."""

    def test_active_player_shows_green_badge(self, client, db_session):
        """Player with pop change in last 3 snapshots = Aktywny."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=2), village_count=10)
        snap2 = Snapshot(fetched_at=now - timedelta(days=1), village_count=10)
        snap3 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2, snap3])
        db_session.flush()

        player = Player(uid=100, name="AktywnyGracz", tid=1, total_pop=600, village_count=1)
        db_session.add(player)

        for snap, pop in [(snap1, 200), (snap2, 400), (snap3, 600)]:
            db_session.add(Village(
                map_id=1, snapshot_id=snap.id, x=0, y=0, tid=1, vid=100,
                name="V1", uid=100, player_name="AktywnyGracz", aid=1,
                alliance_name="A", population=pop,
            ))
        db_session.commit()

        resp = client.get("/player/100")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Aktywny" in html
        assert "\U0001f7e2" in html  # 🟢

    def test_inactive_player_shows_red_badge(self, client, db_session):
        """Player with no pop change in last 3 snapshots = Nieaktywny."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=2), village_count=10)
        snap2 = Snapshot(fetched_at=now - timedelta(days=1), village_count=10)
        snap3 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2, snap3])
        db_session.flush()

        player = Player(uid=101, name="Leniwy", tid=2, total_pop=300, village_count=1)
        db_session.add(player)

        for snap in [snap1, snap2, snap3]:
            db_session.add(Village(
                map_id=2, snapshot_id=snap.id, x=5, y=5, tid=2, vid=200,
                name="V2", uid=101, player_name="Leniwy", aid=1,
                alliance_name="A", population=300,
            ))
        db_session.commit()

        resp = client.get("/player/101")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Nieaktywny" in html
        assert "\U0001f534" in html  # 🔴

    def test_new_player_shows_yellow_badge(self, client, db_session):
        """Player with only 1 snapshot = Nowy gracz."""
        now = datetime.now(timezone.utc)
        snap = Snapshot(fetched_at=now, village_count=10)
        db_session.add(snap)
        db_session.flush()

        player = Player(uid=102, name="NowyGracz", tid=3, total_pop=100, village_count=1)
        db_session.add(player)
        db_session.add(Village(
            map_id=3, snapshot_id=snap.id, x=10, y=10, tid=3, vid=300,
            name="V3", uid=102, player_name="NowyGracz", aid=0,
            alliance_name="", population=100,
        ))
        db_session.commit()

        resp = client.get("/player/102")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Nowy" in html
        assert "\U0001f7e1" in html  # 🟡

    def test_pop_change_display_positive(self, client, db_session):
        """Positive pop change shows green arrow ▲."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=3), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        player = Player(uid=103, name="Rosnacy", tid=1, total_pop=500, village_count=1)
        db_session.add(player)
        db_session.add(Village(
            map_id=4, snapshot_id=snap1.id, x=0, y=0, tid=1, vid=400,
            name="V4", uid=103, player_name="Rosnacy", aid=1,
            alliance_name="A", population=200,
        ))
        db_session.add(Village(
            map_id=4, snapshot_id=snap2.id, x=0, y=0, tid=1, vid=400,
            name="V4", uid=103, player_name="Rosnacy", aid=1,
            alliance_name="A", population=500,
        ))
        db_session.commit()

        resp = client.get("/player/103")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "▲" in html
        assert "+300" in html

    def test_pop_change_display_negative(self, client, db_session):
        """Negative pop change shows red arrow ▼."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=3), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        player = Player(uid=104, name="Spadajacy", tid=2, total_pop=100, village_count=1)
        db_session.add(player)
        db_session.add(Village(
            map_id=5, snapshot_id=snap1.id, x=1, y=1, tid=2, vid=500,
            name="V5", uid=104, player_name="Spadajacy", aid=1,
            alliance_name="A", population=400,
        ))
        db_session.add(Village(
            map_id=5, snapshot_id=snap2.id, x=1, y=1, tid=2, vid=500,
            name="V5", uid=104, player_name="Spadajacy", aid=1,
            alliance_name="A", population=100,
        ))
        db_session.commit()

        resp = client.get("/player/104")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "▼" in html
        assert "-300" in html

    def test_single_snapshot_no_crash(self, client, db_session):
        """Profile with only one snapshot doesn't crash."""
        now = datetime.now(timezone.utc)
        snap = Snapshot(fetched_at=now, village_count=5)
        db_session.add(snap)
        db_session.flush()

        player = Player(uid=105, name="Solo", tid=3, total_pop=250, village_count=1)
        db_session.add(player)
        db_session.add(Village(
            map_id=6, snapshot_id=snap.id, x=2, y=2, tid=3, vid=600,
            name="V6", uid=105, player_name="Solo", aid=0,
            alliance_name="", population=250,
        ))
        db_session.commit()

        resp = client.get("/player/105")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Solo" in html

    def test_no_snapshots_no_crash(self, client, db_session):
        """Profile for player with no villages in any snapshot doesn't crash."""
        player = Player(uid=106, name="Pusty", tid=1, total_pop=0, village_count=0)
        db_session.add(player)
        db_session.commit()

        resp = client.get("/player/106")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Pusty" in html

    def test_first_seen_date_displayed(self, client, db_session):
        """First seen date is displayed on the profile."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=5), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        player = Player(uid=107, name="Stary", tid=1, total_pop=800, village_count=1)
        db_session.add(player)
        for snap, pop in [(snap1, 400), (snap2, 800)]:
            db_session.add(Village(
                map_id=7, snapshot_id=snap.id, x=3, y=3, tid=1, vid=700,
                name="V7", uid=107, player_name="Stary", aid=1,
                alliance_name="A", population=pop,
            ))
        db_session.commit()

        resp = client.get("/player/107")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "Pierwszy snapshot" in html

    def test_avg_daily_growth_displayed(self, client, db_session):
        """Average daily growth is displayed when history exists."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=10), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        player = Player(uid=108, name="Rosnie", tid=2, total_pop=600, village_count=1)
        db_session.add(player)
        db_session.add(Village(
            map_id=8, snapshot_id=snap1.id, x=4, y=4, tid=2, vid=800,
            name="V8", uid=108, player_name="Rosnie", aid=1,
            alliance_name="A", population=100,
        ))
        db_session.add(Village(
            map_id=8, snapshot_id=snap2.id, x=4, y=4, tid=2, vid=800,
            name="V8", uid=108, player_name="Rosnie", aid=1,
            alliance_name="A", population=600,
        ))
        db_session.commit()

        resp = client.get("/player/108")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "Średni dzienny wzrost" in html
