# Sprint 3 Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 new Travian tribes (Egyptians, Huns, Vikings, Spartans), fix 5 data bugs in existing tribes, add auto-resolve attacks, crop balance command, and integration tests.

**Architecture:** New `bot/tribes.py` module with frozen dataclass definitions for all 9 tribes. `bot/utils.py` generates its existing dicts (UNIT_SPEEDS, UNIT_CROP, etc.) from tribes.py at import time — zero cog changes needed. Config-driven server settings replace hardcoded values.

**Tech Stack:** Python 3.12+, py-cord 2.6, Flask, SQLAlchemy, pytest, testcord, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-10-sprint3-phase1-design.md`

---

## Chunk 1: Foundation — `bot/tribes.py` module

### Task 1: Create UnitDef and TribeDef dataclasses with tests

**Files:**
- Create: `bot/tribes.py`
- Create: `tests/test_tribes.py`

- [ ] **Step 1: Write failing tests for dataclass structure**

```python
# tests/test_tribes.py
"""Tests for bot.tribes — unified tribe definitions."""

from bot.tribes import UnitDef, TribeDef, TRIBES


class TestUnitDef:
    def test_frozen_dataclass(self):
        u = UnitDef(name="Test", att=10, def_inf=20, def_cav=30,
                    speed=5, crop=1, unit_type="inf")
        assert u.name == "Test"
        assert u.speed_name == ""  # default empty
        assert u.aliases == ()     # default empty tuple

    def test_speed_name_override(self):
        u = UnitDef(name="Falangita", att=15, def_inf=40, def_cav=50,
                    speed=7, crop=1, unit_type="inf", speed_name="Falanga")
        assert u.speed_name == "Falanga"

    def test_immutable(self):
        u = UnitDef(name="Test", att=10, def_inf=20, def_cav=30,
                    speed=5, crop=1, unit_type="inf")
        import pytest
        with pytest.raises(AttributeError):
            u.att = 99


class TestTribeDef:
    def test_basic_structure(self):
        unit = UnitDef(name="Test", att=10, def_inf=20, def_cav=30,
                       speed=5, crop=1, unit_type="inf")
        tribe = TribeDef(tid=99, name_pl="Test", name_en="Test",
                         emoji="🧪", wall_type="Test Wall", units=(unit,),
                         icon_slug="test")
        assert tribe.tid == 99
        assert len(tribe.units) == 1
        assert tribe.settler_name == "Osadnik"
        assert tribe.chief_idx == 8
        assert tribe.icon_slug == "test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tribes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.tribes'`

- [ ] **Step 3: Create bot/tribes.py with dataclasses (no tribe data yet)**

```python
# bot/tribes.py
"""Unified Travian tribe and unit definitions.

Single source of truth for all unit stats, speeds, crop consumption,
and combat values. bot/utils.py generates its legacy dicts from here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tribes.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bot/tribes.py tests/test_tribes.py
git commit -m "feat: add UnitDef/TribeDef dataclasses (tribes.py foundation)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Add Romans, Teutons, Gauls tribe data with bugfixes

**Files:**
- Modify: `bot/tribes.py`
- Modify: `tests/test_tribes.py`

**Bugfixes applied:**
- Grom Teutatesa att: 90→100
- Gaul Ram def_cav: 70→105
- Equites Legati crop: 3→2
- Teuton Wódz crop: 5→4
- Gaul Wódz crop: 5→4

- [ ] **Step 1: Write failing tests for existing tribe data**

Add to `tests/test_tribes.py`:

```python
class TestExistingTribes:
    """Verify Romans, Teutons, Gauls data matches corrected kirilloid values."""

    def test_tribes_registry_has_base_tribes(self):
        assert 1 in TRIBES  # Romans
        assert 2 in TRIBES  # Teutons
        assert 3 in TRIBES  # Gauls

    def test_romans_unit_count(self):
        assert len(TRIBES[1].units) == 10  # 9 combat + settler

    def test_romans_metadata(self):
        r = TRIBES[1]
        assert r.name_pl == "Rzymianie"
        assert r.name_en == "Romans"
        assert r.emoji == "🏛️"
        assert r.wall_type == "City Wall"

    # --- Bugfix verifications ---
    def test_bugfix_theutates_thunder_att(self):
        """Grom Teutatesa attack should be 100, not 90."""
        gauls = TRIBES[3]
        tt = gauls.units[3]  # index 3 = Theutates Thunder
        assert tt.name == "Grom Teutatesa"
        assert tt.att == 100

    def test_bugfix_gaul_ram_def_cav(self):
        """Gaul Ram def_cav should be 105, not 70."""
        gauls = TRIBES[3]
        ram = gauls.units[6]  # index 6 = Ram
        assert ram.name == "Taran"
        assert ram.def_cav == 105

    def test_bugfix_equites_legati_crop(self):
        """Equites Legati crop should be 2, not 3."""
        romans = TRIBES[1]
        el = romans.units[3]  # index 3 = Equites Legati
        assert el.name == "Equites Legati"
        assert el.crop == 2

    def test_bugfix_teuton_chief_crop(self):
        """Teuton Wódz crop should be 4, not 5."""
        teutons = TRIBES[2]
        chief = teutons.units[8]  # index 8 = chief
        assert chief.name == "Wódz"
        assert chief.crop == 4

    def test_bugfix_gaul_chief_crop(self):
        """Gaul Wódz crop should be 4, not 5."""
        gauls = TRIBES[3]
        chief = gauls.units[8]
        assert chief.name == "Wódz"
        assert chief.crop == 4

    def test_legionista_full_stats(self):
        """Spot-check full stats for one Roman unit."""
        leg = TRIBES[1].units[0]
        assert leg.name == "Legionista"
        assert leg.att == 40
        assert leg.def_inf == 35
        assert leg.def_cav == 50
        assert leg.speed == 6
        assert leg.crop == 1
        assert leg.unit_type == "inf"

    def test_speed_name_legacy(self):
        """Units with different UNIT_SPEEDS names must have speed_name set."""
        gauls = TRIBES[3]
        falangita = gauls.units[0]
        assert falangita.name == "Falangita"
        assert falangita.speed_name == "Falanga"

        tt = gauls.units[3]
        assert tt.name == "Grom Teutatesa"
        assert tt.speed_name == "Piorun Teutatesa"

        druid = gauls.units[4]
        assert druid.name == "Jeździec druidzki"
        assert druid.speed_name == "Druid"
