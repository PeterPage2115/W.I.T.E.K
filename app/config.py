import os
from pathlib import Path
from dotenv import load_dotenv
import yaml

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_yaml_config():
    config_path = BASE_DIR / "config" / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_yaml = _load_yaml_config()


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'witek.db'}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # SQLite concurrent write mitigation (rubber-duck finding #4)
    if not DATABASE_URL:
        SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 30}}
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {}

    # Server profile (shared loader — avoids config divergence between Flask and bot)
    from server_profile import load_profile
    _profile = load_profile()

    TRAVIAN_SERVER_URL = _profile["url"]
    TRAVIAN_MAP_SIZE = _profile["map_size"]
    TRAVIAN_OUR_ALLIANCES = _profile["our_alliances"]
    TRAVIAN_SPEED_MULTIPLIER = _profile["speed"]
    TRAVIAN_TROOP_SPEED_MULTIPLIER = _profile["troop_speed_multiplier"]
    TRAVIAN_AVAILABLE_TRIBES = _profile["tribes"]
    TRAVIAN_FEATURES = _profile["features"]
    TRAVIAN_LEGIONNAIRE_REBALANCED = _profile.get("legionnaire_rebalanced", False)
    SERVER_PROFILE_NAME = _profile["name"]

    # Attacks
    _attacks = _yaml.get("attacks", {})
    AUTO_RESOLVE_AFTER_MINUTES = _attacks.get("auto_resolve_after_minutes", 120)

    # Scheduler
    scheduler = _yaml.get("scheduler", {})
    FETCH_INTERVAL_MINUTES = scheduler.get("fetch_interval_minutes", 60)

    # Alerts
    alerts = _yaml.get("alerts", {})
    POP_DROP_THRESHOLD = alerts.get("pop_drop_threshold", 15)
    NEW_VILLAGE_RADIUS = alerts.get("new_village_radius", 30)

    # Extension API
    EXT_API_TOKEN = os.getenv("EXT_API_TOKEN", "")

    # Discord OAuth2
    DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
    DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
    DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/auth/callback")

    # Discord (rubber-duck finding #6: guild_id must be int, not str)
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
    _guild_id = os.getenv("DISCORD_GUILD_ID", "")
    try:
        DISCORD_GUILD_ID = int(_guild_id) if _guild_id else None
    except ValueError:
        DISCORD_GUILD_ID = None
    ALLIANCE_PASSWORD = os.getenv("ALLIANCE_PASSWORD", "")

    _alerts_ch = os.getenv("DISCORD_ALERTS_CHANNEL_ID", "")
    try:
        DISCORD_ALERTS_CHANNEL_ID = int(_alerts_ch) if _alerts_ch else None
    except ValueError:
        DISCORD_ALERTS_CHANNEL_ID = None

    _forum_ch = os.getenv("DISCORD_DEFENSE_FORUM_ID", "")
    try:
        DISCORD_DEFENSE_FORUM_ID = int(_forum_ch) if _forum_ch else None
    except ValueError:
        DISCORD_DEFENSE_FORUM_ID = None

    _def_role = os.getenv("DISCORD_DEF_ROLE_ID", "")
    try:
        DISCORD_DEF_ROLE_ID = int(_def_role) if _def_role else None
    except ValueError:
        DISCORD_DEF_ROLE_ID = None
