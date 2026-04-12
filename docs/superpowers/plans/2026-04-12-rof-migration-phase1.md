# RoF Migration — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make W.I.T.E.K fully operational on the Reign of Fire x3 International server launching April 14, 2026.

**Architecture:** Config-driven multi-server — same codebase, `SERVER_PROFILE` env var selects config block from `config.yaml`. Separate Docker Compose file per server instance, each with its own DB and Discord token.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy, py-cord, Docker Compose, PostgreSQL

**Spec:** `docs/superpowers/specs/2025-07-24-rof-migration-design.md`

**Deadline:** April 14, 2026 (server launch) — 2 days from now

---

## File Structure

### Files to Modify

| File | Responsibility | Changes |
|------|---------------|---------|
| `bot/tribes.py:178-214` | Tribe definitions | Swap tid 8↔9 (Vikings=9, Spartans=8) |
| `bot/tribes.py:225-252` | Config loading | Use shared profile loader instead of raw YAML |
> **NOTE:** Profile loader lives at project root `server_profile.py` (not `app/`) to avoid circular imports between `app` and `bot` packages.
| `app/map_sql/parser.py` | map.sql parser | Parse all 16 fields into VillageRow |
| `app/models.py:21-45` | Village model | Add region, is_capital, is_city, has_harbor, victory_points columns |
| `app/models.py:48-59` | Player model | Add mixed-tribe detection logic |
| `app/map_sql/collector.py:38-54` | Snapshot storage | Pass new fields from parser to Village model |
| `app/map_sql/collector.py:67-93` | Player aggregation | Most-common-tribe logic for mixed tribes |
| `app/database.py:6-36` | Migration helper | Add villages columns to `expected` dict |
| `app/config.py` | Flask config | Read from `servers.<SERVER_PROFILE>` block |
| `config/config.yaml` | YAML config | Restructure: flat → nested `servers:` with profiles |
| `config/config.example.yaml` | Example config | Mirror new structure |
| `CLAUDE.md` | Project docs | Fix tribe IDs (tid 8=Spartans, 9=Vikings) |
| `docker-compose.yml` | Production Docker | ts31 instance (renamed from generic) |
| `.env.example` | Env template | Add SERVER_PROFILE |

### Files to Create

| File | Responsibility |
|------|---------------|
| `app/server_profile.py` | Shared profile loader — single place to load config for both Flask and bot |
| `docker-compose.rof.yml` | RoF x3 Docker Compose (separate DB, token, guild) |
| `tests/test_parser_rof.py` | Tests for 16-field parser |
| `tests/test_tribes_rof.py` | Tests for corrected tribe IDs |
| `tests/test_server_profile.py` | Tests for shared profile loader |
| `tests/test_collector_rof.py` | End-to-end: parse → store → verify 16 fields in DB |

---

## Chunk 1: Fix Tribe ID Bug + Tests

This is the highest-priority fix — our code has tid 8 and 9 reversed vs official Travian docs. Verified on live RoF x10 data.

### Task 1: Write failing tests for correct tribe IDs

