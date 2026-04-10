"""Shared fixtures for integration tests."""

import pytest


class TestConfig:
    """Config class for integration tests — in-memory SQLite."""
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
    """Create Flask app with in-memory SQLite for testing."""
    from app import create_app
    from app.database import db

    app = create_app(config_class=TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
