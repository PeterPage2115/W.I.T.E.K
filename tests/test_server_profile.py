"""Tests for shared server profile loader."""
import os
import pytest
from unittest.mock import patch


def test_load_default_profile(tmp_path):
    """When SERVER_PROFILE not set, loads first profile."""
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text("""
servers:
  ts31:
    url: "https://ts31.x3.europe.travian.com"
    speed: 3
    tribes: [1, 2, 3, 6, 7]
    our_alliances: [14]
    features:
      ships: false
      regions: false
""")
    from server_profile import load_profile
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SERVER_PROFILE", None)
        os.environ.pop("TRAVIAN_SERVER_URL", None)
        profile = load_profile(config_yaml)
    assert profile["url"] == "https://ts31.x3.europe.travian.com"
    assert profile["speed"] == 3
    assert profile["features"]["ships"] is False


def test_load_rof_profile(tmp_path):
    """SERVER_PROFILE=rof-x3 loads RoF config."""
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text("""
servers:
  ts31:
    url: "https://ts31.x3.europe.travian.com"
    speed: 3
    tribes: [1, 2, 3, 6, 7]
    our_alliances: [14]
    features:
      ships: false
  rof-x3:
    url: "https://rof.x3.international.travian.com"
    speed: 3
    tribes: [1, 3, 6, 7, 8, 9]
    our_alliances: []
    features:
      ships: true
      regions: true
      harbors: true
      victory_points: true
    legionnaire_rebalanced: true
""")
    from server_profile import load_profile
    with patch.dict(os.environ, {"SERVER_PROFILE": "rof-x3"}):
        os.environ.pop("TRAVIAN_SERVER_URL", None)
        profile = load_profile(config_yaml)
    assert profile["url"] == "https://rof.x3.international.travian.com"
    assert profile["features"]["ships"] is True
    assert profile["legionnaire_rebalanced"] is True


def test_invalid_profile_raises(tmp_path):
    """Unknown SERVER_PROFILE raises ValueError."""
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text("""
servers:
  ts31:
    url: "https://ts31.x3.europe.travian.com"
    speed: 3
    tribes: [1, 2, 3]
    our_alliances: []
    features:
      ships: false
""")
    from server_profile import load_profile
    with patch.dict(os.environ, {"SERVER_PROFILE": "nonexistent"}):
        with pytest.raises(ValueError, match="nonexistent"):
            load_profile(config_yaml)


def test_fallback_to_env_server_url(tmp_path):
    """TRAVIAN_SERVER_URL env overrides profile url."""
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text("""
servers:
  ts31:
    url: "https://ts31.x3.europe.travian.com"
    speed: 3
    tribes: [1, 2, 3]
    our_alliances: []
    features:
      ships: false
""")
    from server_profile import load_profile
    with patch.dict(os.environ, {"TRAVIAN_SERVER_URL": "https://custom.url.com"}):
        os.environ.pop("SERVER_PROFILE", None)
        profile = load_profile(config_yaml)
    assert profile["url"] == "https://custom.url.com"


def test_backward_compat_flat_config(tmp_path):
    """Old-style config.yaml without servers: key still works."""
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text("""
travian:
  server_url: "https://ts31.x3.europe.travian.com"
  speed_multiplier: 3
  available_tribes: [1, 2, 3, 6, 7]
  our_alliances: [14, 32]
  troop_speed_multiplier: 2
  map_size: 401
""")
    from server_profile import load_profile
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SERVER_PROFILE", None)
        os.environ.pop("TRAVIAN_SERVER_URL", None)
        profile = load_profile(config_yaml)
    assert profile["url"] == "https://ts31.x3.europe.travian.com"
    assert profile["tribes"] == [1, 2, 3, 6, 7]
    assert profile["our_alliances"] == [14, 32]