**Files:**
- Create: `tests/test_tribes_rof.py`
- Reference: `bot/tribes.py:178-214`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for RoF tribe ID correctness — tid 8=Spartans, tid 9=Vikings."""

from bot.tribes import TRIBES


def test_tid_8_is_spartans():
    """Official Travian docs: tid 8 = Spartans. Verified on live RoF x10."""
    tribe = TRIBES[8]
    assert tribe.name_en == "Spartans"
    assert tribe.name_pl == "Spartanie"
    assert tribe.emoji == "🛡️"


def test_tid_9_is_vikings():
    """Official Travian docs: tid 9 = Vikings. Verified on live RoF x10."""
    tribe = TRIBES[9]
    assert tribe.name_en == "Vikings"
    assert tribe.name_pl == "Wikingowie"
    assert tribe.emoji == "⛵"


def test_spartans_have_hoplite():
    """Spartans (tid=8) first unit is Hoplite."""
    assert TRIBES[8].units[0].name == "Hoplite"


def test_vikings_have_thrall():
    """Vikings (tid=9) first unit is Thrall."""
    assert TRIBES[9].units[0].name == "Thrall"


def test_all_tribes_have_unique_tids():
    """No duplicate tribe IDs."""
    tids = [t.tid for t in TRIBES.values()]
    assert len(tids) == len(set(tids))
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest tests/test_tribes_rof.py -v`
Expected: FAIL — `test_tid_8_is_spartans` fails (currently Vikings), `test_tid_9_is_vikings` fails (currently Spartans)

### Task 2: Fix the tribe ID swap

**Files:**
- Modify: `bot/tribes.py:178-214`

- [ ] **Step 3: Swap tid 8↔9 in tribes.py**

In `bot/tribes.py`, swap the two tribe blocks:

```python
    # ── Spartans (tid=8) ────────────────────────────────────────────
    tribes[8] = TribeDef(
        tid=8, name_pl="Spartanie", name_en="Spartans",
        emoji="🛡️", wall_type="Defensive Wall", icon_slug="spartan",
        units=(
            UnitDef("Hoplite", 50, 35, 30, 6, 1, "inf"),
            UnitDef("Sentinel", 0, 40, 22, 9, 1, "inf"),
            UnitDef("Shieldsman", 40, 85, 45, 8, 1, "inf"),
            UnitDef("Twinsteel Therion", 90, 55, 40, 6, 1, "inf"),
            UnitDef("Elpida Rider", 55, 120, 90, 16, 2, "cav"),
            UnitDef("Corinthian Crusher", 195, 80, 75, 9, 3, "cav"),
            UnitDef("Ram", 65, 30, 80, 4, 3, "siege"),
            UnitDef("Catapult", 50, 60, 10, 3, 6, "siege"),
            UnitDef("Ephor", 40, 60, 40, 4, 4, "special"),
            UnitDef("Settler", 0, 80, 80, 5, 1, "special"),
        ),
        settler_name="Settler",
    )

    # ── Vikings (tid=9) ─────────────────────────────────────────────
    tribes[9] = TribeDef(
        tid=9, name_pl="Wikingowie", name_en="Vikings",
        emoji="⛵", wall_type="Barricade", icon_slug="viking",
        units=(
            UnitDef("Thrall", 45, 22, 5, 7, 1, "inf"),
            UnitDef("Shield Maiden", 20, 50, 30, 7, 1, "inf"),
            UnitDef("Berserker", 70, 30, 25, 5, 2, "inf"),
            UnitDef("Heimdall's Eye", 0, 10, 5, 9, 1, "cav"),
            UnitDef("Huskarl Rider", 45, 95, 100, 12, 2, "cav"),
            UnitDef("Valkyrie's Blessing", 160, 50, 75, 9, 2, "cav"),
            UnitDef("Ram", 65, 30, 80, 4, 3, "siege"),
            UnitDef("Catapult", 50, 60, 10, 3, 6, "siege"),
            UnitDef("Jarl", 40, 40, 60, 5, 4, "special"),
            UnitDef("Settler", 0, 80, 80, 5, 1, "special"),
        ),
        settler_name="Settler",
    )
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/test_tribes_rof.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Run existing tribe tests — no regression**

Run: `python -m pytest tests/test_tribes.py -v`
Expected: All existing tests PASS (tid 1-7 unchanged)

### Task 3: Fix CLAUDE.md tribe documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 6: Update tribe ID table in CLAUDE.md**

Find the line:
```
**Tribe IDs (tid):** 1=Romans, 2=Teutons, 3=Gauls, 4=Nature, 5=Natars, 6=Egyptians, 7=Huns, 8=Vikings, 9=Spartans
```

Replace with:
```
**Tribe IDs (tid):** 1=Romans, 2=Teutons, 3=Gauls, 4=Nature, 5=Natars, 6=Egyptians, 7=Huns, 8=Spartans, 9=Vikings
```

- [ ] **Step 7: Commit chunk 1**

```bash
git add bot/tribes.py tests/test_tribes_rof.py CLAUDE.md
git commit -m "fix: swap tid 8↔9 — Spartans=8, Vikings=9

Verified against official Travian docs and live RoF x10 map.sql data.
Our code had these two tribes reversed, which caused wrong tribe names/icons.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 2: Shared Profile Loader + Config Refactor

Both Flask (`app/config.py`) and bot (`bot/tribes.py`) currently read `config.yaml` independently. We introduce a shared profile loader to prevent config divergence.

### Task 4: Write tests for profile loader

**Files:**
- Create: `tests/test_server_profile.py`
- Create: `app/server_profile.py`

- [ ] **Step 1: Write failing tests for profile loader**

```python
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
    from app.server_profile import load_profile
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
      regions: false
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
    from app.server_profile import load_profile
    with patch.dict(os.environ, {"SERVER_PROFILE": "rof-x3"}):
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
    from app.server_profile import load_profile
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
    from app.server_profile import load_profile
    with patch.dict(os.environ, {"TRAVIAN_SERVER_URL": "https://custom.url.com"}):
        profile = load_profile(config_yaml)
    assert profile["url"] == "https://custom.url.com"
```

- [ ] **Step 2: Run tests — expect FAIL (module doesn't exist)**

Run: `python -m pytest tests/test_server_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.server_profile'`

### Task 5: Implement shared profile loader

**Files:**
- Create: `app/server_profile.py`

- [ ] **Step 3: Create the profile loader**

```python
"""Shared server profile loader.