```

- [ ] **Step 2: Run tests — should fail (no tribe data yet)**

Run: `python -m pytest tests/test_tribes.py::TestExistingTribes -v`
Expected: FAIL — KeyError or AssertionError

- [ ] **Step 3: Implement Romans, Teutons, Gauls in tribes.py**

Add to `bot/tribes.py` after the TRIBES dict:

```python
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

    return tribes


# Build on import
TRIBES.update(_build_tribes())
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_tribes.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/tribes.py tests/test_tribes.py
git commit -m "feat: add Romans/Teutons/Gauls to tribes.py with 5 bugfixes

Fixes: TT att 90→100, Gaul Ram def_cav 70→105, EL crop 3→2,
Teuton/Gaul chief crop 5→4.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Add new tribes — Egyptians, Huns, Vikings, Spartans

**Files:**
- Modify: `bot/tribes.py`
- Modify: `tests/test_tribes.py`

- [ ] **Step 1: Write failing tests for new tribes**

Add to `tests/test_tribes.py`:

```python
class TestNewTribes:
    """Verify Egyptians, Huns, Vikings, Spartans data from kirilloid.ru."""

    def test_all_nine_tribes_present(self):
        for tid in [1, 2, 3, 6, 7, 8, 9]:
            assert tid in TRIBES, f"Missing tribe {tid}"

    # --- Egyptians (tid=6) ---
    def test_egyptians_metadata(self):
        t = TRIBES[6]
        assert t.name_pl == "Egipcjanie"
        assert t.emoji == "🏺"
        assert t.wall_type == "Stone Wall"

    def test_egyptians_unit_count(self):
        assert len(TRIBES[6].units) == 10

    def test_egyptians_resheph_chariot(self):
        rc = TRIBES[6].units[5]
        assert rc.name == "Resheph Chariot"
        assert rc.att == 110
        assert rc.def_inf == 120
        assert rc.def_cav == 150
        assert rc.speed == 10
        assert rc.crop == 3

    # --- Huns (tid=7) ---
    def test_huns_metadata(self):
        t = TRIBES[7]
        assert t.name_pl == "Hunowie"
        assert t.emoji == "🐎"

    def test_huns_mercenary_speed(self):
        """Mercenary speed=7 (official table, not kirilloid's 6)."""
        merc = TRIBES[7].units[0]
        assert merc.name == "Mercenary"
        assert merc.speed == 7

    def test_huns_marauder(self):
        mar = TRIBES[7].units[5]
        assert mar.name == "Marauder"
        assert mar.att == 180
        assert mar.speed == 14

    # --- Vikings (tid=8) ---
    def test_vikings_metadata(self):
        t = TRIBES[8]
        assert t.name_pl == "Wikingowie"
        assert t.emoji == "⛵"
        assert t.wall_type == "Barricade"

    def test_vikings_ram_crop(self):
        """Viking Ram crop=3 (official wiki, not kirilloid's 2)."""
        ram = TRIBES[8].units[6]
        assert ram.name == "Ram"
        assert ram.crop == 3

    def test_vikings_valkyrie(self):
        vb = TRIBES[8].units[5]
        assert vb.name == "Valkyrie's Blessing"
        assert vb.att == 160
        assert vb.speed == 9

    # --- Spartans (tid=9) ---
    def test_spartans_metadata(self):
        t = TRIBES[9]
        assert t.name_pl == "Spartanie"
        assert t.emoji == "🛡️"

    def test_spartans_corinthian_crusher(self):
        cc = TRIBES[9].units[5]
        assert cc.name == "Corinthian Crusher"
        assert cc.att == 195
        assert cc.speed == 9
        assert cc.crop == 3

    def test_spartans_four_infantry(self):
        """Spartans are unique: 4 infantry units."""
        s = TRIBES[9]
        inf_count = sum(1 for u in s.units if u.unit_type == "inf")
        assert inf_count == 4


class TestCrossTribeConsistency:
    """Cross-tribe data integrity checks."""

    def test_all_tribes_have_ram(self):
        for tid in [1, 2, 3, 6, 7, 8, 9]:
            rams = [u for u in TRIBES[tid].units if u.name in ("Taran", "Ram")]
            assert len(rams) == 1, f"Tribe {tid} missing ram"

    def test_all_tribes_have_catapult(self):
        for tid in [1, 2, 3, 6, 7, 8, 9]:
            cats = [u for u in TRIBES[tid].units
                    if u.name in ("Katapulta", "Katapulta ognista", "Trebusz", "Catapult")]
            assert len(cats) == 1, f"Tribe {tid} missing catapult"

    def test_all_tribes_have_10_units(self):
        for tid in [1, 2, 3, 6, 7, 8, 9]:
            assert len(TRIBES[tid].units) == 10, f"Tribe {tid} has {len(TRIBES[tid].units)} units"

    def test_all_chiefs_crop_4_or_5(self):
        for tid in [1, 2, 3, 6, 7, 8, 9]:
            tribe = TRIBES[tid]
            chief = tribe.units[tribe.chief_idx]
            assert chief.crop in (4, 5), f"Tribe {tid} chief crop={chief.crop}"
            assert chief.unit_type == "special"
```

