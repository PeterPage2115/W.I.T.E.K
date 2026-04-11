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