Single source of truth for server configuration. Used by both
Flask app (app/config.py) and Discord bot (bot/tribes.py).
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
    1. SERVER_PROFILE env var → selects named profile
    2. If not set → first profile in 'servers' dict
    3. Env overrides: TRAVIAN_SERVER_URL overrides profile url

    Returns a dict with keys: url, speed, tribes, our_alliances,
    features (dict), legionnaire_rebalanced (bool), plus any extras.
    """
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config" / "config.yaml"

    if not config_path.exists():
        log.warning("Config file not found: %s — using defaults", config_path)
        return _default_profile()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    servers = raw.get("servers")

    # Backward compat: if no 'servers' key, try flat 'travian' structure
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
        # First profile as default
        profile_name = next(iter(servers))
        profile = servers[profile_name]
        log.info("SERVER_PROFILE not set — using '%s'", profile_name)

    result = _normalize(profile, profile_name)

    # Env overrides
    env_url = os.environ.get("TRAVIAN_SERVER_URL")
    if env_url:
        result["url"] = env_url

    return result


def _normalize(profile: dict, name: str) -> dict:
    """Ensure all expected keys exist with defaults."""
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
    """Fallback profile when no config exists."""
    return _normalize({
        "url": os.environ.get("TRAVIAN_SERVER_URL", "https://ts31.x3.europe.travian.com"),
        "speed": 3,
        "tribes": [1, 2, 3],
    }, "default")


def _from_flat_config(raw: dict) -> dict:
    """Backward compat: convert old flat config.yaml to profile format."""
    travian = raw.get("travian", {})
    return _normalize({
        "url": os.environ.get("TRAVIAN_SERVER_URL", travian.get("server_url", "")),
        "speed": travian.get("speed_multiplier", 3),
        "tribes": travian.get("available_tribes", [1, 2, 3]),
        "our_alliances": travian.get("our_alliances", []),
        "troop_speed_multiplier": travian.get("troop_speed_multiplier", 2),
        "map_size": travian.get("map_size", 401),
    }, "legacy")
```

- [ ] **Step 4: Run profile loader tests — expect PASS**

Run: `python -m pytest tests/test_server_profile.py -v`
Expected: All 4 tests PASS

### Task 6: Restructure config.yaml

**Files:**
- Modify: `config/config.yaml`
- Modify: `config/config.example.yaml`

- [ ] **Step 5: Update config.yaml to new servers structure**

```yaml
# W.I.T.E.K — Wirtualny Informator Taktyczno-Ekonomiczny Koalicji
# Konfiguracja — wybór serwera: ustaw SERVER_PROFILE w .env

servers:
  ts31:
    url: "https://ts31.x3.europe.travian.com"
    speed: 3
    map_size: 401
    troop_speed_multiplier: 2
    tribes: [1, 2, 3, 6, 7, 8, 9]
    our_alliances: [14, 32, 46, 120]
    features:
      ships: false
      regions: false
      cities: false
      harbors: false
      victory_points: false
    legionnaire_rebalanced: false

  rof-x3:
    url: "https://rof.x3.international.travian.com"
    speed: 3
    map_size: 401
    troop_speed_multiplier: 2
    tribes: [1, 3, 6, 7, 8, 9]
    our_alliances: []
    features:
      ships: true
      regions: true
      cities: true
      harbors: true
      victory_points: true
    legionnaire_rebalanced: true

scheduler:
  fetch_interval_minutes: 60

alerts:
  pop_drop_threshold: 15
  new_village_radius: 30

attacks:
  auto_resolve_after_minutes: 120

extension:
  enabled: true
```

- [ ] **Step 6: Update config.example.yaml similarly** (same structure, placeholder values)

### Task 7: Wire profile loader into Flask Config

**Files:**
- Modify: `app/config.py`

- [ ] **Step 7: Refactor Config class to use profile loader**

Replace the `travian = _yaml.get("travian", {})` section in `app/config.py` with:

```python
    # Server profile (shared loader)
    from .server_profile import load_profile
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
```

Keep the scheduler/alerts/attacks config reading from YAML as-is (those are global, not per-server).

### Task 8: Wire profile loader into bot/tribes.py

**Files:**
- Modify: `bot/tribes.py:225-252`

- [ ] **Step 8: Replace `_load_travian_config()` with shared loader**

Replace `_load_travian_config()` function and its callers:

```python
def _load_travian_config() -> dict:
    """Load server profile using shared loader."""
    from app.server_profile import load_profile
    return load_profile()


def get_speed_multiplier() -> int:
    """Get troop speed multiplier from config (default 2)."""
    profile = _load_travian_config()
    return profile.get("troop_speed_multiplier", 2)


def get_available_tribes() -> list[int]:
    """Get list of available tribe IDs from config."""
    profile = _load_travian_config()
    raw = profile.get("tribes", [1, 2, 3])
    valid = [t for t in raw if t in _VALID_TIDS]
    if len(valid) != len(raw):
        log.warning("Filtered invalid tribe IDs from config: %s → %s", raw, valid)
    return valid if valid else [1, 2, 3]
```

- [ ] **Step 9: Run all tests — no regression**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 10: Commit chunk 2**

```bash
git add app/server_profile.py app/config.py bot/tribes.py config/ tests/test_server_profile.py .env.example
git commit -m "feat: shared profile loader + multi-server config

Introduce app/server_profile.py as single config source for both
Flask and bot. Config.yaml restructured to servers: dict with
per-server profiles selected by SERVER_PROFILE env var.
Backward compatible with flat travian: config.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 3: Parser 16-Field Support + Village Model

### Task 9: Write failing tests for 16-field parser

**Files:**
- Create: `tests/test_parser_rof.py`
- Reference: `app/map_sql/parser.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for 16-field RoF map.sql parser."""

