"""Shared server profile loader.

Single source of truth for server configuration. Used by both
Flask app (app/config.py) and Discord bot (bot/tribes.py).

Lives at project root to avoid circular imports between app/ and bot/.
"""
import os
import logging
from pathlib import Path
import yaml

log = logging.getLogger(__name__)

_DEFAULT_FEATURES = {
    "ships": False,
    "regions": False,
    "cities": False,
    "harbors": False,
    "victory_points": False,
}


def load_profile(config_path: Path | None = None) -> dict:
    """Load the active server profile from config.yaml.

    Selection order:
    1. SERVER_PROFILE env var → selects named profile under 'servers:'
    2. If not set → first profile in 'servers' dict
    3. Backward compat: if no 'servers' key, reads flat 'travian:' section
    4. Env override: TRAVIAN_SERVER_URL overrides profile url
    """
    if config_path is None:
        config_path = Path(__file__).resolve().parent / "config" / "config.yaml"

    if not config_path.exists():
        log.warning("Config file not found: %s — using defaults", config_path)
        return _default_profile()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    servers = raw.get("servers")
    if not servers:
        return _from_flat_config(raw)

    profile_name = os.environ.get("SERVER_PROFILE", "")
    if profile_name:
        if profile_name not in servers:
            raise ValueError(
                f"SERVER_PROFILE='{profile_name}' not found in config.yaml. "
                f"Available: {list(servers.keys())}"
            )
        profile = servers[profile_name]
    else:
        profile_name = next(iter(servers))
        profile = servers[profile_name]
        log.info("SERVER_PROFILE not set — using '%s'", profile_name)

    result = _normalize(profile, profile_name)

    env_url = os.environ.get("TRAVIAN_SERVER_URL")
    if env_url:
        result["url"] = env_url

    return result


def _normalize(profile: dict, name: str) -> dict:
    features = {**_DEFAULT_FEATURES, **(profile.get("features") or {})}
    return {
        "name": name,
        "url": profile.get("url", ""),
        "speed": profile.get("speed", 1),
        "tribes": profile.get("tribes", [1, 2, 3]),
        "our_alliances": profile.get("our_alliances", []),
        "features": features,
        "legionnaire_rebalanced": profile.get("legionnaire_rebalanced", False),
        "troop_speed_multiplier": profile.get("troop_speed_multiplier", 2),
        "map_size": profile.get("map_size", 401),
    }


def _default_profile() -> dict:
    return _normalize({
        "url": os.environ.get("TRAVIAN_SERVER_URL", "https://ts31.x3.europe.travian.com"),
        "speed": 3,
        "tribes": [1, 2, 3],
    }, "default")


def _from_flat_config(raw: dict) -> dict:
    """Backward compat: convert old flat config.yaml to profile format."""
    travian = raw.get("travian", {})
    result = _normalize({
        "url": travian.get("server_url", ""),
        "speed": travian.get("speed_multiplier", 3),
        "tribes": travian.get("available_tribes", [1, 2, 3]),
        "our_alliances": travian.get("our_alliances", []),
        "troop_speed_multiplier": travian.get("troop_speed_multiplier", 2),
        "map_size": travian.get("map_size", 401),
    }, "legacy")
    env_url = os.environ.get("TRAVIAN_SERVER_URL")
    if env_url:
        result["url"] = env_url
    return result
