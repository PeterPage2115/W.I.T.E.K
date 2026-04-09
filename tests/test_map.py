"""Tests for the interactive 2D map (S4.5)."""

import json
import pytest
from app import create_app
from app.database import db as _db
from app.models import Snapshot, Village


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
def client(app):
    return app.test_client()


@pytest.fixture
def snapshot(app):
    with app.app_context():
        s = Snapshot(village_count=3)
        _db.session.add(s)
        _db.session.commit()
        yield s


def _make_village(map_id, snapshot_id, x, y, uid, player_name, aid,
                  alliance_name, population, tid=1, name="Wioska"):
    return Village(
        map_id=map_id,
        snapshot_id=snapshot_id,
        x=x, y=y, tid=tid,
        vid=map_id, name=name,
        uid=uid, player_name=player_name,
        aid=aid, alliance_name=alliance_name,
        population=population,
    )


# ------------------------------------------------------------------ #
# Map page route
# ------------------------------------------------------------------ #
class TestMapView:
    def test_map_returns_200_empty_db(self, client):
        resp = client.get("/map")
        assert resp.status_code == 200
        assert "Mapa świata" in resp.data.decode("utf-8")

    def test_map_returns_200_with_snapshot(self, client, snapshot):
        resp = client.get("/map")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Mapa świata" in html
        assert "leaflet" in html.lower()

    def test_map_contains_legend(self, client):
        resp = client.get("/map")
        html = resp.data.decode("utf-8")
        assert "Legenda" in html
        assert "Nasz sojusz" in html

    def test_map_contains_search(self, client):
        resp = client.get("/map")
        html = resp.data.decode("utf-8")
        assert "search-input" in html

    def test_map_nav_link_present(self, client):
        resp = client.get("/map")
        html = resp.data.decode("utf-8")
        assert "Mapa" in html


# ------------------------------------------------------------------ #
# API: /api/map/villages
# ------------------------------------------------------------------ #
class TestApiVillages:
    def test_no_snapshot_returns_empty(self, client):
        resp = client.get("/api/map/villages")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data == []

    def test_returns_villages(self, app, client, snapshot):
        with app.app_context():
            _db.session.add_all([
                _make_village(1, snapshot.id, 10, 20, 100, "Player1", 1, "UFOLODZY", 500),
                _make_village(2, snapshot.id, -5, 15, 101, "Player2", 3, "Enemy", 300),
                _make_village(3, snapshot.id, 0, 0, 102, "Player3", 0, "", 100),
            ])
            _db.session.commit()

        resp = client.get("/api/map/villages")
        data = json.loads(resp.data)
        assert len(data) == 3

    def test_village_json_structure(self, app, client, snapshot):
        with app.app_context():
            _db.session.add(
                _make_village(1, snapshot.id, 42, -13, 100, "Gracz", 1, "UFOLODZY", 750, tid=2, name="Twierdza")
            )
            _db.session.commit()

        resp = client.get("/api/map/villages")
        data = json.loads(resp.data)
        assert len(data) == 1
        v = data[0]
        assert v["x"] == 42
        assert v["y"] == -13
        assert v["name"] == "Twierdza"
        assert v["player"] == "Gracz"
        assert v["alliance"] == "UFOLODZY"
        assert v["aid"] == 1
        assert v["pop"] == 750
        assert v["tid"] == 2
        assert "is_ours" in v

    def test_is_ours_flag(self, app, client, snapshot):
        with app.app_context():
            _db.session.add_all([
                _make_village(1, snapshot.id, 0, 0, 10, "Nasz", 1, "UFOLODZY", 100),
                _make_village(2, snapshot.id, 1, 1, 11, "Nasz2", 2, "UFOLODZY2", 200),
                _make_village(3, snapshot.id, 2, 2, 12, "Wrog", 5, "Enemy", 300),
                _make_village(4, snapshot.id, 3, 3, 13, "Neutral", 0, "", 50),
            ])
            _db.session.commit()

        resp = client.get("/api/map/villages")
        data = json.loads(resp.data)
        by_player = {v["player"]: v for v in data}

        assert by_player["Nasz"]["is_ours"] is True
        assert by_player["Nasz2"]["is_ours"] is True
        assert by_player["Wrog"]["is_ours"] is False
        assert by_player["Neutral"]["is_ours"] is False

    def test_bounding_box_filter(self, app, client, snapshot):
        with app.app_context():
            _db.session.add_all([
                _make_village(1, snapshot.id, 10, 10, 100, "Inside", 0, "", 100),
                _make_village(2, snapshot.id, 50, 50, 101, "Outside", 0, "", 100),
                _make_village(3, snapshot.id, -100, -100, 102, "FarOut", 0, "", 100),
            ])
            _db.session.commit()

        resp = client.get("/api/map/villages?x_min=0&x_max=20&y_min=0&y_max=20")
        data = json.loads(resp.data)
        assert len(data) == 1
        assert data[0]["player"] == "Inside"

    def test_alliance_name_filter(self, app, client, snapshot):
        with app.app_context():
            _db.session.add_all([
                _make_village(1, snapshot.id, 0, 0, 100, "P1", 1, "UFOLODZY", 100),
                _make_village(2, snapshot.id, 1, 1, 101, "P2", 3, "Enemy", 100),
            ])
            _db.session.commit()

        resp = client.get("/api/map/villages?alliance=UFOLODZY")
        data = json.loads(resp.data)
        assert len(data) == 1
        assert data[0]["alliance"] == "UFOLODZY"

    def test_alliance_filter_case_insensitive(self, app, client, snapshot):
        with app.app_context():
            _db.session.add_all([
                _make_village(1, snapshot.id, 0, 0, 100, "P1", 1, "UFOLODZY", 100),
            ])
            _db.session.commit()

        resp = client.get("/api/map/villages?alliance=ufolodzy")
        data = json.loads(resp.data)
        assert len(data) == 1

    def test_player_name_filter(self, app, client, snapshot):
        with app.app_context():
            _db.session.add_all([
                _make_village(1, snapshot.id, 0, 0, 100, "Gucio", 1, "UFOLODZY", 100),
                _make_village(2, snapshot.id, 1, 1, 101, "Ktoś", 3, "Enemy", 100),
            ])
            _db.session.commit()

        resp = client.get("/api/map/villages?player=Gucio")
        data = json.loads(resp.data)
        assert len(data) == 1
        assert data[0]["player"] == "Gucio"

    def test_partial_bounding_box_ignored(self, app, client, snapshot):
        """If only some bbox params are given, the filter is not applied."""
        with app.app_context():
            _db.session.add_all([
                _make_village(1, snapshot.id, 10, 10, 100, "P1", 0, "", 100),
                _make_village(2, snapshot.id, 50, 50, 101, "P2", 0, "", 100),
            ])
            _db.session.commit()

        resp = client.get("/api/map/villages?x_min=0&x_max=20")
        data = json.loads(resp.data)
        assert len(data) == 2
