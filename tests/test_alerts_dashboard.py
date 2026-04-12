"""Tests for the /alerts dashboard page."""

import json
import pytest
from datetime import datetime, timezone

from app import create_app
from app.database import db as _db
from app.models import Alert


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TRAVIAN_SERVER_URL = "https://test.travian.com"
    TRAVIAN_MAP_SIZE = 401
    TRAVIAN_OUR_ALLIANCES = [1, 2]
    POP_DROP_THRESHOLD = 25
    NEW_VILLAGE_RADIUS = 30
    MIN_POP_FOR_ALERTS = 500
    ALERT_COOLDOWN_HOURS = 6
    MAX_ALERTS_PER_TYPE = 10
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
def db_session(app):
    with app.app_context():
        yield _db.session


def _make_alert(alert_type, data, notified=False, created_at=None):
    return Alert(
        alert_type=alert_type,
        data=json.dumps(data),
        notified=notified,
        created_at=created_at or datetime.now(timezone.utc),
    )


# ------------------------------------------------------------------
# Basic page load
# ------------------------------------------------------------------

class TestPageLoad:
    def test_alerts_page_returns_200(self, client):
        resp = client.get("/alerts")
        assert resp.status_code == 200

    def test_alerts_page_contains_header(self, client):
        resp = client.get("/alerts")
        assert "Alerty" in resp.data.decode()

    def test_empty_state_message(self, client):
        resp = client.get("/alerts")
        html = resp.data.decode()
        assert "Brak alertów" in html


# ------------------------------------------------------------------
# Alerts displayed
# ------------------------------------------------------------------

class TestAlertsDisplayed:
    def test_pop_drop_alert_shown(self, client, db_session):
        db_session.add(_make_alert("pop_drop", {
            "type": "pop_drop", "uid": 1, "player_name": "Gracz1",
            "alliance_name": "ALI", "old_pop": 1000, "new_pop": 700, "drop_pct": 30.0,
        }))
        db_session.commit()
        resp = client.get("/alerts")
        html = resp.data.decode()
        assert "Gracz1" in html
        assert "1000" in html
        assert "700" in html
        assert "30.0%" in html

    def test_new_village_alert_shown(self, client, db_session):
        db_session.add(_make_alert("new_village", {
            "type": "new_village", "map_id": 99, "village_name": "Wioska",
            "x": -50, "y": 30, "uid": 2, "player_name": "Wrog",
            "aid": 5, "alliance_name": "ZLI", "distance": 12.5,
        }))
        db_session.commit()
        resp = client.get("/alerts")
        html = resp.data.decode()
        assert "Wrog" in html
        assert "(-50|30)" in html
        assert "12.5" in html

    def test_alliance_change_alert_shown(self, client, db_session):
        db_session.add(_make_alert("alliance_change", {
            "type": "alliance_change", "change_type": "joined",
            "uid": 3, "player_name": "Zmiennik",
            "old_aid": 0, "old_alliance_name": "",
            "new_aid": 5, "new_alliance_name": "NOWY",
            "total_pop": 500,
        }))
        db_session.commit()
        resp = client.get("/alerts")
        html = resp.data.decode()
        assert "Zmiennik" in html
        assert "NOWY" in html
        assert "joined" in html

    def test_notified_badge_shown(self, client, db_session):
        db_session.add(_make_alert("pop_drop", {
            "player_name": "A",
            "old_pop": 100, "new_pop": 50, "drop_pct": 50.0,
        }, notified=True))
        db_session.commit()
        resp = client.get("/alerts")
        html = resp.data.decode()
        assert "✅" in html


# ------------------------------------------------------------------
# Filtering
# ------------------------------------------------------------------

class TestFiltering:
    def test_filter_by_type(self, client, db_session):
        db_session.add(_make_alert("pop_drop", {"player_name": "Gracz1", "old_pop": 100, "new_pop": 50, "drop_pct": 50.0}))
        db_session.add(_make_alert("new_village", {"player_name": "Gracz2", "x": 0, "y": 0, "distance": 5.0}))
        db_session.commit()

        resp = client.get("/alerts?type=pop_drop")
        html = resp.data.decode()
        assert "Gracz1" in html
        assert "Gracz2" not in html

    def test_filter_by_type_new_village(self, client, db_session):
        db_session.add(_make_alert("pop_drop", {"player_name": "Gracz1", "old_pop": 100, "new_pop": 50, "drop_pct": 50.0}))
        db_session.add(_make_alert("new_village", {"player_name": "Gracz2", "x": 0, "y": 0, "distance": 5.0}))
        db_session.commit()

        resp = client.get("/alerts?type=new_village")
        html = resp.data.decode()
        assert "Gracz2" in html
        assert "Gracz1" not in html

    def test_search_filter(self, client, db_session):
        db_session.add(_make_alert("pop_drop", {"player_name": "Szukany", "old_pop": 100, "new_pop": 50, "drop_pct": 50.0}))
        db_session.add(_make_alert("pop_drop", {"player_name": "Inny", "old_pop": 200, "new_pop": 100, "drop_pct": 50.0}))
        db_session.commit()

        resp = client.get("/alerts?search=Szukany")
        html = resp.data.decode()
        assert "Szukany" in html
        assert "Inny" not in html

    def test_invalid_type_shows_all(self, client, db_session):
        db_session.add(_make_alert("pop_drop", {"player_name": "A", "old_pop": 1, "new_pop": 0, "drop_pct": 100.0}))
        db_session.commit()

        resp = client.get("/alerts?type=bogus")
        html = resp.data.decode()
        assert "A" in html


# ------------------------------------------------------------------
# Pagination
# ------------------------------------------------------------------

class TestPagination:
    def test_pagination_controls(self, client, db_session):
        for i in range(30):
            db_session.add(_make_alert("pop_drop", {
                "player_name": f"Gracz{i}",
                "old_pop": 100, "new_pop": 50, "drop_pct": 50.0,
            }))
        db_session.commit()

        resp = client.get("/alerts")
        html = resp.data.decode()
        assert "Następna" in html
        assert "1 / 2" in html

    def test_page_2(self, client, db_session):
        for i in range(30):
            db_session.add(_make_alert("pop_drop", {
                "player_name": f"Gracz{i}",
                "old_pop": 100, "new_pop": 50, "drop_pct": 50.0,
            }))
        db_session.commit()

        resp = client.get("/alerts?page=2")
        html = resp.data.decode()
        assert "Poprzednia" in html
        assert "2 / 2" in html

    def test_empty_state_with_filter(self, client, db_session):
        db_session.add(_make_alert("pop_drop", {"player_name": "A", "old_pop": 1, "new_pop": 0, "drop_pct": 100.0}))
        db_session.commit()

        resp = client.get("/alerts?search=Nieistniejacy")
        html = resp.data.decode()
        assert "Brak alertów" in html
        assert "Pokaż wszystkie" in html
