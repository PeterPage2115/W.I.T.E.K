"""Tests for API extension input validation."""
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
    from app.routes.api_ext import _rate_limits
    app = create_app(config_class=TestConfig)
    with app.app_context():
        db.create_all()
        _rate_limits.clear()
        yield app.test_client()
        db.session.remove()
        db.drop_all()
        _rate_limits.clear()


def _headers(token="test-token-123"):
    return {"Content-Type": "application/json", "X-Witek-Token": token}


class TestReportValidation:
    def test_missing_attacker(self, client):
        resp = client.post("/api/ext/report", headers=_headers(), json={"defender": {}})
        assert resp.status_code == 400

    def test_invalid_attacker_type(self, client):
        resp = client.post("/api/ext/report", headers=_headers(), json={
            "attacker": "string", "defender": {},
        })
        assert resp.status_code == 400
        assert "must be a dict" in resp.get_json()["error"]

    def test_invalid_defender_type(self, client):
        resp = client.post("/api/ext/report", headers=_headers(), json={
            "attacker": {}, "defender": 123,
        })
        assert resp.status_code == 400
        assert "must be a dict" in resp.get_json()["error"]

    def test_invalid_troops_type(self, client):
        resp = client.post("/api/ext/report", headers=_headers(), json={
            "attacker": {"troops": "not-a-dict"},
            "defender": {},
        })
        assert resp.status_code == 400

    def test_invalid_losses_type(self, client):
        resp = client.post("/api/ext/report", headers=_headers(), json={
            "attacker": {"losses": [1, 2, 3]},
            "defender": {},
        })
        assert resp.status_code == 400

    def test_invalid_troop_count_type(self, client):
        resp = client.post("/api/ext/report", headers=_headers(), json={
            "attacker": {"troops": {"1": "abc"}},
            "defender": {},
        })
        assert resp.status_code == 400

    def test_invalid_side_name_type(self, client):
        resp = client.post("/api/ext/report", headers=_headers(), json={
            "attacker": {"name": 123},
            "defender": {},
        })
        assert resp.status_code == 400
        assert "must be string" in resp.get_json()["error"]

    def test_valid_report_still_works(self, client):
        resp = client.post("/api/ext/report", headers=_headers(), json={
            "attacker": {"name": "Att", "troops": {"1": 100}, "losses": {"1": 30}},
            "defender": {"name": "Def", "troops": {"1": 200}, "losses": {"1": 80}},
        })
        assert resp.status_code == 201
        assert resp.get_json()["ok"] is True


class TestTroopsValidation:
    def test_missing_coords(self, client):
        resp = client.post("/api/ext/troops", headers=_headers(), json={"troops": {}})
        assert resp.status_code == 400

    def test_invalid_coord_type(self, client):
        resp = client.post("/api/ext/troops", headers=_headers(), json={
            "x": "abc", "y": 5, "troops": {},
        })
        assert resp.status_code == 400

    def test_coords_out_of_bounds(self, client):
        resp = client.post("/api/ext/troops", headers=_headers(), json={
            "x": 300, "y": 5, "troops": {},
        })
        assert resp.status_code == 400
        assert "out of bounds" in resp.get_json()["error"]

    def test_coords_negative_boundary(self, client):
        resp = client.post("/api/ext/troops", headers=_headers(), json={
            "x": -200, "y": -200, "troops": {"1": 10},
        })
        assert resp.status_code == 200

    def test_coords_positive_boundary(self, client):
        resp = client.post("/api/ext/troops", headers=_headers(), json={
            "x": 200, "y": 200, "troops": {"1": 10},
        })
        assert resp.status_code == 200

    def test_invalid_troops_dict(self, client):
        resp = client.post("/api/ext/troops", headers=_headers(), json={
            "x": 5, "y": 5, "troops": [1, 2, 3],
        })
        assert resp.status_code == 400

    def test_valid_troops_still_works(self, client):
        resp = client.post("/api/ext/troops", headers=_headers(), json={
            "x": 76, "y": 43, "village_name": "Test", "troops": {"1": 500},
        })
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


class TestIncomingValidation:
    def test_incoming_not_list(self, client):
        resp = client.post("/api/ext/incoming", headers=_headers(), json={
            "x": 5, "y": 5, "incoming": "nope",
        })
        assert resp.status_code == 400

    def test_incoming_item_not_dict(self, client):
        resp = client.post("/api/ext/incoming", headers=_headers(), json={
            "x": 5, "y": 5, "incoming": ["bad"],
        })
        assert resp.status_code == 400

    def test_incoming_invalid_from_coords(self, client):
        resp = client.post("/api/ext/incoming", headers=_headers(), json={
            "x": 5, "y": 5,
            "incoming": [{"from_x": 999, "from_y": 0}],
        })
        assert resp.status_code == 400
        assert "out of bounds" in resp.get_json()["error"]

    def test_incoming_invalid_target_coords(self, client):
        resp = client.post("/api/ext/incoming", headers=_headers(), json={
            "x": "bad", "y": 5, "incoming": [],
        })
        assert resp.status_code == 400

    def test_valid_incoming_still_works(self, client):
        resp = client.post("/api/ext/incoming", headers=_headers(), json={
            "x": 76, "y": 43,
            "incoming": [
                {"type": "attack", "from_x": 10, "from_y": -5,
                 "arrival_unix": 1712764800, "player_name": "Enemy"},
            ],
        })
        assert resp.status_code == 201
        assert resp.get_json()["ok"] is True