- [ ] **Step 2: Run tests — should fail**

Run: `python -m pytest tests/test_tribes.py::TestNewTribes -v`
Expected: FAIL — KeyError: 6

- [ ] **Step 3: Add Egyptians, Huns, Vikings, Spartans to _build_tribes()**

Add inside `_build_tribes()` in `bot/tribes.py`, after Gauls:

```python
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
            UnitDef("Mercenary", 35, 40, 30, 7, 1, "inf"),  # speed=7 (official)
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
            UnitDef("Ram", 65, 30, 80, 4, 3, "siege"),  # crop=3 (official)
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
```

- [ ] **Step 4: Run all tribe tests**

Run: `python -m pytest tests/test_tribes.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/tribes.py tests/test_tribes.py
git commit -m "feat: add Egyptians, Huns, Vikings, Spartans (tid 6-9)

All base stats from kirilloid.ru/js/units.js, cross-verified with
official Travian wiki for Vikings. Huns Mercenary speed=7 (official).
Viking Ram crop=3 (official).

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Add config helpers to tribes.py

**Files:**
- Modify: `bot/tribes.py`
- Modify: `tests/test_tribes.py`

- [ ] **Step 1: Write tests for config helpers**

Add to `tests/test_tribes.py`:

```python
from unittest.mock import patch


class TestConfigHelpers:
    def test_get_speed_multiplier_default(self):
        from bot.tribes import get_speed_multiplier
        with patch("bot.tribes._load_travian_config", return_value={}):
            assert get_speed_multiplier() == 2  # fallback

    def test_get_speed_multiplier_from_config(self):
        from bot.tribes import get_speed_multiplier
        with patch("bot.tribes._load_travian_config",
                   return_value={"troop_speed_multiplier": 1}):
            assert get_speed_multiplier() == 1

    def test_get_available_tribes_default(self):
        from bot.tribes import get_available_tribes
        with patch("bot.tribes._load_travian_config", return_value={}):
            assert get_available_tribes() == [1, 2, 3]

    def test_get_available_tribes_from_config(self):
        from bot.tribes import get_available_tribes
        with patch("bot.tribes._load_travian_config",
                   return_value={"available_tribes": [1, 3, 6, 7, 8, 9]}):
            result = get_available_tribes()
            assert result == [1, 3, 6, 7, 8, 9]

    def test_get_available_tribes_filters_invalid(self):
        from bot.tribes import get_available_tribes
        with patch("bot.tribes._load_travian_config",
                   return_value={"available_tribes": [1, 2, 99, 3]}):
            result = get_available_tribes()
            assert 99 not in result
            assert 1 in result
```

- [ ] **Step 2: Run tests — should fail**

Run: `python -m pytest tests/test_tribes.py::TestConfigHelpers -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement config helpers**

Add to `bot/tribes.py`:

```python
import yaml
from pathlib import Path

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
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/test_tribes.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/tribes.py tests/test_tribes.py
git commit -m "feat: add config helpers (get_speed_multiplier, get_available_tribes)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 2: Refactor `bot/utils.py` + config + models

### Task 5: Refactor utils.py to generate dicts from tribes.py

**Files:**
- Modify: `bot/utils.py:30-220` (replace hardcoded dicts with generation)
- Modify: `bot/utils.py:384-388` (AVAILABLE_TRIBES in detect_possible_units)
- Modify: `bot/utils.py:612-683` (replace UNIT_COMBAT, _COMBAT_ABBREV)

**Critical:** All existing tests must still pass after this refactor. The public API of utils.py does not change.

- [ ] **Step 1: Run existing test suite as baseline**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ~385 tests PASS (record exact count)

- [ ] **Step 2: Replace TRIBE_NAMES, TRIBE_EMOJI, TRIBE_ICONS with generated versions**

In `bot/utils.py`, replace lines 34-40:

```python
# OLD:
# TRIBE_NAMES = {1: "Rzymianie", 2: "Germanie", 3: "Galowie"}
# TRIBE_EMOJI = {1: "🏛️", 2: "⚔️", 3: "🏹"}
# TRIBE_ICONS = { ... }

# NEW:
from bot.tribes import TRIBES, get_speed_multiplier, get_available_tribes

TRIBE_NAMES = {t.tid: t.name_pl for t in TRIBES.values()}
TRIBE_EMOJI = {t.tid: t.emoji for t in TRIBES.values()}
TRIBE_ICONS = {
    t.tid: f"{CDN_BASE}/global/tribes/{t.icon_slug}_medium.png"
    for t in TRIBES.values()
    if t.icon_slug  # only tribes with known CDN icons
}
```

- [ ] **Step 3: Replace TROOP_SPEED_MULTIPLIER + UNIT_SPEEDS with generated versions**

Replace lines 67-103:

```python
TROOP_SPEED_MULTIPLIER = get_speed_multiplier()
AVAILABLE_TRIBES = get_available_tribes()

UNIT_SPEEDS: dict[int, list[dict]] = {}
for _tid, _tribe in TRIBES.items():
    UNIT_SPEEDS[_tid] = [
        {
            "name": u.speed_name or u.name,
            "speed": u.speed * TROOP_SPEED_MULTIPLIER,
            "type": u.unit_type,
        }
        for u in _tribe.units
        if u.name not in (_tribe.settler_name, "Osadnik", "Settler")
    ]