from app.map_sql.parser import parse_line, VillageRow


def test_parse_rof_line_with_all_fields():
    """Full RoF line with region, capital, city, harbor, VP."""
    line = (
        "INSERT INTO `x_world` VALUES "
        "(5001,-15,88,9,7777,'Viking Village',3001,'VikingPlayer',"
        "500,'NORD',1250,'Venedae',FALSE,FALSE,TRUE,42);"
    )
    row = parse_line(line)
    assert row is not None
    assert row.map_id == 5001
    assert row.x == -15
    assert row.y == 88
    assert row.tid == 9
    assert row.population == 1250
    assert row.region == "Venedae"
    assert row.is_capital is False
    assert row.is_city is False
    assert row.has_harbor is True
    assert row.victory_points == 42


def test_parse_classic_line_nulls():
    """Classic server line — extra fields are NULL."""
    line = (
        "INSERT INTO x_world VALUES "
        "(1,-200,-200,3,10187,'Wioska',480,'player',38,'alliance',"
        "156,NULL,FALSE,NULL,NULL,NULL);"
    )
    row = parse_line(line)
    assert row is not None
    assert row.population == 156
    assert row.region is None
    assert row.is_capital is False
    assert row.is_city is None
    assert row.has_harbor is None
    assert row.victory_points is None


def test_parse_rof_line_with_null_region():
    """Oasis or special tile with NULL region."""
    line = (
        "INSERT INTO `x_world` VALUES "
        "(9999,0,0,4,0,'Occupied Oasis',0,'Nature',0,'',"
        "0,NULL,FALSE,NULL,NULL,NULL);"
    )
    row = parse_line(line)
    assert row is not None
    assert row.region is None
    assert row.victory_points is None


def test_parse_rof_capital():
    """Capital village flagged TRUE."""
    line = (
        "INSERT INTO `x_world` VALUES "
        "(100,50,-50,1,200,'Roma',300,'Caesar',"
        "10,'SPQR',5000,'Cimbri',TRUE,FALSE,FALSE,0);"
    )
    row = parse_line(line)
    assert row.is_capital is True
    assert row.is_city is False
    assert row.has_harbor is False
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest tests/test_parser_rof.py -v`
Expected: FAIL — `VillageRow` has no `region` attribute

### Task 10: Implement 16-field parser

**Files:**
- Modify: `app/map_sql/parser.py`

- [ ] **Step 3: Add new fields to VillageRow dataclass**

```python
@dataclass
class VillageRow:
    map_id: int
    x: int
    y: int
    tid: int  # tribe: 1=Romans, 2=Teutons, 3=Gauls, etc.
    vid: int  # village id
    name: str
    uid: int  # player id
    player_name: str
    aid: int  # alliance id
    alliance_name: str
    population: int
    # RoF extended fields (NULL on classic servers)
    region: str | None = None
    is_capital: bool | None = None
    is_city: bool | None = None
    has_harbor: bool | None = None
    victory_points: int | None = None
