"""Tests for extension webhook API endpoints."""

import json
import pytest


class TestConfig:
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESTING = True
    SECRET_KEY = "test-secret"
    TRAVIAN_SERVER_URL = "https://test.travian.com"
    TRAVIAN_MAP_SIZE = 401
    TRAVIAN_OUR_ALLIANCES = []
    DISCORD_TOKEN = ""
    DISCORD_GUILD_ID = None
    DISCORD_ALERTS_CHANNEL_ID = None
    DISCORD_DEFENSE_FORUM_ID = None
    DISCORD_DEF_ROLE_ID = None
    TRAVIAN_SPEED_MULTIPLIER = 3
    TRAVIAN_TROOP_SPEED_MULTIPLIER = 2
    TRAVIAN_AVAILABLE_TRIBES = [1, 2, 3]
    AUTO_RESOLVE_AFTER_MINUTES = 120
    EXT_API_TOKEN = "test-token-123"


@pytest.fixture
def client():
    from app import create_app
    from app.database import db
    app = create_app(config_class=TestConfig)
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def _headers(token="test-token-123"):
    return {"Content-Type": "application/json", "X-Witek-Token": token}


class TestAuth:
    def test_no_token_returns_401(self, client):
        resp = client.post("/api/ext/report", json={"attacker": {}, "defender": {}})
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client):
        resp = client.post("/api/ext/report", json={"attacker": {}, "defender": {}},
                          headers=_headers("bad-token"))
        assert resp.status_code == 401

    def test_no_json_returns_415(self, client):
        resp = client.post("/api/ext/report", data="not json",
                          headers={"X-Witek-Token": "test-token-123"})
        assert resp.status_code == 415


class TestReportEndpoint:
    def test_submit_report(self, client):
        resp = client.post("/api/ext/report", headers=_headers(), json={
            "attacker": {"name": "Att", "troops": {"1": 100}, "losses": {"1": 30}},
            "defender": {"name": "Def", "troops": {"1": 200}, "losses": {"1": 80}},
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["ok"] is True
        assert "report_id" in data

    def test_missing_attacker_returns_400(self, client):
        resp = client.post("/api/ext/report", headers=_headers(), json={
            "defender": {"name": "Def"},
        })
        assert resp.status_code == 400


class TestTroopsEndpoint:
    def test_submit_troops(self, client):
        resp = client.post("/api/ext/troops", headers=_headers(), json={
            "x": 76, "y": 43,
            "village_name": "TestVillage",
            "troops": {"1": 500, "2": 100},
        })
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_update_existing_troops(self, client):
        payload = {"x": 76, "y": 43, "troops": {"1": 500}}
        client.post("/api/ext/troops", headers=_headers(), json=payload)
        resp = client.post("/api/ext/troops", headers=_headers(), json={
            "x": 76, "y": 43, "troops": {"1": 600, "2": 200},
        })
        assert resp.status_code == 200

    def test_missing_coords_returns_400(self, client):
        resp = client.post("/api/ext/troops", headers=_headers(), json={
            "troops": {"1": 100},
        })
        assert resp.status_code == 400


class TestIncomingEndpoint:
    def test_submit_incoming(self, client):
        resp = client.post("/api/ext/incoming", headers=_headers(), json={
            "x": 76, "y": 43,
            "incoming": [
                {"type": "attack", "from_x": 10, "from_y": -5,
                 "arrival_unix": 1712764800, "player_name": "Enemy"},
            ],
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert len(data["created"]) == 1

    def test_submit_multiple_incoming(self, client):
        resp = client.post("/api/ext/incoming", headers=_headers(), json={
            "x": 76, "y": 43,
            "incoming": [
                {"type": "attack", "from_x": 10, "from_y": -5, "arrival_unix": 1712764800},
                {"type": "raid", "from_x": 20, "from_y": 30, "arrival_unix": 1712764900},
            ],
        })
        assert resp.status_code == 201
        assert len(resp.get_json()["created"]) == 2