```

- [ ] **Step 4: Replace UNIT_CROP with generated version**

Replace lines 110-159:

```python
UNIT_CROP: dict[int, list[dict]] = {}
for _tid, _tribe in TRIBES.items():
    UNIT_CROP[_tid] = [
        {"name": u.name, "crop": u.crop, "type": u.unit_type}
        for u in _tribe.units
    ]

# Nature / captured animals (tid=0) — NOT in TRIBES, keep manually
UNIT_CROP[0] = [
    {"name": "Szczur", "crop": 1, "type": "nature"},
    {"name": "Pająk", "crop": 1, "type": "nature"},
    {"name": "Wąż", "crop": 1, "type": "nature"},
    {"name": "Nietoperz", "crop": 1, "type": "nature"},
    {"name": "Dzik", "crop": 2, "type": "nature"},
    {"name": "Wilk", "crop": 2, "type": "nature"},
    {"name": "Niedźwiedź", "crop": 3, "type": "nature"},
    {"name": "Krokodyl", "crop": 3, "type": "nature"},
    {"name": "Tygrys", "crop": 4, "type": "nature"},
    {"name": "Słoń", "crop": 5, "type": "nature"},
]
```

- [ ] **Step 5: Replace _ALIASES with generated version + preserve nature/shared**

Replace lines 169-216. CRITICAL: Keep nature aliases and shared units ("Bohater", "Taran", etc.) that exist outside TRIBES:

```python
_ALIASES: dict[str, list[str]] = {}
for _tribe in TRIBES.values():
    for _u in _tribe.units:
        if _u.name not in _ALIASES:
            _ALIASES[_u.name] = [_u.name]
        if _u.aliases:
            _ALIASES[_u.name].extend(a for a in _u.aliases if a not in _ALIASES[_u.name])
        # Add speed_name as alias if different
        if _u.speed_name and _u.speed_name not in _ALIASES[_u.name]:
            _ALIASES[_u.name].append(_u.speed_name)

# Hero + Nature units (NOT in TRIBES — keep manually)
_ALIASES["Bohater"] = ["Bohater", "Bohatera"]
_NATURE_ALIASES = {
    "Szczur": ["Szczury", "Szczurów", "Szczur"],
    "Pająk": ["Pająki", "Pająków", "Pająk"],
    "Wąż": ["Węże", "Węży", "Wąż"],
    "Nietoperz": ["Nietoperze", "Nietoperzy", "Nietoperz"],
    "Dzik": ["Dziki", "Dzików", "Dzik"],
    "Wilk": ["Wilki", "Wilków", "Wilk"],
    "Niedźwiedź": ["Niedźwiedzie", "Niedźwiedzi", "Niedźwiedź"],
    "Krokodyl": ["Krokodyle", "Krokodyli", "Krokodyl"],
    "Tygrys": ["Tygrysy", "Tygrysów", "Tygrys"],
    "Słoń": ["Słonie", "Słoni", "Słoń"],
}
_ALIASES.update(_NATURE_ALIASES)

_UNIT_NAME_MAP: dict[str, str] = {}
for canonical, aliases in _ALIASES.items():
    for alias in aliases:
        _UNIT_NAME_MAP[alias.lower()] = canonical
    _UNIT_NAME_MAP[canonical.lower()] = canonical
```

- [ ] **Step 6: Replace UNIT_COMBAT + _COMBAT_ABBREV with generated versions**

Replace lines 612-683:

```python
UNIT_COMBAT: dict[int, list[dict]] = {}
for _tid, _tribe in TRIBES.items():
    UNIT_COMBAT[_tid] = [
        {"name": u.name, "att": u.att, "def_inf": u.def_inf,
         "def_cav": u.def_cav, "type": u.unit_type}
        for u in _tribe.units
        if u.name not in (_tribe.settler_name, "Osadnik", "Settler")
    ]

# Flat lookup (keep existing interface)
COMBAT_BY_NAME: dict[str, dict] = {}
for _tribe_id, _units in UNIT_COMBAT.items():
    for _u in _units:
        COMBAT_BY_NAME[_u["name"]] = {
            "att": _u["att"], "def_inf": _u["def_inf"],
            "def_cav": _u["def_cav"], "type": _u["type"],
            "tribe": _tribe_id,
        }

_COMBAT_ABBREV: dict[str, str] = {
    "ec": "Equites Caesaris", "ei": "Equites Imperatoris",
    "el": "Equites Legati", "ko": "Katapulta ognista",
    "rt": "Germański rycerz", "gt": "Grom Teutatesa",
    "jd": "Jeździec druidzki", "tt": "Grom Teutatesa",
    "imp": "Imperians", "pret": "Pretorianin",
    "leg": "Legionista", "pal": "Paladyn",
    "top": "Topornik", "fal": "Falangita", "haed": "Haeduan",
}
```

- [ ] **Step 7: Update detect_possible_units to use AVAILABLE_TRIBES**

In `bot/utils.py`, change the hardcoded `[1, 2, 3]` at line ~387:

```python
# OLD:
    tribes_to_check = (
        [attacker_tribe]
        if attacker_tribe and attacker_tribe in UNIT_SPEEDS
        else [1, 2, 3]
    )

# NEW:
    tribes_to_check = (
        [attacker_tribe]
        if attacker_tribe and attacker_tribe in UNIT_SPEEDS
        else AVAILABLE_TRIBES
    )