```

- [ ] **Step 4: Update regex and parse_line to capture 16 fields**

Replace the `_ROW_PATTERN` regex and `parse_line` function:

```python
_ROW_PATTERN = re.compile(
    r"INSERT\s+INTO\s+`?x_world`?\s+VALUES\s*\("
    r"(\d+),"               # 1: map_id
    r"(-?\d+),"             # 2: x
    r"(-?\d+),"             # 3: y
    r"(\d+),"               # 4: tid
    r"(\d+),"               # 5: vid
    r"'((?:[^'\\]|'')*)',"  # 6: village_name
    r"(\d+),"               # 7: uid
    r"'((?:[^'\\]|'')*)',"  # 8: player_name
    r"(\d+),"               # 9: aid
    r"'((?:[^'\\]|'')*)',"  # 10: alliance_name
    r"(\d+),"               # 11: population
    r"(NULL|'[^']*'),"      # 12: region (NULL or 'RegionName')
    r"(TRUE|FALSE|NULL),"   # 13: is_capital
    r"(TRUE|FALSE|NULL),"   # 14: is_city
    r"(TRUE|FALSE|NULL),"   # 15: has_harbor
    r"(\d+|NULL)"           # 16: victory_points
    r"\s*\);",
    re.IGNORECASE,
)


def _parse_bool(val: str) -> bool | None:
    """Parse SQL boolean: TRUE→True, FALSE→False, NULL→None."""
    v = val.upper()
    if v == "TRUE":
        return True
    if v == "FALSE":
        return False
    return None


def _parse_int_or_none(val: str) -> int | None:
    """Parse SQL int or NULL."""
    if val.upper() == "NULL":
        return None
    return int(val)


def _parse_region(val: str) -> str | None:
    """Parse region: NULL→None, 'Name'→Name."""
    if val.upper() == "NULL":
        return None
    return val.strip("'").replace("''", "'")


def parse_line(line: str) -> VillageRow | None:
    """Parse a single INSERT INTO x_world line. Returns None if not a valid row."""
    m = _ROW_PATTERN.match(line.strip())
    if not m:
        return None
    return VillageRow(
        map_id=int(m.group(1)),
        x=int(m.group(2)),
        y=int(m.group(3)),
        tid=int(m.group(4)),
        vid=int(m.group(5)),
        name=_unescape_sql(m.group(6)),
        uid=int(m.group(7)),
        player_name=_unescape_sql(m.group(8)),
        aid=int(m.group(9)),
        alliance_name=_unescape_sql(m.group(10)),
        population=int(m.group(11)),
        region=_parse_region(m.group(12)),
        is_capital=_parse_bool(m.group(13)),
        is_city=_parse_bool(m.group(14)),
        has_harbor=_parse_bool(m.group(15)),
        victory_points=_parse_int_or_none(m.group(16)),
    )
```

- [ ] **Step 5: Run new parser tests — expect PASS**

Run: `python -m pytest tests/test_parser_rof.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Run existing parser tests — check regression**

Run: `python -m pytest tests/test_parser.py -v`
Expected: May FAIL if existing test lines don't match new strict 16-field regex. Fix by ensuring old tests use all 16 fields.

- [ ] **Step 7: Fix any existing test regressions**

Update `tests/test_parser.py` test lines to include all 16 fields if needed — the existing lines already have `NULL,FALSE,NULL,NULL,NULL` trailing fields which should match.

### Task 11: Add Village model columns

**Files:**
- Modify: `app/models.py:21-45`
- Modify: `app/database.py:6-36`

- [ ] **Step 8: Add columns to Village model**

In `app/models.py`, add after `population`:

```python
    population = db.Column(db.Integer)
    # RoF extended fields (NULL on classic servers)
    region = db.Column(db.Text, nullable=True)
    is_capital = db.Column(db.Boolean, nullable=True)
    is_city = db.Column(db.Boolean, nullable=True)
    has_harbor = db.Column(db.Boolean, nullable=True)
    victory_points = db.Column(db.Integer, nullable=True)
```

- [ ] **Step 9: Add migration entries to _ensure_columns**

In `app/database.py`, add to the `expected` dict:

```python
    expected = {
        # ... existing entries ...
        "villages": {
            "region": "TEXT",
            "is_capital": "BOOLEAN",
            "is_city": "BOOLEAN",
            "has_harbor": "BOOLEAN",
            "victory_points": "INTEGER",
        },
    }
```

### Task 12: Update collector to store new fields

**Files:**
- Modify: `app/map_sql/collector.py:38-54`

- [ ] **Step 10: Pass new fields in store_snapshot**

Update the Village constructor in `store_snapshot()`:

```python
    villages = [
        Village(
            map_id=r.map_id,
            snapshot_id=snapshot.id,
            x=r.x, y=r.y,
            tid=r.tid, vid=r.vid,
            name=r.name, uid=r.uid,
            player_name=r.player_name,
            aid=r.aid,
            alliance_name=r.alliance_name,
            population=r.population,
            region=r.region,
            is_capital=r.is_capital,
            is_city=r.is_city,
            has_harbor=r.has_harbor,
            victory_points=r.victory_points,
        )
        for r in rows
    ]
```

### Task 13: Update player aggregation for mixed tribes

**Files:**
- Modify: `app/map_sql/collector.py:67-93`

- [ ] **Step 11: Add most-common-tribe logic**

Replace the simple `"tid": r.tid` assignment in `_update_players`:

```python
def _update_players(rows, now):
    """Update player aggregates from parsed village rows."""
    player_data = {}
    player_tribes = {}  # uid -> list of tids
    for r in rows:
        if r.uid == 0:
            continue
        if r.uid not in player_data:
            player_data[r.uid] = {
                "name": r.player_name,
                "aid": r.aid,
                "alliance_name": r.alliance_name,
                "total_pop": 0,
                "village_count": 0,
            }
            player_tribes[r.uid] = []
        player_data[r.uid]["total_pop"] += r.population
        player_data[r.uid]["village_count"] += 1
        player_tribes[r.uid].append(r.tid)

    for uid, data in player_data.items():
        # Most common tribe; tie → lowest tid (deterministic)
        tids = player_tribes[uid]
        from collections import Counter
        tid_counts = Counter(tids)
        primary_tid = min(tid_counts, key=lambda t: (-tid_counts[t], t))
        data["tid"] = primary_tid

        player = db.session.get(Player, uid)
        if player is None:
            player = Player(uid=uid, first_seen_at=now, **data)
            db.session.add(player)
        else:
            for key, val in data.items():
                setattr(player, key, val)
            player.last_updated_at = now
```

### Task 14: Write end-to-end collector test

**Files:**
- Create: `tests/test_collector_rof.py`

- [ ] **Step 12: Write e2e test: parse → store → verify**

```python
"""End-to-end test: RoF map.sql → collector → DB with 16 fields."""

import pytest
from app import create_app
from app.database import db
from app.models import Snapshot, Village, Player
from app.map_sql.collector import store_snapshot


@pytest.fixture
def app():
    app = create_app()
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app


ROF_MAP_SQL = """INSERT INTO `x_world` VALUES (1,50,-50,9,100,'Viking Town',200,'Ragnar',10,'NORD',1500,'Venedae',TRUE,FALSE,TRUE,100);
INSERT INTO `x_world` VALUES (2,51,-49,8,101,'Sparta City',201,'Leonidas',10,'NORD',2000,'Cimbri',FALSE,TRUE,FALSE,50);
INSERT INTO `x_world` VALUES (3,52,-48,9,102,'Second Viking',200,'Ragnar',10,'NORD',800,'Venedae',FALSE,FALSE,FALSE,30);
"""


def test_store_rof_snapshot(app):
    """16-field lines are parsed, stored, and queryable."""
    with app.app_context():
        snap = store_snapshot(ROF_MAP_SQL)
        assert snap.village_count == 3

        v1 = Village.query.filter_by(map_id=1, snapshot_id=snap.id).first()
        assert v1.region == "Venedae"
        assert v1.is_capital is True
        assert v1.has_harbor is True
        assert v1.victory_points == 100

        v2 = Village.query.filter_by(map_id=2, snapshot_id=snap.id).first()
        assert v2.region == "Cimbri"
        assert v2.is_city is True
        assert v2.has_harbor is False


def test_mixed_tribe_player(app):
    """Player with tid=9 and tid=8 villages gets most common tribe."""
    with app.app_context():
        store_snapshot(ROF_MAP_SQL)
        # Ragnar has 2 Viking (tid=9) villages, should be tid=9
        ragnar = Player.query.filter_by(uid=200).first()
        assert ragnar.tid == 9
        assert ragnar.village_count == 2


def test_classic_format_still_works(app):
    """Old 16-field line with NULLs still parses correctly."""
    classic_line = "INSERT INTO x_world VALUES (1,0,0,1,1,'Rome',1,'Caesar',1,'SPQR',500,NULL,FALSE,NULL,NULL,NULL);\n"
    with app.app_context():
        snap = store_snapshot(classic_line)
        v = Village.query.filter_by(map_id=1, snapshot_id=snap.id).first()
        assert v.region is None
        assert v.is_capital is False
        assert v.has_harbor is None
        assert v.victory_points is None
```

