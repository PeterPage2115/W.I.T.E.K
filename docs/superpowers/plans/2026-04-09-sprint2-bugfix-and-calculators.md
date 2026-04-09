# Sprint 2: Bugfixes + Kalkulatory Taktyczne — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 bugs, enhance battle report parser with kill-cost, add 3 new tactical calculator commands (`/tbezpieczne`, `/tileobrony`, `/tprzechwyc`).

**Architecture:** All new commands go in `bot/cogs/economy.py` (existing cog for calculators). New utility functions in `bot/utils.py`. All DB access via `db_query()` returning plain dicts. All distance calculations use `torus_distance(..., map_size)`. `UNIT_SPEEDS` already includes x2 multiplier for x3 server — do NOT multiply again.

**Tech Stack:** Python 3.11+, py-cord (Discord), SQLAlchemy, SQLite/PostgreSQL, pytest

**Spec:** `docs/superpowers/specs/2026-04-09-bugfix-and-features-design.md`

**Rubber-duck findings incorporated:**
1. Use inverse of `_calc_travel_seconds()` for `/tbezpieczne` (not linear formula)
2. Use `simulate_combat()` as foundation for `/tileobrony` (handle inf/cav split)
3. Show ranges via `detect_possible_units()` for `/tprzechwyc` (not single speed)
4. Stay with generic `WALL_BONUS` for v1 (no tribe-specific wall types)
5. Data source: `Snapshot/Village` via `db_query()` (not raw map.sql)
6. `torus_distance()` mandatory for all distance calcs
7. Kill-cost needs new DB fields on `BattleReport`
8. Add coord-based lock for thread creation race condition
9. Drop pact filtering from v1 (no pact model exists)

---

## File Structure

### Modified files:
| File | Responsibility | Changes |
|------|---------------|---------|
| `bot/utils.py` | Shared constants, travel formulas, combat | Add `calc_safe_distance()`, `calc_needed_defense()`, `calc_interception_times()` |
| `bot/cogs/economy.py` | Calculator commands | Add `/tbezpieczne`, `/tileobrony`, `/tprzechwyc` |
| `bot/cogs/attacks.py` | Attack reporting | Add coord-based lock for thread creation race, fix empty alliance brackets |
| `bot/cogs/defense.py` | Report parser + embed | Add kill-cost regex to `parse_battle_report()`, display kill-cost in `_build_report_embed()`, fix empty alliance brackets |
| `bot/cogs/general.py` | Bot info/help | Version bump 0.1.0 → 1.0.0, add new commands to `/thelp` |
| `app/models.py` | DB models | Add `kill_cost_atk`, `kill_cost_def` to `BattleReport` |
| `app/database.py` | DB migration | Add kill-cost columns to `_ensure_columns()` |
| `docs/ROADMAP.md` | Project roadmap | Sync with actual implemented state |

### Test files:
| File | What it tests |
|------|--------------|
| `tests/test_safe_distance.py` (new) | `calc_safe_distance()` — inverse travel formula |
| `tests/test_defense_calc.py` (new) | `calc_needed_defense()` — defense estimation |
| `tests/test_interception.py` (new) | `calc_interception_times()` — send-time ranges |
| `tests/test_defense.py` (modify) | Kill-cost parsing in battle reports |
| `tests/test_thread_race.py` (new) | Coord-based lock for thread creation |

---

## Chunk 1: Bugfixes

### Task 1: Fix duplicate defense thread race condition

**Context:** Two simultaneous `/tatak` commands for the same village can race past the "check existing thread" and both create new threads. Current code at `attacks.py:206-241` checks DB then creates — no atomic guard. There's already a `_thread_locks` dict (line 31) for per-thread locks, but the lock is by thread_id (which doesn't exist yet during creation).

**Files:**
- Modify: `bot/cogs/attacks.py:25-37` (lock dict) and `bot/cogs/attacks.py:206-241` (thread creation)
- Create: `tests/test_thread_race.py`

- [ ] **Step 1: Write failing test for coord-based lock**

```python
# tests/test_thread_race.py
"""Test coord-based locking for defense thread creation."""

import asyncio
import pytest
from bot.cogs.attacks import _get_coord_lock, _coord_locks


class TestCoordLock:
    """Verify coord-based lock prevents duplicate thread creation."""

    def test_same_coords_return_same_lock(self):
        _coord_locks.clear()
        lock1 = _get_coord_lock(76, 43)
        lock2 = _get_coord_lock(76, 43)
        assert lock1 is lock2

    def test_different_coords_return_different_locks(self):
        _coord_locks.clear()
        lock1 = _get_coord_lock(76, 43)
        lock2 = _get_coord_lock(100, 50)
        assert lock1 is not lock2

    def test_lock_is_asyncio_lock(self):
        _coord_locks.clear()
        lock = _get_coord_lock(1, 2)
        assert isinstance(lock, asyncio.Lock)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_thread_race.py -v`
Expected: ImportError — `_get_coord_lock` and `_coord_locks` don't exist yet.

- [ ] **Step 3: Add coord-based lock to attacks.py**

In `bot/cogs/attacks.py`, after the existing `_thread_locks` dict (line 31), add:

```python
# Per-coordinate lock to prevent duplicate thread creation (rubber-duck finding #5)
_coord_locks: dict[tuple[int, int], asyncio.Lock] = {}


def _get_coord_lock(x: int, y: int) -> asyncio.Lock:
    key = (x, y)
    if key not in _coord_locks:
        _coord_locks[key] = asyncio.Lock()
    return _coord_locks[key]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_thread_race.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Wrap thread creation in coord lock**

In `bot/cogs/attacks.py`, find the `/tatak` handler section that checks for existing thread (~line 206-241). Replace:

```python
        existing_thread_id = await db_query(self.bot, _check_existing_thread)

        if existing_thread_id:
```

With:

```python
        coord_lock = _get_coord_lock(def_x, def_y)
        async with coord_lock:
            existing_thread_id = await db_query(self.bot, _check_existing_thread)

            if existing_thread_id:
                # Add to existing thread instead of creating a new one
                try:
                    thread = await self.bot.fetch_channel(existing_thread_id)
                    await thread.send(
                        content=f"➕ **Kolejny atak #{report_id}** dodany do wątku",
                        embed=embed,
                    )
                except Exception:
                    log.exception("Nie udało się dodać ataku do istniejącego wątku %d", existing_thread_id)
                await self._update_thread_summary(existing_thread_id)
            else:
                # Create new forum thread for defense coordination
                defender_name = def_vill["player"] if def_vill else None
                await self._create_defense_thread(
                    ctx, report_id, embed, def_vill, def_x, def_y,
                    defender_name, resolved_attacker, attack_unix,
                    defense_info=defense_info,
                )
```

Note: The entire check+create block must be inside `async with coord_lock:`. The old code after the lock block (log.info at ~line 243) stays outside.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All 357+ tests pass (no regressions).

- [ ] **Step 7: Commit**

```bash
git add bot/cogs/attacks.py tests/test_thread_race.py
git commit -m "fix: add coord-based lock to prevent duplicate defense threads

Race condition: two /tatak for same village could create duplicate threads.
Now uses asyncio.Lock keyed by (x, y) coordinates.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Version bump and ROADMAP sync

**Files:**
- Modify: `bot/cogs/general.py:122` (version string)
- Modify: `docs/ROADMAP.md` (full rewrite)

- [ ] **Step 1: Bump version in general.py**

In `bot/cogs/general.py`, line 122, change:
```python
        embed.add_field(name="Wersja", value="0.1.0", inline=True)
```
to:
```python
        embed.add_field(name="Wersja", value="1.0.0", inline=True)
```