```

- [ ] **Step 8: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: Same number of tests PASS as Step 1 baseline. If any fail, fix and re-run.

- [ ] **Step 9: Commit**

```bash
git add bot/utils.py
git commit -m "refactor: generate utils.py dicts from tribes.py

All UNIT_SPEEDS, UNIT_CROP, UNIT_COMBAT, TRIBE_NAMES, TRIBE_EMOJI,
TRIBE_ICONS, _ALIASES now generated from TRIBES registry.
detect_possible_units() uses AVAILABLE_TRIBES from config.
Zero interface changes — all cog imports unchanged.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: Update config.yaml, app/config.py, and TRIBE_NAMES import

**Files:**
- Modify: `config/config.yaml`
- Modify: `app/config.py:41-58`
- Modify: `app/models.py:122` (remove TRIBE_NAMES)
- Modify: `app/routes/players.py:6` (update TRIBE_NAMES import source)

- [ ] **Step 1: Add new fields to config.yaml**

```yaml
travian:
  server_url: "https://ts31.x3.europe.travian.com"
  map_size: 401
  speed_multiplier: 3
  troop_speed_multiplier: 2
  available_tribes: [1, 2, 3, 6, 7, 8, 9]
  our_alliances: [14, 32, 46, 120]

attacks:
  auto_resolve_after_minutes: 120
```

- [ ] **Step 2: Update app/config.py to load new fields**

Add after line 48 (`TRAVIAN_OUR_ALLIANCES`):

```python
    TRAVIAN_SPEED_MULTIPLIER = travian.get("speed_multiplier", 3)
    TRAVIAN_TROOP_SPEED_MULTIPLIER = travian.get("troop_speed_multiplier", 2)
    TRAVIAN_AVAILABLE_TRIBES = travian.get("available_tribes", [1, 2, 3])

    # Attacks
    attacks = _yaml.get("attacks", {})
    AUTO_RESOLVE_AFTER_MINUTES = attacks.get("auto_resolve_after_minutes", 120)
```

- [ ] **Step 3: Remove TRIBE_NAMES from app/models.py and fix imports**

Delete line 122 from `app/models.py`:
```python
# DELETE: TRIBE_NAMES = {1: "Rzymianie", 2: "Germanie", 3: "Galowie"}
```

Update `app/routes/players.py` line 6:
```python
# OLD:
from ..models import Player, Village, Snapshot, TRIBE_NAMES

# NEW:
from ..models import Player, Village, Snapshot
from bot.utils import TRIBE_NAMES
```

If `bot.utils` can't be imported in Flask routes (circular), keep a minimal mapping in models.py generated from tribes.py:
```python
from bot.tribes import TRIBES
TRIBE_NAMES = {t.tid: t.name_pl for t in TRIBES.values()}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add config/config.yaml app/config.py app/models.py
git commit -m "feat: add per-server config (speed, tribes, auto-resolve)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: Update defense.py REPORT_UNIT_ORDER for new tribes

**Files:**
- Modify: `bot/cogs/defense.py:31-47`
- Modify: `tests/test_defense.py` (if report parsing tests exist for tribe detection)

- [ ] **Step 1: Extend REPORT_UNIT_ORDER with new tribes**

Add to `bot/cogs/defense.py` after Gauls entry:

```python
    6: [  # Egyptians
        "Slave Militia", "Ash Warden", "Khopesh Warrior",
        "Sopdu Explorer", "Anhur Guard", "Resheph Chariot",
        "Ram", "Catapult", "Nomarch", "Settler",
    ],
    7: [  # Huns
        "Mercenary", "Bowman", "Spotter",
        "Steppe Rider", "Marksman", "Marauder",
        "Ram", "Catapult", "Logades", "Settler",
    ],
    8: [  # Vikings
        "Thrall", "Shield Maiden", "Berserker",
        "Heimdall's Eye", "Huskarl Rider", "Valkyrie's Blessing",
        "Ram", "Catapult", "Jarl", "Settler",
    ],
    9: [  # Spartans
        "Hoplite", "Sentinel", "Shieldsman",
        "Twinsteel Therion", "Elpida Rider", "Corinthian Crusher",
        "Ram", "Catapult", "Ephor", "Settler",
    ],
```

- [ ] **Step 2: Update _UNIT_TO_TRIBE generation (line 50-54)**

The existing loop should automatically pick up the new entries. Verify shared names ("Ram", "Catapult", "Settler") are excluded from the mapping.

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_defense.py -v --tb=short`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add bot/cogs/defense.py
git commit -m "feat: extend report parser with new tribe unit orders

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7b: Update economy.py _TRIBE_CHOICE_MAP for new tribes

**Files:**
- Modify: `bot/cogs/economy.py:616` (hardcoded tribe dict)

**Dependencies:** Task 3 (TRIBES registry must exist)

- [ ] **Step 1: Write test**

```python
# tests/test_economy_tribes.py
def test_tribe_choice_map_includes_all_available_tribes():
    """_TRIBE_CHOICE_MAP must include all AVAILABLE_TRIBES, not just 3."""
    from bot.cogs.economy import _TRIBE_CHOICE_MAP
    from bot.utils import AVAILABLE_TRIBES, TRIBE_NAMES
    for tid in AVAILABLE_TRIBES:
        name = TRIBE_NAMES[tid]
        assert name in _TRIBE_CHOICE_MAP, f"Missing tribe {name} (tid={tid})"
        assert _TRIBE_CHOICE_MAP[name] == tid
```

- [ ] **Step 2: Replace hardcoded _TRIBE_CHOICE_MAP**

