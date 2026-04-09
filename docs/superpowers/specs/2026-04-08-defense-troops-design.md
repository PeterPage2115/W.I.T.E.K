# Defense & Troop Tracking System — Design Spec

## Problem
Alliance members need to coordinate defense effectively. Current `/tatak` requires attacker name (not always known) but doesn't track attacker coords as required. No way to track troops in villages, parse battle reports, or calculate crop consumption.

## Changes

### 1. `/tatak` parameter rework
- `cel` (target coords) — required (unchanged)
- `zrodlo` (attacker coords) — **required** (was optional)
- `czas` (attack time) — required (unchanged)
- `mur` (wall level 0-20) — optional, integer
- `zboze` (current crop) — optional, integer
- `produkcja` (crop/hour) — optional, integer
- `atakujacy` (attacker name) — **optional** (was required), derived from map data if omitted
- `notatki` — optional (unchanged)

### 2. `/traport` — Battle Report Parser
**Input**: Discord Modal with textarea (4000 char limit).
User pastes raw text copied from Travian battle report.

**Parsing**: Tab-separated format from game:
```
TitleLine (e.g. "PlayerA grabs PlayerB")
Date (e.g. "08.04.26, 21:11:02")
"Napastnik" header
[Alliance] Player z osady Village
UnitName1\tUnitName2\t...\tBohater
Count1\tCount2\t...           (troops sent)
Count1\tCount2\t...           (troops killed)
[Count1\tCount2\t...]         (trapped — optional, if Trapper)
"zdobycz"\tLumber\tClay\tIron\tCarried/Capacity
"Obrońca" header
[Alliance] Player z osady Village
UnitName1\tUnitName2\t...\tBohater
Count1\tCount2\t...           (troops)
Count1\tCount2\t...           (killed)
"Statystyki"
"Napastnik"\t"Obrońca"
"Siła w walce"\tVal\tVal
"Utrzymanie przed"\tVal\tVal
"Utrzymanie zabitych"\tVal\tVal
"Koszt zabitych"\tVal\tVal
```

**Output**: Embed with:
- Attacker: alliance, player, village, troops (with losses highlighted)
- Defender: same
- Bounty: resources captured
- Stats: attack power, crop consumption
- Link to map coordinates

**Options**:
- `watek` (optional int): Link to existing attack report thread

### 3. `/twojska` — Village Troop Registration
**Input**: Discord Modal with textarea.
User pastes unit list from game:
```
UnitName\tCount\tUnitName
UnitName\tCount\tUnitName
```
Plus a coords field for the village.

**Output**: Embed showing:
- All units with counts
- Total crop consumption (calculated from official data)
- Breakdown: infantry, cavalry, siege, nature, hero

**Storage**: `village_troops` table — latest snapshot per village per player.

### 4. `/twsparcie` — Support Registration
**Input**: Slash command with:
- `skad` (from coords) — required
- `dokad` (to coords) — required
- Then Modal for troop list

**Output**: Embed showing:
- Troops being sent
- Travel time (based on slowest unit)
- Crop consumption of support
- Posted in defense thread if one exists for target village

**Storage**: `troop_support` table.

## Data Model Changes

### New columns on `attack_reports`:
- `wall_level` INTEGER nullable
- `crop_amount` INTEGER nullable
- `crop_production` INTEGER nullable

### New table: `village_troops`
```sql
CREATE TABLE village_troops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    village_x INTEGER NOT NULL,
    village_y INTEGER NOT NULL,
    village_name TEXT,
    player_discord_id TEXT NOT NULL,
    player_name TEXT,
    troops TEXT NOT NULL,           -- JSON: {"Falangi": 510, "Tropiciele": 20, ...}
    crop_consumption INTEGER,       -- calculated total crop/h
    created_at DATETIME,
    updated_at DATETIME
);
```