- [ ] **Step 2: Rewrite ROADMAP.md to match actual state**

Replace `docs/ROADMAP.md` entirely with content reflecting what's actually implemented (10 cogs, 357 tests, all features through Slice 5.7). Mark the new Sprint 2 features (calculators) as "W trakcie". Key sections:
- ✅ Zrealizowane: Fazy 1-3.5, most of 4-5 (symulacja, porównanie, cropper, digest, mapa 2D)
- 🔧 W trakcie: Sprint 2 kalkulatory (/tbezpieczne, /tileobrony, /tprzechwyc)
- 📋 Planowane: Discord OAuth, RBAC, deploy prod, browser extension

- [ ] **Step 3: Run tests (sanity check)**

Run: `python -m pytest tests/test_combat_sim.py tests/test_unit_detector.py -v`
Expected: All pass (version change is cosmetic).

- [ ] **Step 4: Commit**

```bash
git add bot/cogs/general.py docs/ROADMAP.md
git commit -m "chore: bump version to 1.0.0, sync ROADMAP with actual state

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2b: Fix empty alliance brackets in attack embeds

**Context:** When a player has no alliance (or whitespace-only alliance name), attack embeds display `[ ]` or `[—]`. The bracket wrapping at `attacks.py` lines ~658/666 and `defense.py` lines ~961/994 should be conditional — only show `[AllianceName]` if the name is non-empty/non-whitespace.

**Files:**
- Modify: `bot/cogs/attacks.py` (~lines 658, 666 — `_build_attack_embed()`)
- Modify: `bot/cogs/defense.py` (~lines 961, 994 — `_build_report_embed()`)

- [ ] **Step 1: Fix alliance brackets in attacks.py `_build_attack_embed()`**

Find lines that display alliance in brackets and make them conditional:

```python
# Before:
f"[{def_info['alliance']}] {def_info['player']}"
# After:
(f"[{def_info['alliance']}] " if def_info.get('alliance', '').strip() else "") + f"{def_info['player']}"
```

Apply the same pattern for attacker alliance display.

- [ ] **Step 2: Fix alliance brackets in defense.py `_build_report_embed()`**

In `_build_report_embed()`, lines ~961 and ~994, change:

```python
# Before:
        if atk.get("alliance"):
            atk_text += f"[{atk['alliance']}] "
# After:
        if atk.get("alliance", "").strip():
            atk_text += f"[{atk['alliance']}] "
```

Same for defender section (~line 994).

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/ -v --tb=short -k "attack or defense or embed"`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add bot/cogs/attacks.py bot/cogs/defense.py
git commit -m "fix: hide empty alliance brackets in attack/report embeds

Skip [alliance] prefix when alliance name is empty or whitespace-only.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Add kill-cost fields to BattleReport model + DB migration

**Context:** `BattleReport` in `app/models.py` has `bounty` (JSON) and `battle_power_atk`/`battle_power_def` (int) but no kill-cost fields. The parser needs somewhere to store parsed "Koszt zabitych" values. Existing tables are migrated via `_ensure_columns()` in `app/database.py` — adding the column to the model alone is NOT enough for existing DBs.

**Files:**
- Modify: `app/models.py:164-192` (BattleReport model)
- Modify: `app/database.py:6-33` (_ensure_columns migration)

- [ ] **Step 1: Add kill_cost fields to BattleReport model**

In `app/models.py`, after line 185 (`battle_power_def`), add:

```python
    kill_cost_atk = db.Column(db.Text, nullable=True)  # JSON {resource: amount}
    kill_cost_def = db.Column(db.Text, nullable=True)  # JSON {resource: amount}
```

- [ ] **Step 2: Add kill_cost columns to _ensure_columns() migration**

In `app/database.py`, in the `_ensure_columns()` function, add to the `"battle_reports"` dict:

```python
        "battle_reports": {
            "result": "TEXT",
            "is_manual": "BOOLEAN DEFAULT 0",
            "reported_by_name": "TEXT",
            "kill_cost_atk": "TEXT",
            "kill_cost_def": "TEXT",
        },
```

- [ ] **Step 3: Verify app starts and migration runs**

Run: `python -c "from app import create_app; app = create_app(); print('OK')"`
Expected: Prints "OK". If existing DB exists, migration log shows "added battle_reports.kill_cost_atk" etc.

- [ ] **Step 4: Commit**

```bash
git add app/models.py app/database.py
git commit -m "feat: add kill_cost_atk/def fields to BattleReport model

Stores parsed 'Koszt zabitych' resource costs as JSON.
Includes _ensure_columns() migration for existing databases.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Enhance parser with kill-cost extraction + embed display

**Context:** The battle report text from Travian contains a "Koszt zabitych" section with resource costs. Current parser at `bot/cogs/defense.py` already handles bounty (line 197-217) and stats (line 237-257). We need to add kill-cost parsing AND display it in `_build_report_embed()` (line 942+).

Travian kill-cost format (tab-separated, similar to bounty):
```
Koszt zabitych
Drewno	11250	Drewno	8200
Glina	9700	Glina	6500
Żelazo	14800	Żelazo	9100
Zboże	7100	Zboże	4300
```

**Files:**
- Modify: `bot/cogs/defense.py` (add kill-cost parsing to `parse_battle_report()` + display in `_build_report_embed()`)
- Modify: `tests/test_defense.py` (add kill-cost test to existing battle report test class)

- [ ] **Step 1: Write failing test for kill-cost parsing**

Add to `tests/test_defense.py` (after existing `TestParseBattleReport` class):

```python
class TestKillCostParsing:
    """Test extraction of 'Koszt zabitych' from battle reports."""

    def test_parse_kill_cost_basic(self):
        """Kill cost section is parsed into attacker/defender dicts."""
        from bot.cogs.defense import parse_battle_report

        report_text = (
            "Atakujący\tOrzel\n"
            "Wioska\tOsada\n"
            "Pałkarz\t100\t0\n"
            "Straty\t50\t0\n"
            "Obrońca\tKnight\n"
            "Wioska\tZamek\n"
            "Falangita\t200\t0\n"
            "Straty\t30\t0\n"
            "Koszt zabitych\n"
            "Drewno\t5000\tDrewno\t3000\n"
            "Glina\t4000\tGlina\t2500\n"
            "Żelazo\t6000\tŻelazo\t4000\n"
            "Zboże\t2000\tZboże\t1500\n"
        )
        result = parse_battle_report(report_text)
        assert result["kill_cost_atk"] == {
            "Drewno": 5000, "Glina": 4000, "Żelazo": 6000, "Zboże": 2000
        }
        assert result["kill_cost_def"] == {
            "Drewno": 3000, "Glina": 2500, "Żelazo": 4000, "Zboże": 1500
        }

    def test_parse_no_kill_cost(self):
        """Reports without kill cost section return None for both."""
        from bot.cogs.defense import parse_battle_report

        report_text = (
            "Atakujący\tOrzel\n"
            "Wioska\tOsada\n"
            "Pałkarz\t100\t0\n"
            "Obrońca\tKnight\n"
            "Wioska\tZamek\n"
            "Falangita\t200\t0\n"
        )
        result = parse_battle_report(report_text)
        assert result.get("kill_cost_atk") is None
        assert result.get("kill_cost_def") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_defense.py::TestKillCostParsing -v`
Expected: FAIL — `kill_cost_atk` key missing from result.

- [ ] **Step 3: Add kill-cost parsing to parse_battle_report()**

In `bot/cogs/defense.py`, in the `parse_battle_report()` function, after the existing bounty and stats parsing sections, add a new section that:

1. Scans for a line starting with "Koszt zabitych" (case-insensitive)
2. Reads subsequent lines with resource/count pairs (tab-separated)
3. Left columns = attacker cost, right columns = defender cost
4. Returns `kill_cost_atk` and `kill_cost_def` as `{resource: int}` dicts

The parsing follows the same tab-separated pattern as existing bounty parsing. Resource names: Drewno, Glina, Żelazo, Zboże.

```python
# After stats parsing, add kill-cost parsing
kill_cost_atk = {}
kill_cost_def = {}
in_kill_cost = False