In `bot/cogs/economy.py`, replace line 616:
```python
# OLD:
_TRIBE_CHOICE_MAP = {"Rzymianie": 1, "Germanie": 2, "Galowie": 3}

# NEW:
from bot.utils import AVAILABLE_TRIBES, TRIBE_NAMES
_TRIBE_CHOICE_MAP = {TRIBE_NAMES[tid]: tid for tid in AVAILABLE_TRIBES}
```

- [ ] **Step 3: Green — test passes**

---

## Chunk 3: Auto-resolve + Crop balance

### Task 8: Add auto_resolved column + migration

**Files:**
- Modify: `app/models.py:92-119`
- Modify: `app/database.py` (auto-migration check for new column)
- Create: `migrations/003_auto_resolved.sql`

- [ ] **Step 1: Add auto_resolved column to AttackReport model**

In `app/models.py`, after line 117 (`resolved_at`), add:

```python
    auto_resolved = db.Column(db.Boolean, default=False)
```

- [ ] **Step 2: Create migration SQL file**

```sql
-- migrations/003_auto_resolved.sql
-- Sprint 3: Auto-resolve attack reports after timeout

ALTER TABLE attack_reports ADD COLUMN auto_resolved BOOLEAN DEFAULT FALSE;
UPDATE attack_reports SET auto_resolved = FALSE WHERE auto_resolved IS NULL;
CREATE INDEX IF NOT EXISTS ix_attack_reports_status_unix ON attack_reports (status, attack_unix);
```

- [ ] **Step 3: Add auto-migration logic to app/database.py**

Add a function that checks if column exists and runs ALTER TABLE if not. Call it after `db.create_all()`:

```python
def _run_auto_migrations(app):
    """Apply schema changes that db.create_all() doesn't handle."""
    from sqlalchemy import inspect, text
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [c["name"] for c in inspector.get_columns("attack_reports")]
        if "auto_resolved" not in columns:
            with db.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE attack_reports ADD COLUMN auto_resolved BOOLEAN DEFAULT FALSE"
                ))
                conn.execute(text(
                    "UPDATE attack_reports SET auto_resolved = FALSE WHERE auto_resolved IS NULL"
                ))
            app.logger.info("Migration: added auto_resolved column to attack_reports")

        # Index (safe to CREATE IF NOT EXISTS on both SQLite and PG)
        with db.engine.begin() as conn:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_attack_reports_status_unix "
                "ON attack_reports (status, attack_unix)"
            ))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/database.py migrations/003_auto_resolved.sql
git commit -m "feat: add auto_resolved column + migration + index

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 9: Implement auto-resolve background task

**Files:**
- Modify: `bot/cogs/attacks.py`
- Create: `tests/test_auto_resolve.py`

- [ ] **Step 1: Write tests for auto-resolve logic**

Tests use real DB via flask_app fixture (not mocks) to validate actual SQL queries:

```python
# tests/test_auto_resolve.py
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
    """Seed a real DefenseThread row (uses actual model fields)."""
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
            assert len(result) == 1  # one thread resolved

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
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_auto_resolve.py -v`
Expected: All PASS (these test pure logic, no imports from attacks.py needed)

- [ ] **Step 3: Add auto-resolve loop to Attacks cog**

Add to `bot/cogs/attacks.py`, inside the `Attacks` class:

```python
from discord.ext import tasks

@tasks.loop(minutes=5)
async def auto_resolve_loop(self):
    """Automatically resolve expired attack reports."""
    try:
        threshold = getattr(self.bot, 'flask_app', None)
        if not threshold:
            return

        from app.config import Config
        threshold_minutes = Config.AUTO_RESOLVE_AFTER_MINUTES

        resolved_threads = await db_query(self.bot, lambda: self._do_auto_resolve(threshold_minutes))

        for thread_info in (resolved_threads or []):
            try:
                thread = await self.bot.fetch_channel(thread_info["thread_id"])
                ids_text = ", ".join(f"#{i}" for i in thread_info["report_ids"])
                await thread.send(f"🕐 Ataki {ids_text} automatycznie rozwiązane (czas ataku minął)")
                await thread.edit(archived=True)
            except Exception:
                log.exception("Auto-resolve: nie udało się zarchiwizować wątku %s",
                              thread_info.get("thread_id"))
    except Exception:
        log.exception("Auto-resolve loop error")

def _do_auto_resolve(self, threshold_minutes: int) -> list[dict]:
    """DB-side auto-resolve logic. Returns list of resolved thread info."""
    from app.database import db
    from app.models import AttackReport, DefenseThread

    now = datetime.now(timezone.utc)
    now_unix = int(now.timestamp())
    threshold_unix = now_unix - (threshold_minutes * 60)

    resolved = []

    # 1. Thread-level: find active DefenseThreads
    active_threads = DefenseThread.query.filter_by(status="active").all()
    for dt in active_threads:
        reports = AttackReport.query.filter(
            AttackReport.forum_thread_id == dt.forum_thread_id,
            AttackReport.status != "resolved",
        ).all()

        if not reports:
            continue

        # All reports must have attack_unix and be past threshold
        all_expired = all(
            r.attack_unix and r.attack_unix < threshold_unix
            for r in reports
        )
        if not all_expired:
            continue

        report_ids = []
        for r in reports:
            r.status = "resolved"
            r.resolved_at = now
            r.auto_resolved = True
            report_ids.append(r.id)

        dt.status = "resolved"
        resolved.append({"thread_id": dt.forum_thread_id, "report_ids": report_ids})

    # 2. Orphan reports (no thread)
    orphans = AttackReport.query.filter(
        AttackReport.forum_thread_id.is_(None),
        AttackReport.status != "resolved",
        AttackReport.attack_unix.isnot(None),
        AttackReport.attack_unix < threshold_unix,
    ).all()
    for r in orphans:
        r.status = "resolved"
        r.resolved_at = now
        r.auto_resolved = True

    db.session.commit()
    return resolved

