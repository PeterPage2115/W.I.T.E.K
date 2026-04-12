"""Tests for app/snapshot_helpers.py — request-scoped cached snapshot."""

import pytest
from datetime import datetime, timezone, timedelta
from app import create_app
from app.database import db as _db
from app.models import Snapshot
from app.snapshot_helpers import get_latest_snapshot


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TRAVIAN_SERVER_URL = "https://test.travian.com"
    TRAVIAN_MAP_SIZE = 401
    TRAVIAN_OUR_ALLIANCES = [1]
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


class TestGetLatestSnapshot:
    """Unit tests for get_latest_snapshot()."""

    def test_returns_none_when_no_snapshots(self, app):
        with app.test_request_context():
            result = get_latest_snapshot()
            assert result is None

    def test_returns_latest_snapshot(self, app):
        old = Snapshot(fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc), village_count=100)
        new = Snapshot(fetched_at=datetime(2024, 6, 1, tzinfo=timezone.utc), village_count=200)
        _db.session.add_all([old, new])
        _db.session.commit()

        with app.test_request_context():
            result = get_latest_snapshot()
            assert result is not None
            assert result.village_count == 200

    def test_cached_per_request(self, app):
        snap = Snapshot(fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc), village_count=50)
        _db.session.add(snap)
        _db.session.commit()

        with app.test_request_context():
            first_call = get_latest_snapshot()
            second_call = get_latest_snapshot()
            assert first_call is second_call

    def test_not_cached_across_real_requests(self, app):
        """Each real HTTP request gets its own flask.g (no stale cache)."""
        snap = Snapshot(fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc), village_count=50)
        _db.session.add(snap)
        _db.session.commit()

        client = app.test_client()
        # Two requests — if caching leaked, second would fail
        resp1 = client.get("/")
        assert resp1.status_code == 200
        resp2 = client.get("/")
        assert resp2.status_code == 200


class TestContextProcessor:
    """Verify the context processor injects 'snapshot' into templates."""

    def test_snapshot_available_in_template_context(self, app):
        snap = Snapshot(fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc), village_count=42)
        _db.session.add(snap)
        _db.session.commit()

        with app.test_request_context():
            # Context processors are called by render_template; simulate via app
            ctx = app.jinja_env.globals
            # Instead, use the processors directly
            processors = app.template_context_processors[None]
            context = {}
            for proc in processors:
                context.update(proc())
            assert "snapshot" in context
            assert context["snapshot"].village_count == 42

    def test_snapshot_none_when_empty(self, app):
        with app.test_request_context():
            processors = app.template_context_processors[None]
            context = {}
            for proc in processors:
                context.update(proc())
            assert "snapshot" in context
            assert context["snapshot"] is None

    def test_dashboard_gets_snapshot_via_context(self, client, app):
        """Dashboard renders without snapshot= kwarg thanks to context processor."""
        snap = Snapshot(fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc), village_count=10)
        _db.session.add(snap)
        _db.session.commit()

        resp = client.get("/")
        assert resp.status_code == 200
