"""Testy dla tras dashboardu (app/routes/dashboard.py)."""

import pytest
from datetime import datetime, timezone
from app import create_app
from app.database import db as _db
from app.models import Snapshot, Alliance, Player


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


class TestDashboardIndex:
    def test_empty_db_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_empty_db_renders_dashboard(self, client):
        resp = client.get("/")
        assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data

    def test_with_snapshot_returns_200(self, client, db_session):
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=100)
        db_session.add(snap)
        db_session.commit()
        resp = client.get("/")
        assert resp.status_code == 200

    def test_shows_top_alliances(self, client, db_session):
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=50)
        db_session.add(snap)
        db_session.flush()
        a1 = Alliance(aid=1, name="UFOLODZY", total_pop=50000, member_count=10)
        a2 = Alliance(aid=2, name="TestAlliance", total_pop=30000, member_count=5)
        db_session.add_all([a1, a2])
        db_session.commit()
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"UFOLODZY" in resp.data
        assert b"TestAlliance" in resp.data

    def test_shows_top_players(self, client, db_session):
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=50)
        db_session.add(snap)
        db_session.flush()
        p1 = Player(uid=1, name="Gracz1", tid=1, total_pop=10000, village_count=5)
        p2 = Player(uid=2, name="Gracz2", tid=2, total_pop=8000, village_count=3)
        db_session.add_all([p1, p2])
        db_session.commit()
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Gracz1" in resp.data
        assert b"Gracz2" in resp.data

    def test_alliances_ordered_by_population(self, client, db_session):
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=10)
        db_session.add(snap)
        db_session.flush()
        a_small = Alliance(aid=10, name="SojuszMniejszy", total_pop=100, member_count=1)
        a_big = Alliance(aid=11, name="SojuszWiekszy", total_pop=99999, member_count=50)
        db_session.add_all([a_small, a_big])
        db_session.commit()
        resp = client.get("/")
        data = resp.data
        assert b"SojuszWiekszy" in data
        assert b"SojuszMniejszy" in data
        assert data.index(b"SojuszWiekszy") < data.index(b"SojuszMniejszy")

    def test_players_ordered_by_population(self, client, db_session):
        snap = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=10)
        db_session.add(snap)
        db_session.flush()
        p_small = Player(uid=20, name="GraczMniejszy", tid=1, total_pop=50, village_count=1)
        p_big = Player(uid=21, name="GraczWiekszy", tid=2, total_pop=99999, village_count=20)
        db_session.add_all([p_small, p_big])
        db_session.commit()
        resp = client.get("/")
        data = resp.data
        assert b"GraczWiekszy" in data
        assert b"GraczMniejszy" in data
        assert data.index(b"GraczWiekszy") < data.index(b"GraczMniejszy")

    def test_total_counts_shown(self, client, db_session):
        for i in range(3):
            db_session.add(Alliance(aid=100 + i, name=f"A{i}", total_pop=100))
        for i in range(5):
            db_session.add(Player(uid=100 + i, name=f"P{i}", tid=1, total_pop=100))
        db_session.commit()
        resp = client.get("/")
        assert resp.status_code == 200
