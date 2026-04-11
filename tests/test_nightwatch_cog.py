"""Testy czuwania nocnego (/tczuwanie)."""

import pytest
from datetime import datetime, time, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app import create_app
from app.database import db as _db
from app.models import AttackReport, NightWatchSetting
from bot.cogs.nightwatch import (
    NightWatchCog,
    _in_time_window,
    _build_attack_embed,
    MAX_DMS_PER_SESSION,
)


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
def db_session(app):
    with app.app_context():
        yield _db.session


# ------------------------------------------------------------------ #
# _in_time_window
# ------------------------------------------------------------------ #

class TestInTimeWindow:
    def test_normal_range_inside(self):
        # 08:00-18:00, check at 12:00
        dt = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert _in_time_window(dt, 8, 0, 18, 0) is True

    def test_normal_range_outside(self):
        # 08:00-18:00, check at 20:00
        dt = datetime(2024, 1, 1, 20, 0, tzinfo=timezone.utc)
        assert _in_time_window(dt, 8, 0, 18, 0) is False

    def test_overnight_range_late_evening(self):
        # 22:00-06:00, check at 23:30
        dt = datetime(2024, 1, 1, 23, 30, tzinfo=timezone.utc)
        assert _in_time_window(dt, 22, 0, 6, 0) is True

    def test_overnight_range_early_morning(self):
        # 22:00-06:00, check at 03:00
        dt = datetime(2024, 1, 1, 3, 0, tzinfo=timezone.utc)
        assert _in_time_window(dt, 22, 0, 6, 0) is True

    def test_overnight_range_outside_afternoon(self):
        # 22:00-06:00, check at 14:00
        dt = datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc)
        assert _in_time_window(dt, 22, 0, 6, 0) is False

    def test_at_start_boundary(self):
        dt = datetime(2024, 1, 1, 22, 0, tzinfo=timezone.utc)
        assert _in_time_window(dt, 22, 0, 6, 0) is True

    def test_at_end_boundary(self):
        # End is exclusive
        dt = datetime(2024, 1, 1, 6, 0, tzinfo=timezone.utc)
        assert _in_time_window(dt, 22, 0, 6, 0) is False

    def test_minutes_matter(self):
        dt = datetime(2024, 1, 1, 22, 30, tzinfo=timezone.utc)
        assert _in_time_window(dt, 22, 45, 6, 0) is False

    def test_same_hour_range(self):
        # 0:00-0:00 → no window
        dt = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert _in_time_window(dt, 0, 0, 0, 0) is False


# ------------------------------------------------------------------ #
# _build_attack_embed
# ------------------------------------------------------------------ #

class TestBuildAttackEmbed:
    def test_embed_fields(self):
        attack = {
            "attacker_name": "Attacker1",
            "defender_name": "Defender1",
            "defender_x": 10,
            "defender_y": -20,
            "attack_time": "23:45",
        }
        embed = _build_attack_embed(attack)
        assert embed.title == "🌙 Czuwanie Nocne — Nowy Atak!"
        assert embed.color.value == 0xE74C3C
        assert len(embed.fields) == 4
        assert "Attacker1" in embed.fields[0].value
        assert "Defender1" in embed.fields[1].value
        assert "(10|-20)" in embed.fields[2].value
        assert "23:45" in embed.fields[3].value
        assert "W.I.T.E.K" in embed.footer.text

    def test_embed_missing_values(self):
        embed = _build_attack_embed({})
        assert "Nieznany" in embed.fields[0].value
        assert "?" in embed.fields[2].value


# ------------------------------------------------------------------ #
# NightWatchSetting model
# ------------------------------------------------------------------ #

class TestNightWatchSettingModel:
    def test_create_with_defaults(self, app, db_session):
        nw = NightWatchSetting(discord_id=12345)
        db_session.add(nw)
        db_session.commit()

        loaded = NightWatchSetting.query.first()
        assert loaded.discord_id == 12345
        assert loaded.enabled is True
        assert loaded.start_hour == 22
        assert loaded.end_hour == 6
        assert loaded.dm_count == 0

    def test_unique_discord_id(self, app, db_session):
        db_session.add(NightWatchSetting(discord_id=111))
        db_session.commit()
        db_session.add(NightWatchSetting(discord_id=111))
        with pytest.raises(Exception):
            db_session.commit()


# ------------------------------------------------------------------ #
# Cog helper methods (DB)
# ------------------------------------------------------------------ #

