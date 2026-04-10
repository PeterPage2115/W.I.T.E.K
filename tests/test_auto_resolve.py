"""Tests for auto-resolve attack logic — uses real DB."""

import time
import pytest
from datetime import datetime, timezone


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


@pytest.fixture
def flask_app():
    """Create a real Flask app with in-memory SQLite for testing."""
    from app import create_app
    from app.database import db

    app = create_app(config_class=TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _seed_attack(db, attack_unix, status="reported", thread_id=None):
    """Seed a real AttackReport row."""
    from app.models import AttackReport
    r = AttackReport(
        reported_by_discord="test_user",
        defender_x=0, defender_y=0,
        attack_unix=attack_unix,
        status=status,
        forum_thread_id=thread_id,
    )
    db.session.add(r)
    db.session.commit()
    return r


def _seed_thread(db, forum_thread_id, status="active"):
    """Seed a real DefenseThread row."""
    from app.models import DefenseThread
    dt = DefenseThread(
        forum_thread_id=forum_thread_id,
        defender_x=0,
        defender_y=0,
        status=status,
    )
    db.session.add(dt)
    db.session.commit()
    return dt


class TestAutoResolveDB:
    def test_expired_attack_resolved(self, flask_app):
        """Attack past threshold should be auto-resolved in DB."""
        from app.database import db
        from app.models import AttackReport
        from bot.cogs.attacks import Attacks

        now = int(time.time())
        with flask_app.app_context():
            _seed_attack(db, attack_unix=now - 7200 - 60)
            cog = Attacks.__new__(Attacks)
            cog._do_auto_resolve(threshold_minutes=120)
            r = AttackReport.query.first()
            assert r.status == "resolved"
            assert r.auto_resolved is True

    def test_future_attack_not_resolved(self, flask_app):
        """Attack in future should NOT be resolved."""
        from app.database import db
        from app.models import AttackReport

        now = int(time.time())
        with flask_app.app_context():
            _seed_attack(db, attack_unix=now + 3600)
            from bot.cogs.attacks import Attacks
            cog = Attacks.__new__(Attacks)
            cog._do_auto_resolve(threshold_minutes=120)
            r = AttackReport.query.first()
            assert r.status == "reported"

    def test_thread_mixed_attacks_not_resolved(self, flask_app):
        """Thread with one active attack should NOT resolve any."""
        from app.database import db
        from app.models import AttackReport

        now = int(time.time())
        with flask_app.app_context():
            _seed_thread(db, forum_thread_id=100)
            _seed_attack(db, attack_unix=now - 7200 - 60, thread_id=100)
            _seed_attack(db, attack_unix=now + 3600, thread_id=100)
            from bot.cogs.attacks import Attacks
            cog = Attacks.__new__(Attacks)
            cog._do_auto_resolve(threshold_minutes=120)
            reports = AttackReport.query.all()
            assert all(r.status == "reported" for r in reports)

    def test_thread_all_expired_resolved(self, flask_app):
        """Thread where ALL attacks expired should resolve all."""
        from app.database import db
        from app.models import AttackReport, DefenseThread

        now = int(time.time())
        with flask_app.app_context():
            _seed_thread(db, forum_thread_id=200)
            _seed_attack(db, attack_unix=now - 9000, thread_id=200)
            _seed_attack(db, attack_unix=now - 8000, thread_id=200)
            from bot.cogs.attacks import Attacks
            cog = Attacks.__new__(Attacks)
            result = cog._do_auto_resolve(threshold_minutes=120)
            reports = AttackReport.query.all()
            assert all(r.status == "resolved" for r in reports)
            assert all(r.auto_resolved is True for r in reports)
            dt = DefenseThread.query.first()
            assert dt.status == "resolved"
            assert len(result) == 1

    def test_already_resolved_skipped(self, flask_app):
        """Already resolved attacks should not be touched."""
        from app.database import db
        from app.models import AttackReport

        now = int(time.time())
        with flask_app.app_context():
            _seed_attack(db, attack_unix=now - 9999, status="resolved")
            from bot.cogs.attacks import Attacks
            cog = Attacks.__new__(Attacks)
            result = cog._do_auto_resolve(threshold_minutes=120)
            assert len(result) == 0