@auto_resolve_loop.before_loop
async def before_auto_resolve(self):
    await self.bot.wait_until_ready()
```

Start the loop in `cog_load` (with testing guard):

```python
def cog_load(self):
    if not getattr(self.bot, '_testing', False):
        self.auto_resolve_loop.start()

def cog_unload(self):
    self.auto_resolve_loop.cancel()
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/cogs/attacks.py tests/test_auto_resolve.py
git commit -m "feat: add auto-resolve background task for expired attacks

Runs every 5 minutes. Thread-level logic: all attacks in thread
must expire before auto-resolve. Configurable threshold (default 2h).

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 10: Implement /tzboza crop balance command

**Files:**
- Modify: `bot/cogs/defense.py`
- Create: `tests/test_crop_balance.py`

- [ ] **Step 1: Write tests for crop balance calculation**

```python
# tests/test_crop_balance.py
"""Tests for crop balance calculation."""

from bot.utils import calc_crop_consumption, HERO_CROP


class TestCropBalance:
    def test_simple_army(self):
        troops = {"Legionista": 100, "Imperians": 50}
        # Legionista=1crop, Imperians=1crop → 150
        assert calc_crop_consumption(troops) == 150

    def test_mixed_cavalry(self):
        troops = {"Equites Caesaris": 10, "Equites Imperatoris": 20}
        # EC=4crop*10=40, EI=3crop*20=60 → 100
        assert calc_crop_consumption(troops) == 100

    def test_hero_crop_constant(self):
        assert HERO_CROP == 6

    def test_new_tribe_units(self):
        troops = {"Marauder": 10, "Corinthian Crusher": 5}
        # Marauder=3crop*10=30, CC=3crop*5=15 → 45
        assert calc_crop_consumption(troops) == 45

    def test_empty_army(self):
        assert calc_crop_consumption({}) == 0
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_crop_balance.py -v`
Expected: All PASS (calc_crop_consumption already exists, new tribes added via tribes.py)

- [ ] **Step 3: Add /tzboza command to defense.py**

Add to `bot/cogs/defense.py` inside the Defense class:

```python
@discord.slash_command(name="tzboza", description="Bilans zbożowy wioski (zużycie vs produkcja)")
@discord.option("kordy", str, description="Koordynaty wioski np. 76|43 (auto w wątku)", required=False, default="")
@discord.option("produkcja", int, description="Produkcja zboża/h (nadpisuje dane z raportu)", required=False, default=0)
@discord.option("bohater", bool, description="Czy bohater jest w wiosce? (+6 🌾/h)", required=False, default=False)
async def tzboza(self, ctx: discord.ApplicationContext, kordy: str, produkcja: int, bohater: bool):
    await ctx.defer()

    # Parse coordinates (auto-detect from defense thread if in thread)
    x, y = None, None
    if kordy:
        parsed = parse_coords(kordy)
        if parsed:
            x, y = parsed
    if x is None and isinstance(ctx.channel, discord.Thread):
        thread_coords = await db_query(self.bot, lambda: self._get_thread_coords(ctx.channel.id))
        if thread_coords:
            x, y = thread_coords

    if x is None:
        await ctx.followup.send("❌ Podaj koordynaty wioski np. `76|43`", ephemeral=True)
        return

    data = await db_query(self.bot, lambda: self._gather_crop_data(x, y, produkcja))

    garrison_crop = data["garrison_crop"]
    support_crop = data["support_crop"]
    support_count = data["support_count"]
    hero_crop = HERO_CROP if bohater else 0
    total = garrison_crop + support_crop + hero_crop
    prod = data["production"] or produkcja
    balance = prod - total if prod else None

    lines = [f"🏠 Garnizon:      **-{garrison_crop}** 🌾/h"]
    if support_count:
        lines.append(f"🤝 Wsparcie ({support_count}):  **-{support_crop}** 🌾/h")
    if bohater:
        lines.append(f"🦸 Bohater:        **-{hero_crop}** 🌾/h")
    lines.append("━" * 28)
    lines.append(f"📉 Zużycie:       **-{total}** 🌾/h")

    if prod:
        lines.append(f"📈 Produkcja:     **+{prod}** 🌾/h")
        sign = "+" if balance >= 0 else ""
        color = COLOR_DEFENSE if balance >= 0 else COLOR_ATTACK
        lines.append(f"💰 Bilans:        **{sign}{balance}** 🌾/h")
        if balance < 0:
            lines.append(f"\n⚠️ Zboże się skończy przy obecnym zużyciu")
            if data.get("crop_amount") and data["crop_amount"] > 0:
                hours_left = data["crop_amount"] / abs(balance)
                if hours_left < 1:
                    eta_str = f"~{int(hours_left * 60)} min"
                elif hours_left < 24:
                    eta_str = f"~{hours_left:.1f}h"
                else:
                    eta_str = f"~{hours_left / 24:.1f} dni"
                lines.append(f"⏰ Czas do wyczerpania: **{eta_str}** (przy {data['crop_amount']} 🌾)")
    else:
        color = COLOR_INFO
        lines.append("📈 Produkcja:     *nie podano*")

    embed = discord.Embed(
        title=f"🌾 Bilans zbożowy — ({x}|{y})",
        description="\n".join(lines),
        color=color,
    )
    embed.set_footer(text=FOOTER)
    await ctx.followup.send(embed=embed)

def _get_thread_coords(self, thread_id: int):
    from app.models import DefenseThread
    dt = DefenseThread.query.filter_by(forum_thread_id=thread_id).first()
    if dt:
        return (dt.defender_x, dt.defender_y)
    return None

def _gather_crop_data(self, x: int, y: int, override_prod: int) -> dict:
    import json
    from app.models import VillageTroops, TroopSupport, AttackReport

    # Garrison
    vt = VillageTroops.query.filter_by(village_x=x, village_y=y).first()
    garrison_crop = 0
    if vt:
        troops = json.loads(vt.troops)
        garrison_crop = calc_crop_consumption(troops)

    # Support (all statuses)
    supports = TroopSupport.query.filter_by(to_x=x, to_y=y).all()
    support_crop = 0
    for s in supports:
        troops = json.loads(s.troops)
        support_crop += calc_crop_consumption(troops)

    # Production from latest attack report
    production = override_prod or 0
    crop_amount = 0
    if not production:
        report = AttackReport.query.filter(
            AttackReport.defender_x == x,
            AttackReport.defender_y == y,
            AttackReport.crop_production.isnot(None),
            AttackReport.crop_production > 0,
        ).order_by(AttackReport.created_at.desc()).first()
        if report:
            production = report.crop_production
            crop_amount = getattr(report, 'crop_amount', 0) or 0

    return {
        "garrison_crop": garrison_crop,
        "support_crop": support_crop,
        "support_count": len(supports),
        "production": production,
        "crop_amount": crop_amount,
    }
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/cogs/defense.py tests/test_crop_balance.py
git commit -m "feat: add /tzboza crop balance command

Shows garrison + support crop consumption, production, and net balance.
Auto-detects coordinates from defense thread context.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 4: Integration tests + final verification

### Task 11: Set up integration test infrastructure

**Files:**
- Modify: `requirements.txt`
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/conftest.py`
- Create: `pytest.ini` (or add to existing)

