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

    def test_options_preflight_no_auth_required(self, client):
        """CORS preflight must pass without token."""
        resp = client.options("/api/ext/report")
        assert resp.status_code == 204
        assert "X-Witek-Token" in resp.headers.get("Access-Control-Allow-Headers", "")


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


class TestRateLimiting:
    """Rate limiter: 30 requests/min per IP."""

    def test_requests_within_limit_succeed(self, client):
        """Requests under the limit should all pass."""
        from app.routes.api_ext import _rate_limits
        _rate_limits.clear()

        for _ in range(5):
            resp = client.post("/api/ext/report", headers=_headers(), json={
                "attacker": {"name": "A"}, "defender": {"name": "D"},
            })
            assert resp.status_code == 201

    def test_rate_limit_exceeded_returns_429(self, client):
        """Exceeding 30 req/min should return 429."""
        from app.routes.api_ext import _rate_limits, _RATE_LIMIT
        _rate_limits.clear()

        for _ in range(_RATE_LIMIT):
            resp = client.post("/api/ext/report", headers=_headers(), json={
                "attacker": {"name": "A"}, "defender": {"name": "D"},
            })
            assert resp.status_code == 201

        # 31st request should be blocked
        resp = client.post("/api/ext/report", headers=_headers(), json={
            "attacker": {"name": "A"}, "defender": {"name": "D"},
        })
        assert resp.status_code == 429
        assert "Rate limit" in resp.get_json()["error"]

    def test_rate_limit_does_not_block_options(self, client):
        """CORS preflight (OPTIONS) should bypass rate limiter."""
        from app.routes.api_ext import _rate_limits
        _rate_limits.clear()

        for _ in range(35):
            resp = client.options("/api/ext/report")
            assert resp.status_code == 204

    def test_rate_limit_window_expires(self, client):
        """After window passes, requests should succeed again."""
        import time as _time
        from unittest.mock import patch
        from app.routes.api_ext import _rate_limits, _RATE_LIMIT
        _rate_limits.clear()

        # Fill up the limit at t=0
        with patch("app.routes.api_ext.time") as mock_time:
            mock_time.time.return_value = 1000.0
            for _ in range(_RATE_LIMIT):
                client.post("/api/ext/report", headers=_headers(), json={
                    "attacker": {"name": "A"}, "defender": {"name": "D"},
                })

            # Still at t=0 — should be blocked
            resp = client.post("/api/ext/report", headers=_headers(), json={
                "attacker": {"name": "A"}, "defender": {"name": "D"},
            })
            assert resp.status_code == 429

            # Jump forward 61 seconds — window expired
            mock_time.time.return_value = 1061.0
            resp = client.post("/api/ext/report", headers=_headers(), json={
                "attacker": {"name": "A"}, "defender": {"name": "D"},
            })
            assert resp.status_code == 201


class TestGameDataEndpoint:
    def test_submit_hero_data(self, client):
        resp = client.post("/api/ext/game-data", headers=_headers(), json={
            "type": "hero",
            "data": {"health_percent": 85.0, "level": 12, "experience": 4500},
            "server_url": "https://ts31.x3.europe.travian.com",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["ok"] is True
        assert "id" in data

    def test_submit_marketplace_data(self, client):
        resp = client.post("/api/ext/game-data", headers=_headers(), json={
            "type": "marketplace",
            "data": {
                "merchants_available": 3,
                "merchants_total": 5,
                "offers": [{"offered": {"lumber": 500}, "requested": {"iron": 500}}],
            },
        })
        assert resp.status_code == 201
        assert resp.get_json()["ok"] is True

    def test_submit_training_data(self, client):
        resp = client.post("/api/ext/game-data", headers=_headers(), json={
            "type": "training",
            "data": {
                "building_type": "barracks",
                "queue": [{"unit_id": "1", "unit_name": "Legionnaire", "count": 10}],
            },
        })
        assert resp.status_code == 201
        assert resp.get_json()["ok"] is True

    def test_invalid_type_returns_400(self, client):
        resp = client.post("/api/ext/game-data", headers=_headers(), json={
            "type": "invalid_type",
            "data": {},
        })
        assert resp.status_code == 400
        assert "type must be one of" in resp.get_json()["error"]

    def test_missing_type_returns_400(self, client):
        resp = client.post("/api/ext/game-data", headers=_headers(), json={
            "data": {"foo": "bar"},
        })
        assert resp.status_code == 400

    def test_data_must_be_dict(self, client):
        resp = client.post("/api/ext/game-data", headers=_headers(), json={
            "type": "hero",
            "data": "not a dict",
        })
        assert resp.status_code == 400
        assert "data must be a dict" in resp.get_json()["error"]

    def test_data_persisted_to_db(self, client):
        client.post("/api/ext/game-data", headers=_headers(), json={
            "type": "hero",
            "data": {"level": 5},
            "server_url": "https://test.travian.com",
        })
        from app.models import GameData
        entry = GameData.query.first()
        assert entry is not None
        assert entry.data_type == "hero"
        assert '"level": 5' in entry.data
        assert entry.server_url == "https://test.travian.com"

    def test_options_preflight(self, client):
        resp = client.options("/api/ext/game-data")
        assert resp.status_code == 204
