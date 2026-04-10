"""Unified Travian tribe and unit definitions.

Single source of truth for all unit stats, speeds, crop consumption,
and combat values. bot/utils.py generates its legacy dicts from here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UnitDef:
    """Single unit definition with all combat/economy attributes."""
    name: str           # Canonical name (Polish for tid 1-3, English for 6-9)
    att: int            # Base attack
    def_inf: int        # Defense vs infantry
    def_cav: int        # Defense vs cavalry
    speed: int          # Base speed (fields/h, before server multiplier)
    crop: int           # Crop consumption per hour
    unit_type: str      # inf / cav / siege / special
    speed_name: str = ""          # Legacy UNIT_SPEEDS name if different from name
    aliases: tuple[str, ...] = ()  # All alternative name forms


@dataclass(frozen=True)
class TribeDef:
    """Complete tribe definition."""
    tid: int
    name_pl: str
    name_en: str
    emoji: str
    wall_type: str
    units: tuple[UnitDef, ...]
    icon_slug: str = ""       # CDN icon filename base (e.g. "roman" → roman_medium.png)
    settler_name: str = "Osadnik"
    chief_idx: int = 8  # Index of chief/leader in units tuple


# Registry — populated by _build_tribes() below
TRIBES: dict[int, TribeDef] = {}


def _build_tribes() -> dict[int, TribeDef]:
    """Build the complete tribe registry."""
    tribes = {}

    # ── Romans (tid=1) ──────────────────────────────────────────────
    tribes[1] = TribeDef(
        tid=1, name_pl="Rzymianie", name_en="Romans",
        emoji="🏛️", wall_type="City Wall", icon_slug="roman",
        units=(
            UnitDef("Legionista", 40, 35, 50, 6, 1, "inf",
                    aliases=("Legioniści", "Legionistów")),
            UnitDef("Pretorianin", 30, 65, 35, 5, 1, "inf",
                    aliases=("Pretorianie", "Pretorianów")),
            UnitDef("Imperians", 70, 40, 25, 7, 1, "inf",
                    aliases=("Imperiansy", "Imperiansów")),
            UnitDef("Equites Legati", 0, 20, 10, 16, 2, "cav"),  # crop=2 (bugfix)
            UnitDef("Equites Imperatoris", 120, 65, 50, 14, 3, "cav"),
            UnitDef("Equites Caesaris", 180, 80, 105, 10, 4, "cav"),
            UnitDef("Taran", 60, 30, 75, 4, 3, "siege",
                    aliases=("Tarany", "Taranów")),
            UnitDef("Katapulta ognista", 75, 60, 10, 3, 6, "siege",
                    aliases=("Katapulty ogniste",)),
            UnitDef("Senator", 50, 40, 30, 4, 5, "special",
                    aliases=("Senatorzy", "Senatorów")),
            UnitDef("Osadnik", 0, 80, 80, 5, 1, "special",
                    aliases=("Osadnicy", "Osadników")),
        ),
    )

    # ── Teutons (tid=2) ─────────────────────────────────────────────
    tribes[2] = TribeDef(
        tid=2, name_pl="Germanie", name_en="Teutons",
        emoji="⚔️", wall_type="Earth Wall", icon_slug="teuton",
        units=(
            UnitDef("Pałkarz", 40, 20, 5, 7, 1, "inf",
                    aliases=("Pałkarze", "Pałkarzy")),
            UnitDef("Włócznik", 10, 35, 60, 7, 1, "inf",
                    aliases=("Włócznicy", "Włóczników")),
            UnitDef("Topornik", 60, 30, 30, 6, 1, "inf",
                    aliases=("Topornicy", "Toporników")),
            UnitDef("Zwiadowca", 0, 10, 5, 9, 1, "cav",
                    aliases=("Zwiadowcy", "Zwiadowców")),
            UnitDef("Paladyn", 55, 100, 40, 10, 2, "cav",
                    aliases=("Paladyni", "Paladynów")),
            UnitDef("Germański rycerz", 150, 50, 75, 9, 3, "cav",
                    speed_name="Rycerz Teutoński",
                    aliases=("Germańscy rycerze", "Germańskich rycerzy", "Rycerz Teutoński")),
            UnitDef("Taran", 65, 30, 80, 4, 3, "siege",
                    aliases=("Tarany", "Taranów")),
            UnitDef("Katapulta", 50, 60, 10, 3, 6, "siege",
                    aliases=("Katapulty", "Katapult")),
            UnitDef("Wódz", 40, 60, 40, 4, 4, "special",  # crop=4 (bugfix)
                    aliases=("Wodzowie", "Wodzów")),
            UnitDef("Osadnik", 0, 80, 80, 5, 1, "special",
                    aliases=("Osadnicy", "Osadników")),
        ),
    )

    # ── Gauls (tid=3) ───────────────────────────────────────────────
    tribes[3] = TribeDef(
        tid=3, name_pl="Galowie", name_en="Gauls",
        emoji="🏹", wall_type="Palisade", icon_slug="gaul",
        units=(
            UnitDef("Falangita", 15, 40, 50, 7, 1, "inf",
                    speed_name="Falanga",
                    aliases=("Falangi", "Falangitów", "Falanga")),
            UnitDef("Miecznik", 65, 35, 20, 6, 1, "inf",
                    aliases=("Miecznicy", "Mieczników")),
            UnitDef("Tropiciel", 0, 20, 10, 17, 2, "cav",
                    aliases=("Tropiciele", "Tropicieli")),
            UnitDef("Grom Teutatesa", 100, 25, 40, 19, 2, "cav",  # att=100 (bugfix)
                    speed_name="Piorun Teutatesa",
                    aliases=("Gromy Teutatesa", "Gromów Teutatesa", "Piorun Teutatesa")),
            UnitDef("Jeździec druidzki", 45, 115, 55, 16, 2, "cav",
                    speed_name="Druid",
                    aliases=("Jeźdźcy druidzcy", "Jeźdźców druidzkich", "Druid")),
            UnitDef("Haeduan", 140, 50, 165, 13, 3, "cav",
                    aliases=("Haeduanowie", "Haeduanów")),
            UnitDef("Taran", 50, 30, 105, 4, 3, "siege",  # def_cav=105 (bugfix)
                    aliases=("Tarany", "Taranów")),
            UnitDef("Trebusz", 70, 45, 10, 3, 6, "siege",
                    aliases=("Trebusze", "Trebuszów")),
            UnitDef("Wódz", 40, 50, 50, 5, 4, "special",  # crop=4 (bugfix)
                    aliases=("Wodzowie", "Wodzów")),
            UnitDef("Osadnik", 0, 80, 80, 5, 1, "special",
                    aliases=("Osadnicy", "Osadników")),
        ),
    )

    # ── Egyptians (tid=6) ───────────────────────────────────────────
    tribes[6] = TribeDef(
        tid=6, name_pl="Egipcjanie", name_en="Egyptians",
        emoji="🏺", wall_type="Stone Wall", icon_slug="egyptian",
        units=(
            UnitDef("Slave Militia", 10, 30, 20, 7, 1, "inf"),
            UnitDef("Ash Warden", 30, 55, 40, 6, 1, "inf"),
            UnitDef("Khopesh Warrior", 65, 50, 20, 7, 1, "inf"),
            UnitDef("Sopdu Explorer", 0, 20, 10, 16, 2, "cav"),
            UnitDef("Anhur Guard", 50, 110, 50, 15, 2, "cav"),
            UnitDef("Resheph Chariot", 110, 120, 150, 10, 3, "cav"),
            UnitDef("Ram", 55, 30, 95, 4, 3, "siege"),
            UnitDef("Catapult", 65, 55, 10, 3, 6, "siege"),
            UnitDef("Nomarch", 40, 50, 50, 4, 4, "special"),
            UnitDef("Settler", 0, 80, 80, 5, 1, "special"),
        ),
        settler_name="Settler",
    )

    # ── Huns (tid=7) ────────────────────────────────────────────────
    tribes[7] = TribeDef(
        tid=7, name_pl="Hunowie", name_en="Huns",
        emoji="🐎", wall_type="Makeshift Wall", icon_slug="hun",
        units=(
            UnitDef("Mercenary", 35, 40, 30, 7, 1, "inf"),
            UnitDef("Bowman", 50, 30, 10, 6, 1, "inf"),
            UnitDef("Spotter", 0, 20, 10, 19, 2, "cav"),
            UnitDef("Steppe Rider", 120, 30, 15, 16, 2, "cav"),
            UnitDef("Marksman", 110, 80, 70, 15, 2, "cav"),
            UnitDef("Marauder", 180, 60, 40, 14, 3, "cav"),
            UnitDef("Ram", 65, 30, 90, 4, 3, "siege"),
            UnitDef("Catapult", 45, 55, 10, 3, 6, "siege"),
            UnitDef("Logades", 50, 40, 30, 5, 4, "special"),
            UnitDef("Settler", 0, 80, 80, 5, 1, "special"),
        ),
        settler_name="Settler",
    )

    # ── Vikings (tid=8) ─────────────────────────────────────────────
    tribes[8] = TribeDef(
        tid=8, name_pl="Wikingowie", name_en="Vikings",
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

    # ── Spartans (tid=9) ────────────────────────────────────────────
    tribes[9] = TribeDef(
        tid=9, name_pl="Spartanie", name_en="Spartans",
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

    return tribes


# Build on import
TRIBES.update(_build_tribes())

_VALID_TIDS = frozenset(TRIBES.keys())


def _load_travian_config() -> dict:
    """Load travian section from config.yaml."""
    config_path = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("travian", {})
    return {}


def get_speed_multiplier() -> int:
    """Get troop speed multiplier from config (default 2)."""
    cfg = _load_travian_config()
    val = cfg.get("troop_speed_multiplier", 2)
    if val not in (1, 2):
        log.warning("Invalid troop_speed_multiplier=%s, using 2", val)
        return 2
    return val


def get_available_tribes() -> list[int]:
    """Get list of available tribe IDs from config (default [1,2,3])."""
    cfg = _load_travian_config()
    raw = cfg.get("available_tribes", [1, 2, 3])
    valid = [t for t in raw if t in _VALID_TIDS]
    if len(valid) != len(raw):
        log.warning("Filtered invalid tribe IDs from config: %s → %s", raw, valid)
    return valid if valid else [1, 2, 3]