- [ ] **Step 1: Add test dependencies to requirements.txt**

Append to `requirements.txt`:

```
testcord>=0.1.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: Install new dependencies**

Run: `pip install testcord pytest-asyncio`

- [ ] **Step 3: Create pytest marker config**

Create `pytest.ini`:

```ini
[pytest]
markers =
    integration: Discord bot integration tests (require testcord)
asyncio_mode = auto
```

- [ ] **Step 4: Create integration test conftest**

```python
# tests/integration/__init__.py
```

```python
# tests/integration/conftest.py
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


@pytest.fixture
def flask_app():
    """Create Flask app with in-memory SQLite for testing.

    Uses TestConfig passed to create_app() so init_db() uses
    the test DB from the start (not the default witek.db).
    """
    from app import create_app
    from app.database import db

    app = create_app(config_class=TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt pytest.ini tests/integration/
git commit -m "feat: set up integration test infrastructure

Adds testcord, pytest-asyncio, marker config, and conftest fixtures.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 12: Write cog loading smoke tests

> Scope: Import smoke tests only — verifying all cogs load without errors.
> Real interactive Discord tests (using testcord) are deferred to Sprint 3 Phase 2.

**Files:**
- Create: `tests/integration/test_cog_loading.py`

- [ ] **Step 1: Write cog loading smoke tests**

```python
# tests/integration/test_cog_loading.py
"""Verify all cogs load without errors."""

import pytest


@pytest.mark.integration
class TestCogLoading:
    def test_attacks_cog_imports(self):
        from bot.cogs.attacks import Attacks
        assert Attacks is not None

    def test_defense_cog_imports(self):
        from bot.cogs.defense import Defense
        assert Defense is not None

    def test_economy_cog_imports(self):
        from bot.cogs.economy import Economy
        assert Economy is not None

    def test_general_cog_imports(self):
        from bot.cogs.general import General
        assert General is not None

    def test_identity_cog_imports(self):
        from bot.cogs.identity import Identity
        assert Identity is not None

    def test_alerts_cog_imports(self):
        from bot.cogs.alerts import AlertsCog
        assert AlertsCog is not None

    def test_tribes_module(self):
        from bot.tribes import TRIBES
        assert len(TRIBES) >= 7  # tid 1,2,3,6,7,8,9

    def test_utils_generated_dicts(self):
        from bot.utils import UNIT_SPEEDS, UNIT_CROP, UNIT_COMBAT, TRIBE_NAMES
        assert len(UNIT_SPEEDS) >= 7
        assert len(UNIT_CROP) >= 7
        assert len(UNIT_COMBAT) >= 7
        assert 6 in TRIBE_NAMES  # Egyptians
        assert 9 in TRIBE_NAMES  # Spartans
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/integration/test_cog_loading.py -v -m integration`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_cog_loading.py
git commit -m "test: add cog loading integration tests

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 13: Final verification — run full test suite

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS (previous ~385 + new tribe/crop/auto-resolve/integration tests)

- [ ] **Step 2: Verify bot starts locally**

Run: `python run.py --bot-only` (briefly, Ctrl+C after seeing "Bot ready")
Expected: No import errors, all cogs loaded

- [ ] **Step 3: Verify Docker build**

Run: `docker compose -f docker-compose.dev.yml build`
Expected: Build succeeds

- [ ] **Step 4: Update CLAUDE.md if needed**

Add new tribe IDs to the comment in CLAUDE.md:
```
### Tribe IDs in map.sql
1=Romans, 2=Teutons, 3=Gauls, 4=Nature, 5=Natars, 6=Egyptians, 7=Huns, 8=Vikings, 9=Spartans
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: Sprint 3 Phase 1 complete — verification pass

All tests pass, bot starts cleanly, Docker builds.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