- [ ] **Step 13: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 14: Commit chunk 3**

```bash
git add app/map_sql/parser.py app/models.py app/database.py app/map_sql/collector.py tests/test_parser_rof.py tests/test_collector_rof.py
git commit -m "feat: 16-field map.sql parser + RoF village model

Parser now captures region, is_capital, is_city, has_harbor,
victory_points from all 16 map.sql fields. NULLs stored as-is.
Village model has new nullable columns via _ensure_columns.
Player aggregation uses most-common-tribe for mixed-tribe support.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 4: Docker Multi-Instance + Deep Links + Deploy Validation

### Task 15: Create RoF Docker Compose file

**Files:**
- Create: `docker-compose.rof.yml`
- Modify: `.env.example`

- [ ] **Step 1: Create docker-compose.rof.yml**

```yaml
# W.I.T.E.K — Docker Compose (RoF x3 International)
# Uruchomienie: docker compose -f docker-compose.rof.yml up -d
# Wymaga oddzielnego pliku .env.rof z konfiguracją RoF

services:
  witek-rof-db:
    image: postgres:16-alpine
    container_name: witek-rof-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-witek_rof}
      POSTGRES_USER: ${POSTGRES_USER:-witek}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Ustaw POSTGRES_PASSWORD w .env.rof}
    volumes:
      - witek-rof-pgdata:/var/lib/postgresql/data
    networks:
      - witek-rof-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-witek} -d ${POSTGRES_DB:-witek_rof}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  witek-rof-app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: witek-rof-app
    restart: unless-stopped
    ports:
      - "${WITEK_PORT:-5001}:5000"
    env_file:
      - .env.rof
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER:-witek}:${POSTGRES_PASSWORD}@witek-rof-db:5432/${POSTGRES_DB:-witek_rof}
      SERVER_PROFILE: rof-x3
      FLASK_DEBUG: "false"
    volumes:
      - ./config/config.yaml:/app/config/config.yaml:ro
    depends_on:
      witek-rof-db:
        condition: service_healthy
    networks:
      - witek-rof-net
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

volumes:
  witek-rof-pgdata:
    name: witek-rof-pgdata

networks:
  witek-rof-net:
    name: witek-rof-net
```

- [ ] **Step 2: Add SERVER_PROFILE to .env.example**

Add line: `SERVER_PROFILE=ts31  # or rof-x3`

- [ ] **Step 3: Create .env.rof.example**

Template for RoF-specific env:

```bash
# W.I.T.E.K — RoF x3 International Environment
SERVER_PROFILE=rof-x3
DISCORD_TOKEN=your-rof-bot-token-here
DISCORD_GUILD_ID=your-rof-guild-id
DISCORD_ALERTS_CHANNEL_ID=
DISCORD_DEFENSE_FORUM_ID=
DISCORD_DEF_ROLE_ID=
FLASK_SECRET_KEY=change-me-rof
POSTGRES_PASSWORD=change-me
WITEK_PORT=5001
EXT_API_TOKEN=
```

### Task 16: Add deep link helper

**Files:**
- Create: `bot/deep_links.py`
- Create: `tests/test_deep_links.py`

- [ ] **Step 4: Write deep link tests**

```python
"""Tests for in-game deep link URL generation."""

from bot.deep_links import map_link, send_troops_link, marketplace_link


def test_map_link():
    url = map_link("https://rof.x3.international.travian.com", 50, -30)
    assert url == "https://rof.x3.international.travian.com/position_details.php?x=50&y=-30"


def test_send_troops_link_reinforce():
    url = send_troops_link("https://example.com", 10, 20, event_type=2)
    assert "tt=2" in url
    assert "x=10" in url
    assert "y=20" in url


def test_marketplace_link():
    url = marketplace_link("https://example.com", -5, 15)
    assert "gid=17" in url
    assert "x=-5" in url
```

- [ ] **Step 5: Implement deep links module**

```python
"""In-game URL deep link generators for Travian Legends.

URLs open the corresponding game page when clicked by a logged-in player.
Designed for use in Discord embed fields.
"""


def map_link(server_url: str, x: int, y: int) -> str:
    """Link to map tile position details."""
    base = server_url.rstrip("/")
    return f"{base}/position_details.php?x={x}&y={y}"


def send_troops_link(
    server_url: str, x: int, y: int,
    event_type: int = 2, troops: dict[str, int] | None = None,
) -> str:
    """Link to send troops form. event_type: 2=reinforce, 3=attack, 4=raid."""
    base = server_url.rstrip("/")
    url = f"{base}/build.php?id=39&tt=2&x={x}&y={y}&eventType={event_type}"
    if troops:
        for unit_key, count in troops.items():
            url += f"&troop[{unit_key}]={count}"
    return url


def marketplace_link(server_url: str, x: int, y: int) -> str:
    """Link to marketplace send resources form."""
    base = server_url.rstrip("/")
    return f"{base}/build.php?gid=17&x={x}&y={y}&t=5"
```