for line in lines:
    stripped = line.strip()
    if re.match(r'(?i)^koszt\s+zabitych', stripped):
        in_kill_cost = True
        continue
    if in_kill_cost and stripped:
        # Format: "Resource\tAmount\tResource\tAmount" or just "Resource\tAmount"
        parts = stripped.split('\t')
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 2:
            try:
                res_name = parts[0]
                amount = int(re.sub(r'[\s.]', '', parts[1]))
                kill_cost_atk[res_name] = amount
            except (ValueError, IndexError):
                pass
        if len(parts) >= 4:
            try:
                res_name = parts[2]
                amount = int(re.sub(r'[\s.]', '', parts[3]))
                kill_cost_def[res_name] = amount
            except (ValueError, IndexError):
                pass
    elif in_kill_cost and not stripped:
        break  # Empty line ends kill cost section

result["kill_cost_atk"] = kill_cost_atk if kill_cost_atk else None
result["kill_cost_def"] = kill_cost_def if kill_cost_def else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_defense.py::TestKillCostParsing -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Add kill-cost display to _build_report_embed()**

In `bot/cogs/defense.py`, in `_build_report_embed()` (~line 942), after the existing bounty display section, add kill-cost rendering:

```python
    # Kill cost section
    kill_cost_atk = parsed.get("kill_cost_atk")
    kill_cost_def = parsed.get("kill_cost_def")
    if kill_cost_atk or kill_cost_def:
        kc_text = ""
        if kill_cost_atk:
            kc_text += "⚔️ **Napastnik:**\n"
            for res, amount in kill_cost_atk.items():
                kc_text += f"  {res}: {amount:,}\n"
        if kill_cost_def:
            kc_text += "🛡️ **Obrońca:**\n"
            for res, amount in kill_cost_def.items():
                kc_text += f"  {res}: {amount:,}\n"
        embed.add_field(name="💀 Koszt zabitych", value=kc_text[:1024], inline=False)
```

- [ ] **Step 6: Update the report save callback to persist kill-cost**

In `bot/cogs/defense.py`, in the `ReportModal.callback()` method (~line 637), when creating `BattleReport`, add:

```python
                kill_cost_atk=json.dumps(parsed.get("kill_cost_atk"), ensure_ascii=False) if parsed.get("kill_cost_atk") else None,
                kill_cost_def=json.dumps(parsed.get("kill_cost_def"), ensure_ascii=False) if parsed.get("kill_cost_def") else None,
```

- [ ] **Step 7: Run full parser test suite**

Run: `python -m pytest tests/test_defense.py tests/test_smart_parser.py -v`
Expected: All pass (no regressions to existing parsing).

- [ ] **Step 8: Commit**

```bash
git add bot/cogs/defense.py app/models.py tests/test_defense.py
git commit -m "feat: parse, display, and persist kill-cost from battle reports

Extracts 'Koszt zabitych' section (attacker + defender resource costs).
Displayed in report embed. Stored as JSON in BattleReport.kill_cost_atk/def.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 2: `/tbezpieczne` — Safe Troops Calculator

### Task 5: Implement `calc_safe_distance()` in utils.py

**Context:** The core problem: given available time (hours) and a unit's speed, calculate the MINIMUM distance a troop must travel so that its round trip takes at least `hours_away` hours. This is the INVERSE of `_calc_travel_seconds()`.

The existing two-phase formula:
- First 20 fields: `time = dist / (base_speed * artifact_mult) * 3600`
- After 20 fields: extra time adds `(dist - 20) / (base_speed * artifact_mult * (1 + boots + 0.2*ts)) * 3600`

For round trip: `total_time = 2 * one_way_time`.

We solve for distance using binary search on `_calc_travel_seconds()` — this correctly handles the two-phase formula including Tournament Square and boots.

**Files:**
- Modify: `bot/utils.py` (add `calc_safe_distance()`)
- Create: `tests/test_safe_distance.py`

- [ ] **Step 1: Write failing tests for safe distance calculation**

```python
# tests/test_safe_distance.py
"""Tests for safe-troop distance calculator (inverse of travel time)."""

import pytest
from bot.utils import _calc_travel_seconds, calc_safe_distance


