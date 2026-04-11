"""Tests for spy report API endpoint and dashboard route."""

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
def app():
    from app import create_app
    from app.database import db
    from app.routes.api_ext import _rate_limits
    application = create_app(config_class=TestConfig)
    with application.app_context():
        db.create_all()
        _rate_limits.clear()
        yield application
        db.session.remove()
        db.drop_all()
        _rate_limits.clear()


@pytest.fixture
def client(app):
    return app.test_client()


def _headers(token="test-token-123"):
    return {"Content-Type": "application/json", "X-Witek-Token": token}


class TestSpyReportEndpoint:
    def test_submit_resources_spy_report(self, client):
        resp = client.post("/api/ext/spy-report", headers=_headers(), json={
            "x": 50, "y": -30,
            "spy_type": "resources",
            "target_player": "EnemyPlayer",
            "target_village": "EnemyVillage",
            "resources": {"lumber": 1000, "clay": 500, "iron": 300, "crop": 2000},
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["ok"] is True
        assert "report_id" in data

    def test_submit_troops_spy_report(self, client):
        resp = client.post("/api/ext/spy-report", headers=_headers(), json={
            "x": 10, "y": 20,
            "spy_type": "troops",
            "target_player": "Defender",
            "troops": {"1": 100, "2": 50},
        })
        assert resp.status_code == 201
        assert resp.get_json()["ok"] is True

    def test_submit_both_spy_report(self, client):
        resp = client.post("/api/ext/spy-report", headers=_headers(), json={
            "x": -100, "y": 100,
            "spy_type": "both",
            "target_player": "Target",
            "target_village": "Village",
            "resources": {"lumber": 500, "crop": 1000},
            "troops": {"11": 200},
            "defense_buildings": {"wall": 10, "palace": 5},
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["ok"] is True

        # Verify stored data
        from app.models import SpyReport
        report = SpyReport.query.get(data["report_id"])
        assert report.spy_type == "both"
        assert report.target_x == -100
        assert report.target_y == 100
        assert report.resources_lumber == 500
        assert report.resources_crop == 1000
        assert report.resources_clay is None
        assert json.loads(report.troops) == {"11": 200}
        assert json.loads(report.defense_buildings) == {"wall": 10, "palace": 5}

    def test_missing_coords_returns_400(self, client):
        resp = client.post("/api/ext/spy-report", headers=_headers(), json={
            "spy_type": "resources",
        })
        assert resp.status_code == 400

    def test_missing_spy_type_returns_400(self, client):
        resp = client.post("/api/ext/spy-report", headers=_headers(), json={
            "x": 10, "y": 20,
        })
        assert resp.status_code == 400

    def test_invalid_spy_type_returns_400(self, client):
        resp = client.post("/api/ext/spy-report", headers=_headers(), json={
            "x": 10, "y": 20,
            "spy_type": "invalid",
        })
        assert resp.status_code == 400
        assert "spy_type" in resp.get_json()["error"]

    def test_invalid_coords_returns_400(self, client):
        resp = client.post("/api/ext/spy-report", headers=_headers(), json={
            "x": 999, "y": 20,
            "spy_type": "resources",
        })
        assert resp.status_code == 400
        assert "out of bounds" in resp.get_json()["error"]

    def test_invalid_troops_returns_400(self, client):
        resp = client.post("/api/ext/spy-report", headers=_headers(), json={
            "x": 10, "y": 20,
            "spy_type": "troops",
            "troops": "not a dict",
        })
        assert resp.status_code == 400

    def test_invalid_resources_returns_400(self, client):
        resp = client.post("/api/ext/spy-report", headers=_headers(), json={
            "x": 10, "y": 20,
            "spy_type": "resources",
            "resources": "not a dict",
        })
        assert resp.status_code == 400

    def test_invalid_defense_buildings_returns_400(self, client):
        resp = client.post("/api/ext/spy-report", headers=_headers(), json={
            "x": 10, "y": 20,
            "spy_type": "both",
            "defense_buildings": "not a dict",
        })
        assert resp.status_code == 400

    def test_no_token_returns_401(self, client):
        resp = client.post("/api/ext/spy-report", json={
            "x": 10, "y": 20, "spy_type": "resources",
        })
        assert resp.status_code == 401

    def test_options_preflight(self, client):
        resp = client.options("/api/ext/spy-report")
        assert resp.status_code == 204


class TestSpyReportDashboard:
    def _login(self, client):
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["discord_id"] = 123456
            sess["discord_name"] = "TestUser"
            sess["role"] = "leader"

    def _create_spy_report(self, client):
        return client.post("/api/ext/spy-report", headers=_headers(), json={
            "x": 50, "y": -30,
            "spy_type": "resources",
            "target_player": "EnemyPlayer",
            "target_village": "EnemyVillage",
            "resources": {"lumber": 1000, "clay": 500, "iron": 300, "crop": 2000},
        })

    def test_spy_report_list_requires_login(self, client):
        resp = client.get("/reports/spy")
        assert resp.status_code == 302  # redirect to login

    def test_spy_report_list_empty(self, client):
        self._login(client)
        resp = client.get("/reports/spy")
        assert resp.status_code == 200
        assert "Brak raportów szpiegowskich" in resp.data.decode()

    def test_spy_report_list_with_data(self, client):
        self._create_spy_report(client)
        self._login(client)
        resp = client.get("/reports/spy")
        assert resp.status_code == 200
        assert "EnemyPlayer" in resp.data.decode()

    def test_spy_report_filter_by_player(self, client):
        self._create_spy_report(client)
        self._login(client)
        resp = client.get("/reports/spy?player=Enemy")
        assert resp.status_code == 200
        assert "EnemyPlayer" in resp.data.decode()

    def test_spy_report_filter_by_type(self, client):
        self._create_spy_report(client)
        self._login(client)
        resp = client.get("/reports/spy?spy_type=resources")
        assert resp.status_code == 200
        assert "EnemyPlayer" in resp.data.decode()

        resp = client.get("/reports/spy?spy_type=troops")
        assert resp.status_code == 200
        assert "Brak raportów" in resp.data.decode()