- [ ] **Step 6: Run deep link tests**

Run: `python -m pytest tests/test_deep_links.py -v`
Expected: All PASS

### Task 17: Deploy validation on RoF x10 data

- [ ] **Step 7: Fetch live RoF x10 map.sql and validate parser**

```bash
python -c "
from app.map_sql.parser import parse_map_sql
import requests
r = requests.get('https://rof.x10.international.travian.com/map.sql', timeout=30)
rows = parse_map_sql(r.text)
print(f'Parsed {len(rows)} villages')
# Check we got RoF fields
has_region = sum(1 for v in rows if v.region is not None)
has_harbor = sum(1 for v in rows if v.has_harbor is True)
print(f'Villages with region: {has_region}')
print(f'Villages with harbor: {has_harbor}')
# Verify tribe IDs
vikings = [v for v in rows if v.tid == 9]
spartans = [v for v in rows if v.tid == 8]
print(f'Vikings (tid=9): {len(vikings)} villages')
print(f'Spartans (tid=8): {len(spartans)} villages')
if vikings:
    print(f'  Sample Viking player: {vikings[0].player_name}')
if spartans:
    print(f'  Sample Spartan player: {spartans[0].player_name}')
"
```

Expected: Successfully parses thousands of villages with region/harbor data.

- [ ] **Step 8: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 9: Commit chunk 4**

```bash
git add docker-compose.rof.yml .env.example bot/deep_links.py tests/test_deep_links.py
git commit -m "feat: RoF Docker Compose + deep links

Separate docker-compose.rof.yml for RoF x3 instance with own DB,
token, and SERVER_PROFILE=rof-x3. Deep link helpers for map,
send troops, and marketplace URLs.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 5: Rebalanced Legionnaire + Final Wiring

### Task 18: Conditional Legionnaire stats

**Files:**
- Modify: `bot/tribes.py`

- [ ] **Step 1: Write test for rebalanced Legionnaire**

Add to `tests/test_tribes_rof.py`:

```python
from bot.tribes import TRIBES, get_legionnaire_stats


def test_legionnaire_default_stats():
    """Standard Legionnaire (no rebalance)."""
    stats = get_legionnaire_stats(rebalanced=False)
    assert stats["def_cav"] == 50
    assert stats["speed"] == 6


def test_legionnaire_rebalanced_stats():
    """Rebalanced Legionnaire for RoF servers with Vikings."""
    stats = get_legionnaire_stats(rebalanced=True)
    assert stats["def_cav"] == 70
    assert stats["speed"] == 7
```

- [ ] **Step 2: Implement get_legionnaire_stats in tribes.py**

```python
def get_legionnaire_stats(rebalanced: bool = False) -> dict:
    """Get Legionnaire stats, optionally rebalanced for RoF.

    Rebalanced (on servers with Vikings, no Teutons):
    - Cav def: 50 → 70
    - Training time: 26:40 → 22:40 (not stored here)
    - Speed: 6 → 7
    """
    base = TRIBES[1].units[0]  # Legionnaire is first Roman unit
    if not rebalanced:
        return {"att": base.att, "def_inf": base.def_inf, "def_cav": base.def_cav, "speed": base.speed}
    return {
        "att": base.att,
        "def_inf": base.def_inf,
        "def_cav": 70,  # 50 → 70
        "speed": 7,     # 6 → 7
    }
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_tribes_rof.py -v`
Expected: All PASS

### Task 19: Final integration — run full suite + Docker build

- [ ] **Step 4: Run complete test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Docker build smoke test**

Run: `docker build -t witek:rof-test .`
Expected: Build succeeds

- [ ] **Step 6: Commit chunk 5**

```bash
git add bot/tribes.py tests/test_tribes_rof.py
git commit -m "feat: rebalanced Legionnaire stats for RoF

get_legionnaire_stats() returns adjusted cav def (70) and speed (7)
when rebalanced=True (RoF servers with Vikings, no Teutons).

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

- [ ] **Step 7: Final commit — update plan.md and CLAUDE.md**

Update CLAUDE.md with new architecture notes (multi-server, SERVER_PROFILE).

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for multi-server architecture

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