class TestCogDbHelpers:
    def test_get_active_watchers_in_window(self, app, db_session):
        db_session.add(NightWatchSetting(
            discord_id=100, enabled=True,
            start_hour=22, start_minute=0,
            end_hour=6, end_minute=0,
        ))
        db_session.commit()

        bot = MagicMock()
        bot.flask_app = app
        cog = NightWatchCog(bot)

        # 23:00 UTC — inside window
        now = datetime(2024, 1, 1, 23, 0, tzinfo=timezone.utc)
        with app.app_context():
            watchers = cog._get_active_watchers(now)
        assert len(watchers) == 1
        assert watchers[0]["discord_id"] == 100

    def test_get_active_watchers_outside_window(self, app, db_session):
        db_session.add(NightWatchSetting(
            discord_id=100, enabled=True,
            start_hour=22, start_minute=0,
            end_hour=6, end_minute=0,
        ))
        db_session.commit()

        bot = MagicMock()
        bot.flask_app = app
        cog = NightWatchCog(bot)

        # 14:00 UTC — outside window
        now = datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc)
        with app.app_context():
            watchers = cog._get_active_watchers(now)
        assert len(watchers) == 0

    def test_get_active_watchers_disabled(self, app, db_session):
        db_session.add(NightWatchSetting(
            discord_id=100, enabled=False,
            start_hour=22, start_minute=0,
            end_hour=6, end_minute=0,
        ))
        db_session.commit()

        bot = MagicMock()
        bot.flask_app = app
        cog = NightWatchCog(bot)

        now = datetime(2024, 1, 1, 23, 0, tzinfo=timezone.utc)
        with app.app_context():
            watchers = cog._get_active_watchers(now)
        assert len(watchers) == 0

    def test_get_recent_attacks(self, app, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(AttackReport(
            reported_by_discord="user1",
            attacker_name="Raider",
            defender_name="Ally1",
            defender_x=10, defender_y=20,
            attack_time="23:30",
            status="reported",
            created_at=now - timedelta(minutes=2),
        ))
        # Old attack — should be excluded
        db_session.add(AttackReport(
            reported_by_discord="user2",
            attacker_name="OldRaider",
            defender_name="Ally2",
            defender_x=5, defender_y=5,
            attack_time="10:00",
            status="reported",
            created_at=now - timedelta(hours=1),
        ))
        # Resolved attack — should be excluded
        db_session.add(AttackReport(
            reported_by_discord="user3",
            attacker_name="Resolved",
            defender_name="Ally3",
            defender_x=1, defender_y=1,
            attack_time="23:00",
            status="resolved",
            created_at=now - timedelta(minutes=1),
        ))
        db_session.commit()

        bot = MagicMock()
        bot.flask_app = app
        cog = NightWatchCog(bot)

        with app.app_context():
            attacks = cog._get_recent_attacks(now)
        assert len(attacks) == 1
        assert attacks[0]["attacker_name"] == "Raider"

    def test_increment_dm_count(self, app, db_session):
        db_session.add(NightWatchSetting(
            discord_id=100, enabled=True, dm_count=2,
            session_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        ))
        db_session.commit()

        bot = MagicMock()
        bot.flask_app = app
        cog = NightWatchCog(bot)

        with app.app_context():
            cog._increment_dm_count(100, 1)
            setting = NightWatchSetting.query.filter_by(discord_id=100).first()
            assert setting.dm_count == 3

    def test_increment_dm_count_resets_on_new_day(self, app, db_session):
        db_session.add(NightWatchSetting(
            discord_id=100, enabled=True, dm_count=4,
            session_date="2023-01-01",
        ))
        db_session.commit()

        bot = MagicMock()
        bot.flask_app = app
        cog = NightWatchCog(bot)

        with app.app_context():
            cog._increment_dm_count(100, 2)
            setting = NightWatchSetting.query.filter_by(discord_id=100).first()
            assert setting.dm_count == 2

    def test_dm_count_limit_respected(self, app, db_session):
        """Watchers at DM limit should be returned but with correct count."""
        now = datetime(2024, 6, 15, 23, 0, tzinfo=timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        db_session.add(NightWatchSetting(
            discord_id=100, enabled=True,
            start_hour=22, start_minute=0,
            end_hour=6, end_minute=0,
            dm_count=MAX_DMS_PER_SESSION,
            session_date=today_str,
        ))
        db_session.commit()

        bot = MagicMock()
        bot.flask_app = app
        cog = NightWatchCog(bot)

        with app.app_context():
            watchers = cog._get_active_watchers(now)
        assert len(watchers) == 1
        assert watchers[0]["dm_count"] == MAX_DMS_PER_SESSION