class TestCalcSafeDistance:
    """Test calc_safe_distance — inverse of _calc_travel_seconds for round trips."""

    def test_basic_short_distance(self):
        """Phalanx (14 f/h), 2 hours away → round trip = 4h travel budget.
        One way = 2h → 14 * 2 = 28 fields. Needs to go >= 28 fields to be safe.
        But under 20 fields no TS bonus, so first 20 fields take 20/14 h = 1.43h.
        Only 0.57h left for remaining distance at same speed = 14*0.57 = 8 fields.
        Total = 28 fields one way. Round trip at 28 fields = 2*28/14*3600 = 14400s = 4h.
        With 2h budget: min_dist should be ~14 fields (half of one-way for round trip).
        """
        # Phalanx 14 f/h (already x2 in UNIT_SPEEDS), 2 hours, no TS
        dist = calc_safe_distance(
            speed=14, hours_away=2.0, ts_level=0, boots_bonus=0.0, artifact_mult=1.0
        )
        # Round trip of `dist` fields must take >= 2 hours
        round_trip_seconds = 2 * _calc_travel_seconds(dist, 14)
        assert round_trip_seconds >= 2.0 * 3600 - 1  # 1 second tolerance
        # Distance should be approximately speed * hours / 2 for short distances
        assert 13.5 <= dist <= 14.5

    def test_zero_hours(self):
        """0 hours → distance 0 (can't go anywhere safely)."""
        dist = calc_safe_distance(speed=14, hours_away=0.0)
        assert dist == 0.0

    def test_negative_hours(self):
        """Negative hours → distance 0."""
        dist = calc_safe_distance(speed=14, hours_away=-1.0)
        assert dist == 0.0

    def test_with_tournament_square(self):
        """TS makes troops faster after 20 fields → can go FARTHER in same time."""
        dist_no_ts = calc_safe_distance(speed=14, hours_away=4.0, ts_level=0)
        dist_with_ts = calc_safe_distance(speed=14, hours_away=4.0, ts_level=10)
        assert dist_with_ts > dist_no_ts

    def test_with_boots(self):
        """Boots bonus makes troops faster → can go farther."""
        dist_no_boots = calc_safe_distance(speed=14, hours_away=4.0)
        dist_with_boots = calc_safe_distance(
            speed=14, hours_away=4.0, boots_bonus=0.75
        )
        assert dist_with_boots > dist_no_boots

    def test_round_trip_consistency(self):
        """Verify round trip at calculated distance takes >= hours_away."""
        for speed in [6, 10, 14, 19, 32]:
            for hours in [1.0, 2.0, 4.0, 8.0]:
                for ts in [0, 5, 10, 20]:
                    dist = calc_safe_distance(
                        speed=speed, hours_away=hours, ts_level=ts
                    )
                    if dist <= 0:
                        continue
                    rt = 2 * _calc_travel_seconds(dist, speed, ts_level=ts)
                    assert rt >= hours * 3600 - 2, (
                        f"speed={speed}, hours={hours}, ts={ts}: "
                        f"dist={dist:.2f}, round_trip={rt:.1f}s < {hours*3600}s"
                    )

    def test_long_distance_with_ts(self):
        """Long distance where TS matters (>20 fields one way)."""
        # Catapult 6 f/h, 10 hours, TS=20
        dist = calc_safe_distance(
            speed=6, hours_away=10.0, ts_level=20
        )
        # With TS20: speed after 20 fields = 6 * (1 + 0.2*20) = 6*5 = 30 f/h
        # Should be able to go much farther than without TS
        dist_no_ts = calc_safe_distance(speed=6, hours_away=10.0, ts_level=0)
        assert dist > dist_no_ts * 1.5  # At least 50% farther with TS20

    def test_artifact_multiplier(self):
        """Speed artifact makes troops faster everywhere."""
        dist_no_art = calc_safe_distance(speed=14, hours_away=4.0)
        dist_with_art = calc_safe_distance(
            speed=14, hours_away=4.0, artifact_mult=2.0
        )
        assert dist_with_art > dist_no_art
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_safe_distance.py -v`
Expected: ImportError — `calc_safe_distance` not defined.

- [ ] **Step 3: Implement calc_safe_distance() using binary search**

In `bot/utils.py`, after the `_calc_travel_seconds()` function (~line 313), add:

```python
def calc_safe_distance(
    speed: float,
    hours_away: float,
    ts_level: int = 0,
    boots_bonus: float = 0.0,
    artifact_mult: float = 1.0,
) -> float:
    """Calculate minimum one-way distance for a safe round trip.

    Given available time (hours_away), finds the distance where
    the round trip (2 × one-way) takes exactly that long.
    Uses binary search on _calc_travel_seconds() to correctly handle
    the two-phase travel formula (TS/boots only apply after 20 fields).

    Args:
        speed: Unit base speed in fields/hour (from UNIT_SPEEDS, already x2 for x3 server).
        hours_away: Total time available in hours.
        ts_level: Tournament Square level (0-20).
        boots_bonus: Hero boots bonus (0.0, 0.25, 0.5, 0.75).
        artifact_mult: Speed artifact multiplier (1.0, 1.5, 2.0).

    Returns:
        Minimum one-way distance in fields (float). Troops must go at least
        this far to be safely away for the full duration.
    """
    if hours_away <= 0 or speed <= 0:
        return 0.0

    budget_seconds = hours_away * 3600

    # Upper bound: assume max possible speed applies everywhere
    max_speed = speed * artifact_mult * (1 + boots_bonus + 0.2 * ts_level)
    upper = max_speed * hours_away / 2 * 1.1  # 10% margin
    lower = 0.0

    # Binary search: find distance where 2 * travel_time == budget
    for _ in range(100):  # converges well within 100 iterations
        mid = (lower + upper) / 2
        round_trip = 2 * _calc_travel_seconds(mid, speed, artifact_mult, boots_bonus, ts_level)

        if abs(round_trip - budget_seconds) < 1.0:  # 1 second precision
            return round(mid, 2)

        if round_trip < budget_seconds:
            lower = mid
        else:
            upper = mid

    return round((lower + upper) / 2, 2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_safe_distance.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite for regressions**

Run: `python -m pytest tests/ -v --tb=short`
Expected: 357+ tests pass.

- [ ] **Step 6: Commit**

```bash
git add bot/utils.py tests/test_safe_distance.py
git commit -m "feat: add calc_safe_distance() — inverse travel formula for safe troops

Uses binary search on _calc_travel_seconds() for round-trip distance.
Correctly handles two-phase TS/boots formula after 20 fields.
Supports all modifiers: TS, boots, artifacts.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: Implement `/tbezpieczne` command

**Context:** The command shows minimum distance for each unit type to be safely away during an attack. Optionally suggests nearby unoccupied/inactive villages as targets.

**Files:**
- Modify: `bot/cogs/economy.py` (add command)
- Modify: `bot/cogs/general.py` (add to /thelp)

- [ ] **Step 1: Add `/tbezpieczne` slash command to economy.py**

In `bot/cogs/economy.py`, inside the `Economy` class, add the command. Import needed utilities at the top of the file:

```python
from bot.utils import (
    calc_safe_distance, _calc_travel_seconds,
    UNIT_SPEEDS, UNIT_CROP, TRIBE_NAMES, TRIBE_EMOJI,
    TYPE_EMOJI, torus_distance, parse_coords, coords_display,
    COLOR_SUCCESS, COLOR_INFO, FOOTER,
)
```

Command implementation:

```python
    @discord.slash_command(
        name="tbezpieczne",
        description="Kalkulator bezpiecznego wysyłania wojsk — minimalna odległość",
    )
    @discord.option("czas", str, description="Ile godzin masz do ataku np. 2.5 lub 2:30")
    @discord.option(
        "plemie", str, description="Twoje plemię",
        choices=["Rzymianie", "Germanie", "Galowie"],
    )
    @discord.option(
        "ts", int, description="Poziom Placu Turniejowego (0-20)",
        required=False, default=0, min_value=0, max_value=20,
    )
    @discord.option(
        "buty", float, description="Bonus butów bohatera (0, 0.25, 0.5, 0.75)",
        required=False, default=0.0,
    )
    @discord.option(
        "kordy", str, description="Twoja wioska (do sugestii celów) np. 76|43",
        required=False, default=None,
    )
    async def tbezpieczne(
        self, ctx: discord.ApplicationContext,
        czas: str, plemie: str, ts: int, buty: float, kordy: str | None,
    ):
        await ctx.defer()

        # Parse time input: "2.5" or "2:30" → float hours
        hours = _parse_hours(czas)
        if hours is None or hours <= 0:
            await ctx.followup.send(
                "❌ Nieprawidłowy czas. Użyj formatu `2.5` (godziny) lub `2:30` (h:mm).",
                ephemeral=True,
            )
            return

        tribe_map = {"Rzymianie": 1, "Germanie": 2, "Galowie": 3}
        tid = tribe_map[plemie]

        # Calculate safe distance for each unit type
        units = UNIT_SPEEDS.get(tid, [])
        results = []
        for unit in units:
            dist = calc_safe_distance(
                speed=unit["speed"],
                hours_away=hours,
                ts_level=ts,
                boots_bonus=buty,
            )
            results.append({
                "name": unit["name"],
                "speed": unit["speed"],
                "type": unit["type"],
                "safe_dist": dist,
            })

        # Sort by distance (shortest first — most restrictive)
        results.sort(key=lambda r: r["safe_dist"])

        # Build embed
        embed = discord.Embed(
            title=f"🛡️ Bezpieczne wysyłanie — {plemie}",
            description=(
                f"⏰ Czas do ataku: **{hours:.1f}h**\n"
                f"🏟️ Plac Turniejowy: **{ts}**"
                + (f" | 👢 Buty: **{int(buty*100)}%**" if buty > 0 else "")
            ),
            color=COLOR_SUCCESS,
        )

        lines = []
        for r in results:
            emoji = TYPE_EMOJI.get(r["type"], "")
            dist_str = f"{r['safe_dist']:.1f}" if r["safe_dist"] > 0 else "0"
            lines.append(
                f"{emoji} **{r['name']}** ({r['speed']} pól/h): "
                f"min. **{dist_str}** pól"
            )

        embed.add_field(
            name="📏 Minimalne odległości (w jedną stronę)",
            value="\n".join(lines)[:1024],
            inline=False,
        )

        # Target suggestions if coords provided
        if kordy:
            cx, cy = parse_coords(kordy)
            if cx is not None:
                # Get slowest unit's safe distance as search radius
                max_dist = max(r["safe_dist"] for r in results)
                min_dist = min(r["safe_dist"] for r in results)

                targets = await self._find_safe_targets(cx, cy, min_dist, max_dist)
                if targets:
                    server_url = self._server_url()
                    target_lines = []
                    for t in targets[:10]:
                        tc = coords_display(server_url, t["x"], t["y"])
                        status = "✅ wolne" if not t["occupied"] else f"👤 {t['player']} ({t['pop']} pop)"
                        target_lines.append(f"📍 {tc} — {status} • 📏 {t['dist']:.1f}")

                    embed.add_field(
                        name=f"🎯 Sugerowane cele ({min_dist:.0f}-{max_dist:.0f} pól)",
                        value="\n".join(target_lines)[:1024],
                        inline=False,
                    )

        embed.set_footer(text=f"{FOOTER} | Pamiętaj o czasie powrotu!")
        await ctx.followup.send(embed=embed)
```

- [ ] **Step 2: Add `_parse_hours()` helper**

Add as a module-level function in economy.py (before the Economy class):

```python
def _parse_hours(text: str) -> float | None:
    """Parse time input: '2.5' (hours) or '2:30' (h:mm) → float hours."""
    text = text.strip()
    # Try h:mm format
    m = re.match(r'^(\d+):(\d{1,2})$', text)
    if m:
        h = int(m.group(1))
        mins = int(m.group(2))
        if mins >= 60:
            return None
        return h + mins / 60.0
    # Try decimal hours
    try:
        val = float(text.replace(',', '.'))
        return val if val >= 0 else None
    except ValueError:
        return None
```

Add `import re` to the top of the file if not already present.

- [ ] **Step 3: Add `_find_safe_targets()` method to Economy class**

```python
    async def _find_safe_targets(self, cx, cy, min_dist, max_dist):
        """Find villages/oases in distance range as safe-send targets.

        Returns list of dicts sorted by distance.
        Uses Snapshot/Village via db_query() — never raw map.sql.
        """
        map_size = self._map_size()

        def _query():
            from app.models import Snapshot, Village
            snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
            if not snap:
                return []

            # Get villages in bounding box (wider than needed, filter by torus distance)
            search_radius = int(max_dist) + 5
            villages = (
                Village.query
                .filter(
                    Village.snapshot_id == snap.id,
                    _bbox_filter(Village.x, cx, search_radius, map_size),
                    _bbox_filter(Village.y, cy, search_radius, map_size),
                )
                .all()
            )

            results = []
            for v in villages:
                dist = torus_distance(cx, cy, v.x, v.y, map_size)
                if min_dist <= dist <= max_dist:
                    results.append({
                        "x": v.x, "y": v.y,
                        "occupied": v.uid > 0,
                        "player": v.player_name or "",
                        "pop": v.population or 0,
                        "dist": dist,
                    })

            # Sort: unoccupied first, then by distance
            results.sort(key=lambda t: (t["occupied"], t["dist"]))
            return results[:15]

        return await db_query(self.bot, _query)
```

- [ ] **Step 4: Add to /thelp listing in general.py**

In `bot/cogs/general.py`, find the help command list and add in the economy section:

```python
"⚔️ `/tbezpieczne` — Kalkulator bezpiecznego wysyłania (min. odległość)",
```

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add bot/cogs/economy.py bot/cogs/general.py
git commit -m "feat: add /tbezpieczne — safe troop distance calculator

Shows minimum distance for each unit type to safely send away.
Uses binary search on inverse travel formula (two-phase TS-aware).
Optional target suggestions from latest snapshot data.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 3: `/tileobrony` — Defense Calculator

### Task 7: Implement `calc_needed_defense()` in utils.py

**Context:** Given an attacking army composition (with inf/cav split), wall level, and a desired defender unit type, calculate how many defenders are needed to win. Uses `simulate_combat()` internals: attack power is split inf/cav, effective defense depends on the majority attack type. This is an ESTIMATE — labeled clearly.

**Files:**
- Modify: `bot/utils.py` (add function)
- Create: `tests/test_defense_calc.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_defense_calc.py
"""Tests for defense calculator — how many defenders needed to survive."""

import pytest
from bot.utils import calc_needed_defense, WALL_BONUS, COMBAT_BY_NAME


class TestCalcNeededDefense:
    """Test defense estimation based on simulate_combat() semantics."""

    def test_pure_infantry_attack(self):
        """All-infantry attack should use def_inf stat."""
        result = calc_needed_defense(
            attackers={"Imperians": 1000},
            defender_unit="Pretorianin",
            wall_level=0,
        )
        # Imperians: 70 att * 1000 = 70,000 att (all inf)
        # Pretorianin: 65 def_inf each
        # Need ~1077 Pretorianin for 70,000 def_inf (70000/65)
        assert result is not None
        assert "count" in result
        assert result["count"] > 0
        # Rough check: should be around 1077
        assert 900 < result["count"] < 1200

    def test_pure_cavalry_attack(self):
        """All-cavalry attack should use def_cav stat."""
        result = calc_needed_defense(
            attackers={"Equites Caesaris": 500},
            defender_unit="Włócznik",
            wall_level=0,
        )
        # EC: 180 att * 500 = 90,000 att (all cav)
        # Włócznik: 60 def_cav each
        # Need ~1500 (90000/60)
        assert result is not None
        assert 1300 < result["count"] < 1700

    def test_wall_reduces_needed_defense(self):
        """Higher wall → fewer defenders needed."""
        no_wall = calc_needed_defense(
            attackers={"Imperians": 1000},
            defender_unit="Pretorianin",
            wall_level=0,
        )
        with_wall = calc_needed_defense(
            attackers={"Imperians": 1000},
            defender_unit="Pretorianin",
            wall_level=20,
        )
        assert with_wall["count"] < no_wall["count"]

    def test_mixed_attack(self):
        """Mixed inf+cav attack: majority type determines which def stat applies."""
        result = calc_needed_defense(
            attackers={"Imperians": 500, "Equites Imperatoris": 500},
            defender_unit="Pretorianin",
            wall_level=0,
        )
        # Imperians: 70*500=35000 (inf), EI: 120*500=60000 (cav)
        # Majority = cav → uses def_cav of Pretorianin (35)
        assert result is not None
        assert result["att_type"] == "cav"
        assert result["count"] > 0

    def test_unknown_unit_returns_none(self):
        """Unknown defender unit returns None."""
        result = calc_needed_defense(
            attackers={"Imperians": 100},
            defender_unit="NieistniejącaJednostka",
            wall_level=0,
        )
        assert result is None

    def test_empty_attackers(self):
        """Empty attacker dict returns 0 needed."""
        result = calc_needed_defense(
            attackers={},
            defender_unit="Pretorianin",
            wall_level=0,
        )
        assert result is not None
        assert result["count"] == 0

    def test_result_includes_crop_cost(self):
        """Result includes crop consumption estimate."""
        result = calc_needed_defense(
            attackers={"Imperians": 1000},
            defender_unit="Pretorianin",
            wall_level=0,
        )
        assert "crop_per_hour" in result
        assert result["crop_per_hour"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_defense_calc.py -v`
Expected: ImportError — `calc_needed_defense` not defined.

- [ ] **Step 3: Implement calc_needed_defense()**

In `bot/utils.py`, after `calc_safe_distance()`, add:

```python
def calc_needed_defense(
    attackers: dict[str, int],
    defender_unit: str,
    wall_level: int = 0,
) -> dict | None:
    """Estimate how many of a specific defender unit are needed to win.

    Uses the same combat model as simulate_combat():
    - Attack power split into inf and cav
    - Majority attack type determines which defense stat applies
    - Wall bonus is a percentage multiplier

    This is an ESTIMATE. Real combat has morale, hero, and other factors.

    Args:
        attackers: dict {canonical_unit_name: count}
        defender_unit: canonical name of the unit to defend with
        wall_level: wall level (0-20)

    Returns:
        dict with: count, att_type, total_att, effective_def_per_unit,
                   wall_mult, crop_per_hour
        or None if defender_unit is unknown.
    """
    stats = COMBAT_BY_NAME.get(defender_unit)
    if stats is None:
        return None

    # Calculate total attack power (split inf/cav)
    inf_att = 0
    cav_att = 0
    for name, count in attackers.items():
        unit_stats = COMBAT_BY_NAME.get(name)
        if not unit_stats or count <= 0:
            continue
        power = unit_stats["att"] * count
        if unit_stats["type"] in ("inf", "siege", "special"):
            inf_att += power
        else:
            cav_att += power

    total_att = inf_att + cav_att
    if total_att == 0:
        return {
            "count": 0, "att_type": "inf", "total_att": 0,
            "effective_def_per_unit": 0, "wall_mult": 1.0,
            "crop_per_hour": 0,
        }

    # Determine attack type (majority)
    att_type = "cav" if cav_att > inf_att else "inf"

    # Select the relevant defense stat
    def_per_unit = stats["def_cav"] if att_type == "cav" else stats["def_inf"]

    # Wall multiplier
    wall_level = max(0, min(20, wall_level))
    wall_pct = WALL_BONUS[wall_level]
    wall_mult = 1 + wall_pct / 100

    if def_per_unit <= 0:
        return {
            "count": 0, "att_type": att_type, "total_att": total_att,
            "effective_def_per_unit": 0, "wall_mult": wall_mult,
            "crop_per_hour": 0,
        }

    # needed_count * def_per_unit * wall_mult >= total_att
    import math
    needed = math.ceil(total_att / (def_per_unit * wall_mult))

    # Crop cost
    crop_per_unit = _get_crop_for_unit(defender_unit)
    crop_total = needed * crop_per_unit

    return {
        "count": needed,
        "att_type": att_type,
        "total_att": total_att,
        "effective_def_per_unit": def_per_unit,
        "wall_mult": wall_mult,
        "crop_per_hour": crop_total,
    }


def _get_crop_for_unit(name: str) -> int:
    """Look up crop consumption for a unit by canonical name."""
    for tribe_units in UNIT_CROP.values():
        for u in tribe_units:
            if u["name"] == name:
                return u["crop"]
    return 1  # fallback
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_defense_calc.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/utils.py tests/test_defense_calc.py
git commit -m "feat: add calc_needed_defense() — defense estimation calculator

Estimates defenders needed based on simulate_combat() semantics.
Handles inf/cav attack split, wall bonus, crop consumption.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 8: Implement `/tileobrony` command

**Files:**
- Modify: `bot/cogs/economy.py` (add command)
- Modify: `bot/cogs/general.py` (add to /thelp)

- [ ] **Step 1: Add `/tileobrony` command**

```python
    @discord.slash_command(
        name="tileobrony",
        description="Kalkulator obrony — ile wojsk potrzeba do obrony",
    )
    @discord.option("atakujacy", str, description="Skład ataku np. 'Imperians:1000, EC:500'")
    @discord.option(
        "jednostka", str, description="Jednostka obronna (np. Pretorianin, Falangita, Włócznik)",
    )
    @discord.option(
        "mur", int, description="Poziom muru (0-20)",
        required=False, default=0, min_value=0, max_value=20,
    )
    async def tileobrony(
        self, ctx: discord.ApplicationContext,
        atakujacy: str, jednostka: str, mur: int,
    ):
        await ctx.defer()

        # Parse attacker army
        army, errors = parse_army_input(atakujacy)
        if not army:
            error_text = "\n".join(errors) if errors else "Nie rozpoznano żadnych jednostek."
            await ctx.followup.send(
                f"❌ Błąd parsowania armii atakującej:\n{error_text}\n"
                "💡 Format: `nazwa:ilość` np. `Imperians:1000, EC:500`",
                ephemeral=True,
            )
            return

        # Normalize defender unit name
        defender_canonical = normalize_unit_name(jednostka)
        if not defender_canonical:
            defender_canonical = _COMBAT_ABBREV.get(jednostka.lower())
        if not defender_canonical or defender_canonical not in COMBAT_BY_NAME:
            await ctx.followup.send(
                f"❌ Nieznana jednostka obronna: `{jednostka}`\n"
                "💡 Przykłady: Pretorianin, Falangita, Włócznik, Paladyn",
                ephemeral=True,
            )
            return

        result = calc_needed_defense(army, defender_canonical, mur)
        if result is None:
            await ctx.followup.send(
                "❌ Nie udało się obliczyć obrony.",
                ephemeral=True,
            )
            return

        # Build embed
        embed = discord.Embed(
            title="🛡️ Kalkulator obrony",
            description="⚠️ _Przybliżenie — nie uwzględnia morale, bohatera ani artefaktów_",
            color=COLOR_DEFENSE,
        )

        # Attacker summary
        atk_lines = []
        for name, count in army.items():
            stats = COMBAT_BY_NAME.get(name, {})
            emoji = TYPE_EMOJI.get(stats.get("type", ""), "")
            atk_lines.append(f"{emoji} {name}: **{count:,}**")
        embed.add_field(
            name=f"⚔️ Atakujący (siła: {result['total_att']:,})",
            value="\n".join(atk_lines)[:1024],
            inline=False,
        )

        # Attack type
        type_label = "Piechota" if result["att_type"] == "inf" else "Kawaleria"
        embed.add_field(
            name="🎯 Typ ataku",
            value=f"Większość siły: **{type_label}** → obrona liczy def vs {type_label.lower()}",
            inline=False,
        )

        # Defense result
        def_stat = result["effective_def_per_unit"]
        wall_text = f"Mur lvl {mur}: **×{result['wall_mult']:.2f}**" if mur > 0 else "Bez muru"
        embed.add_field(
            name=f"🛡️ Potrzeba: **{result['count']:,}× {defender_canonical}**",
            value=(
                f"Obrona/szt: **{def_stat}** (vs {type_label.lower()})\n"
                f"🧱 {wall_text}\n"
                f"🌾 Zużycie zboża: **{result['crop_per_hour']:,}/h**"
            ),
            inline=False,
        )

        if errors:
            embed.add_field(
                name="⚠️ Ostrzeżenia",
                value="\n".join(errors)[:512],
                inline=False,
            )

        embed.set_footer(text=FOOTER)
        await ctx.followup.send(embed=embed)
```

Note: Import `parse_army_input`, `normalize_unit_name`, `calc_needed_defense`, `_COMBAT_ABBREV`, `COLOR_DEFENSE` at the top.

- [ ] **Step 2: Add to /thelp in general.py**

```python
"🛡️ `/tileobrony` — Kalkulator obrony (ile wojsk potrzeba)",
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add bot/cogs/economy.py bot/cogs/general.py
git commit -m "feat: add /tileobrony — defense calculator command

Shows needed defenders based on attacker composition.
Handles inf/cav split, wall bonus, crop cost.
Clearly labeled as estimate.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 4: `/tprzechwyc` — Interception Calculator

### Task 9: Implement `calc_interception_times()` in utils.py

**Context:** Given an incoming attack (defender village coords, attacker village coords, attack ETA), calculate when to send OUR interception troops so they arrive at the defender village just before the attack hits. The key insight: we show RANGES of possible send times (one per our unit type), not a single exact answer.

For each of our unit types:
1. Calculate travel time from our village to the defender
2. send_time = attack_ETA - travel_time
3. If send_time is in the past → that unit can't make it
4. If send_time is in the future → show it

**Files:**
- Modify: `bot/utils.py` (add function)
- Create: `tests/test_interception.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_interception.py
"""Tests for interception time calculator."""

import pytest
from bot.utils import calc_interception_times, _calc_travel_seconds, torus_distance


class TestCalcInterceptionTimes:
    """Test interception send-time calculation."""

    def test_basic_interception(self):
        """Calculate send times for tribe units to reach a village."""
        # Our village: (0, 0), defender: (10, 0), distance = 10
        results = calc_interception_times(
            our_x=0, our_y=0,
            def_x=10, def_y=0,
            attack_eta_seconds=7200,  # Attack in 2 hours
            our_tribe=3,  # Gauls
            ts_level=0,
        )
        assert len(results) > 0
        # Each result should have name, send_in_seconds, travel_seconds, can_make_it
        for r in results:
            assert "name" in r
            assert "send_in_seconds" in r
            assert "travel_seconds" in r
            assert "can_make_it" in r

    def test_fast_unit_has_more_time(self):
        """Faster units have later send times (more time to spare)."""
        results = calc_interception_times(
            our_x=0, our_y=0, def_x=10, def_y=0,
            attack_eta_seconds=7200, our_tribe=3, ts_level=0,
        )
        # Find Tropiciel (17 f/h, fast) and Falangita (14 f/h, slower)
        tropiciel = next((r for r in results if "Tropiciel" in r["name"]), None)
        falangita = next((r for r in results if "Falangita" in r["name"]), None)
        if tropiciel and falangita and tropiciel["can_make_it"] and falangita["can_make_it"]:
            # Faster unit needs less travel time → can be sent later
            assert tropiciel["send_in_seconds"] > falangita["send_in_seconds"]

    def test_attack_too_soon_some_cant_make_it(self):
        """If attack is very soon, slow units can't make it."""
        results = calc_interception_times(
            our_x=0, our_y=0, def_x=50, def_y=0,
            attack_eta_seconds=600,  # Attack in 10 minutes — very soon
            our_tribe=1, ts_level=0,
        )
        # Catapults (6 f/h) definitely can't reach 50 fields in 10 min
        catapult = next((r for r in results if "Katapulta" in r["name"]), None)
        if catapult:
            assert catapult["can_make_it"] is False

    def test_ts_shortens_travel_for_long_distance(self):
        """TS reduces travel time for distances > 20 fields."""
        results_no_ts = calc_interception_times(
            our_x=0, our_y=0, def_x=50, def_y=0,
            attack_eta_seconds=14400, our_tribe=3, ts_level=0,
        )
        results_with_ts = calc_interception_times(
            our_x=0, our_y=0, def_x=50, def_y=0,
            attack_eta_seconds=14400, our_tribe=3, ts_level=10,
        )
        # With TS, send times should be later (less travel time needed)
        for r_ts in results_with_ts:
            r_no = next((r for r in results_no_ts if r["name"] == r_ts["name"]), None)
            if r_no and r_ts["can_make_it"] and r_no["can_make_it"]:
                assert r_ts["send_in_seconds"] >= r_no["send_in_seconds"]

    def test_torus_distance_used(self):
        """Distance wraps around torus map correctly."""
        # Near map edge: (199, 0) to (-199, 0) = 3 fields on torus, not 398
        results = calc_interception_times(
            our_x=199, our_y=0, def_x=-199, def_y=0,
            attack_eta_seconds=7200, our_tribe=1, ts_level=0,
            map_size=401,
        )
        # All units should be able to reach 3 fields in 2 hours
        for r in results:
            assert r["can_make_it"] is True

    def test_zero_distance(self):
        """Same village → travel time 0, all units can make it."""
        results = calc_interception_times(
            our_x=10, our_y=10, def_x=10, def_y=10,
            attack_eta_seconds=60, our_tribe=2, ts_level=0,
        )
        for r in results:
            assert r["can_make_it"] is True
            assert r["travel_seconds"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_interception.py -v`
Expected: ImportError — `calc_interception_times` not defined.

- [ ] **Step 3: Implement calc_interception_times()**

In `bot/utils.py`, add:

```python
def calc_interception_times(
    our_x: int, our_y: int,
    def_x: int, def_y: int,
    attack_eta_seconds: float,
    our_tribe: int,
    ts_level: int = 0,
    boots_bonus: float = 0.0,
    artifact_mult: float = 1.0,
    map_size: int = 401,
) -> list[dict]:
    """Calculate when to send each unit type to intercept an attack.

    For each unit in our tribe, computes travel time to the defender village
    and derives the latest send time so troops arrive before the attack.

    Args:
        our_x, our_y: Our village coordinates.
        def_x, def_y: Defender (target) village coordinates.
        attack_eta_seconds: Seconds until the attack hits.
        our_tribe: Our tribe id (1=Romans, 2=Teutons, 3=Gauls).
        ts_level: Tournament Square level (0-20).
        boots_bonus: Hero boots bonus (0.0-0.75).
        artifact_mult: Speed artifact multiplier (1.0, 1.5, 2.0).
        map_size: Map size for torus distance (default 401).

    Returns:
        List of dicts sorted by send time (most urgent first):
            name, type, speed, travel_seconds, send_in_seconds, can_make_it
    """
    distance = torus_distance(our_x, our_y, def_x, def_y, map_size)

    units = UNIT_SPEEDS.get(our_tribe, [])
    results = []

    for unit in units:
        travel = _calc_travel_seconds(
            distance, unit["speed"], artifact_mult, boots_bonus, ts_level,
        )
        send_in = attack_eta_seconds - travel
        can_make = send_in >= 0

        results.append({
            "name": unit["name"],
            "type": unit["type"],
            "speed": unit["speed"],
            "travel_seconds": round(travel, 1),
            "send_in_seconds": round(send_in, 1),
            "can_make_it": can_make,
        })

    # Sort: most urgent first (smallest send_in_seconds that's still positive)
    results.sort(key=lambda r: (not r["can_make_it"], r["send_in_seconds"]))
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_interception.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/utils.py tests/test_interception.py
git commit -m "feat: add calc_interception_times() — send-time calculator

Calculates when to send each unit type to intercept an attack.
Uses torus distance and two-phase travel formula.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 10: Implement `/tprzechwyc` command

**Files:**
- Modify: `bot/cogs/economy.py` (add command)
- Modify: `bot/cogs/general.py` (add to /thelp)

- [ ] **Step 1: Add `/tprzechwyc` command**

```python
    @discord.slash_command(
        name="tprzechwyc",
        description="Kalkulator przechwycenia — kiedy wysłać def",
    )
    @discord.option("moja_wioska", str, description="Twoja wioska (skąd wysyłasz) np. 81|33")
    @discord.option("cel", str, description="Atakowana wioska (dokąd wysyłasz) np. 76|43")
    @discord.option("eta", str, description="Czas do ataku (h:mm) lub godziny np. 2:30 lub 2.5")
    @discord.option(
        "plemie", str, description="Twoje plemię",
        choices=["Rzymianie", "Germanie", "Galowie"],
    )
    @discord.option(
        "ts", int, description="Poziom Placu Turniejowego (0-20)",
        required=False, default=0, min_value=0, max_value=20,
    )
    @discord.option(
        "buty", float, description="Bonus butów bohatera (0, 0.25, 0.5, 0.75)",
        required=False, default=0.0,
    )
    async def tprzechwyc(
        self, ctx: discord.ApplicationContext,
        moja_wioska: str, cel: str, eta: str,
        plemie: str, ts: int, buty: float,
    ):
        await ctx.defer()

        our_x, our_y = parse_coords(moja_wioska)
        if our_x is None:
            await ctx.followup.send(
                "❌ Nieprawidłowe koordynaty Twojej wioski.",
                ephemeral=True,
            )
            return

        def_x, def_y = parse_coords(cel)
        if def_x is None:
            await ctx.followup.send(
                "❌ Nieprawidłowe koordynaty atakowanej wioski.",
                ephemeral=True,
            )
            return

        hours = _parse_hours(eta)
        if hours is None or hours <= 0:
            await ctx.followup.send(
                "❌ Nieprawidłowy czas. Użyj `2:30` (h:mm) lub `2.5` (godziny).",
                ephemeral=True,
            )
            return

        tribe_map = {"Rzymianie": 1, "Germanie": 2, "Galowie": 3}
        tid = tribe_map[plemie]
        attack_eta_seconds = hours * 3600

        results = calc_interception_times(
            our_x, our_y, def_x, def_y,
            attack_eta_seconds, tid,
            ts_level=ts, boots_bonus=buty,
            map_size=self._map_size(),
        )

        dist = torus_distance(our_x, our_y, def_x, def_y, self._map_size())
        server_url = self._server_url()

        embed = discord.Embed(
            title="🎯 Kalkulator przechwycenia",
            description=(
                f"📍 Twoja wioska: {coords_display(server_url, our_x, our_y)}\n"
                f"🛡️ Cel (bronimy): {coords_display(server_url, def_x, def_y)}\n"
                f"📏 Dystans: **{dist:.2f}** pól\n"
                f"⏰ Atak za: **{hours:.1f}h** ({int(attack_eta_seconds)}s)\n"
                f"🏟️ TS: **{ts}**"
                + (f" | 👢 Buty: **{int(buty*100)}%**" if buty > 0 else "")
            ),
            color=COLOR_INFO,
        )

        can_lines = []
        cant_lines = []

        for r in results:
            emoji = TYPE_EMOJI.get(r["type"], "")
            travel_str = _format_duration(r["travel_seconds"])

            if r["can_make_it"]:
                send_str = _format_duration(r["send_in_seconds"])
                can_lines.append(
                    f"{emoji} **{r['name']}** ({r['speed']} pól/h)\n"
                    f"  🕐 Podróż: {travel_str} | ✈️ Wyślij za: **{send_str}**"
                )
            else:
                cant_lines.append(
                    f"{emoji} **{r['name']}** — ❌ za wolny (podróż: {travel_str})"
                )

        if can_lines:
            embed.add_field(
                name="✅ Zdążą (kiedy wysłać)",
                value="\n".join(can_lines)[:1024],
                inline=False,
            )

        if cant_lines:
            embed.add_field(
                name="❌ Nie zdążą",
                value="\n".join(cant_lines)[:1024],
                inline=False,
            )

        if not can_lines and not cant_lines:
            embed.add_field(
                name="⚠️",
                value="Brak danych o jednostkach tego plemienia.",
                inline=False,
            )

        embed.set_footer(text=f"{FOOTER} | Czasy podróży bez bohatera (chyba że podano buty)")
        await ctx.followup.send(embed=embed)
```

- [ ] **Step 2: Add `_format_duration()` helper**

In economy.py (module-level):

```python
def _format_duration(seconds: float) -> str:
    """Format seconds as 'Xh Ym' or 'Ym Zs'."""
    if seconds < 0:
        return "—"
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    elif m > 0:
        return f"{m}m {s:02d}s"
    else:
        return f"{s}s"
```

- [ ] **Step 3: Add to /thelp in general.py**

```python
"🎯 `/tprzechwyc` — Kalkulator przechwycenia (kiedy wysłać def)",
```

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass + new tests from this sprint.

- [ ] **Step 5: Commit**

```bash
git add bot/cogs/economy.py bot/cogs/general.py
git commit -m "feat: add /tprzechwyc — interception time calculator

Shows when to send each unit type to arrive before an attack.
Uses torus distance and two-phase travel formula.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 5: Final Integration & Testing

### Task 11: Update /thelp with all new commands and run final verification

**Files:**
- Modify: `bot/cogs/general.py` (verify /thelp has all 3 new commands)

- [ ] **Step 1: Verify /thelp has all new commands**

Check that the help command listing in `general.py` includes:
```
💰 Ekonomia i Kalkulatory
⚔️ /tbezpieczne — Kalkulator bezpiecznego wysyłania (min. odległość)
🛡️ /tileobrony — Kalkulator obrony (ile wojsk potrzeba)
🎯 /tprzechwyc — Kalkulator przechwycenia (kiedy wysłać def)
```

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (357 existing + ~25 new = ~382+).

- [ ] **Step 3: Test bot startup**

Run: `python -c "from app import create_app; app = create_app(); print('App OK')"` and
`python -c "from bot.bot import create_bot; print('Bot imports OK')"`
Expected: Both print OK without errors.

- [ ] **Step 4: Build Docker image**

Run: `docker compose -f docker-compose.dev.yml build`
Expected: Build succeeds.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: Sprint 2 complete — 3 calculators + bugfixes + parser enhancement

New commands: /tbezpieczne, /tileobrony, /tprzechwyc
Bugfixes: thread race condition, version bump, ROADMAP sync
Parser: kill-cost extraction and persistence

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Testing Checklist (for manual Discord testing)

After deployment, test these scenarios:

### /tbezpieczne
- [ ] Basic: `/tbezpieczne czas:2 plemie:Galowie` — shows distances for all Gaul units
- [ ] With TS: `/tbezpieczne czas:4 plemie:Germanie ts:10` — distances increase
- [ ] With coords: `/tbezpieczne czas:3 plemie:Rzymianie kordy:76|43` — shows target suggestions
- [ ] Edge: `/tbezpieczne czas:0.5 plemie:Galowie` — very short time, all distances small
- [ ] Invalid time: `/tbezpieczne czas:abc plemie:Galowie` — error message

### /tileobrony
- [ ] Pure infantry: `/tileobrony atakujacy:Imperians:1000 jednostka:Pretorianin mur:10`
- [ ] Pure cavalry: `/tileobrony atakujacy:EC:500 jednostka:Włócznik`
- [ ] Mixed: `/tileobrony atakujacy:Imperians:500,EC:300 jednostka:Falangita mur:15`
- [ ] Unknown unit: `/tileobrony atakujacy:Imperians:100 jednostka:Smok` — error message
- [ ] Abbreviations: `/tileobrony atakujacy:imp:500,ec:200 jednostka:pret`

### /tprzechwyc
- [ ] Basic: `/tprzechwyc moja_wioska:81|33 cel:76|43 eta:2:00 plemie:Galowie`
- [ ] Short ETA: `/tprzechwyc moja_wioska:81|33 cel:76|43 eta:0:10 plemie:Galowie` — some can't make it
- [ ] With TS: `/tprzechwyc moja_wioska:0|0 cel:50|50 eta:3:00 plemie:Rzymianie ts:15`
- [ ] Same village: `/tprzechwyc moja_wioska:76|43 cel:76|43 eta:1:00 plemie:Germanie` — all 0 travel

### Bugfixes
- [ ] Duplicate threads: two simultaneous `/tatak` for same village → only one thread created
- [ ] Version: `/tinfo` shows 1.0.0
- [ ] Kill cost: paste a report with "Koszt zabitych" section → parsed and displayed