### New table: `troop_support`
```sql
CREATE TABLE troop_support (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_x INTEGER NOT NULL,
    from_y INTEGER NOT NULL,
    to_x INTEGER NOT NULL,
    to_y INTEGER NOT NULL,
    player_discord_id TEXT NOT NULL,
    player_name TEXT,
    troops TEXT NOT NULL,           -- JSON
    crop_consumption INTEGER,
    travel_time_seconds INTEGER,
    attack_report_id INTEGER,       -- FK to attack_reports if linked
    forum_thread_id BIGINT,
    status TEXT DEFAULT 'in_transit', -- in_transit / arrived / recalled
    created_at DATETIME,
    updated_at DATETIME
);
```

### New table: `battle_reports`
```sql
CREATE TABLE battle_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attack_report_id INTEGER,       -- FK to attack_reports if linked
    forum_thread_id BIGINT,
    attacker_name TEXT,
    attacker_alliance TEXT,
    attacker_village TEXT,
    attacker_troops TEXT,           -- JSON: {"Pałkarz": 80, "Topornik": 150}
    attacker_losses TEXT,           -- JSON
    attacker_trapped TEXT,          -- JSON (optional)
    defender_name TEXT,
    defender_alliance TEXT,
    defender_village TEXT,
    defender_troops TEXT,           -- JSON
    defender_losses TEXT,           -- JSON
    bounty TEXT,                    -- JSON: {"lumber": 97980, ...}
    battle_power_atk INTEGER,
    battle_power_def INTEGER,
    raw_text TEXT,
    reported_by_discord TEXT,
    created_at DATETIME
);
```

## Crop Consumption Data (official, confirmed)

### Romans (tribe_id=1)
| Unit (PL) | Crop/h |
|-----------|--------|
| Legionista | 1 |
| Pretorianin | 1 |
| Imperians | 1 |
| Equites Legati | 3 |
| Equites Imperatoris | 3 |
| Equites Caesaris | 4 |
| Taran | 3 |
| Katapulta ognista | 6 |
| Senator | 5 |

### Teutons (tribe_id=2)
| Unit (PL) | Crop/h |
|-----------|--------|
| Pałkarz | 1 |
| Włócznik | 1 |
| Topornik | 1 |
| Zwiadowca | 1 |
| Paladyn | 2 |
| Germański rycerz | 3 |
| Taran | 3 |
| Katapulta | 6 |
| Wódz | 5 |

### Gauls (tribe_id=3)
| Unit (PL) | Crop/h |
|-----------|--------|
| Falangita/Falangi | 1 |
| Miecznik/Miecznicy | 1 |
| Tropiciel/Tropiciele | 2 |
| Grom Teutatesa/Gromy | 2 |
| Jeździec druidzki/Jeźdźcy | 2 |
| Haeduan/Haeduanowie | 3 |
| Taran/Tarany | 3 |
| Trebusz/Trebusze | 6 |
| Wódz/Wodzowie | 5 |

### Nature (captured animals)
| Unit (PL) | Crop/h |
|-----------|--------|
| Szczur/Szczury | 1 |
| Pająk/Pająki | 1 |
| Wąż/Węże | 1 |
| Nietoperz/Nietoperze | 1 |
| Dzik/Dziki | 2 |
| Wilk/Wilki | 2 |
| Niedźwiedź/Niedźwiedzie | 3 |
| Krokodyl/Krokodyle | 3 |
| Tygrys/Tygrysy | 4 |
| Słoń/Słonie | 5 |

### Hero
| Unit | Crop/h |
|------|--------|
| Bohater | 6 |

## Unit Name Mapping

The game uses different naming forms in different contexts:
- **Battle reports**: Singular nominative (Pałkarz, Włócznik, Falangita)
- **Unit lists**: Plural nominative (Falangi, Tropiciele, Gromy Teutatesa)

Parser must handle BOTH forms via a fuzzy mapping dictionary.

## Implementation Notes

- All new commands go in a new cog: `bot/cogs/defense.py` (keeps attacks.py focused on attack reporting)
- Unit data (names, crop, mapping) goes in `bot/utils.py`
- Modals use py-cord's `discord.ui.Modal` and `discord.ui.InputText`
- Crop consumption is NOT affected by server speed
- All DB access via `db_query()` pattern (return dicts, not models)
