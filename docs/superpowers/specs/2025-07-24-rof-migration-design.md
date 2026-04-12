# W.I.T.E.K — Reign of Fire Migration Design

## Problem Statement

W.I.T.E.K currently targets ts31.x3.europe.travian.com (classic Legends server). We're migrating to **Reign of Fire Spring Round 2026 — International x3** (80-day seasonal server, launching April 14). RoF 2026 introduces ships, harbors, regions, item crafting, Vikings tribe, and a rebalanced Legionnaire — requiring significant parser, calculator, and UI updates.

The same codebase will serve both servers via config-driven Docker instances.

> **Source**: [Reign of Fire – Spring Round 2026 Details](https://www.travian.com/international/news/2026/03/17/reign-of-fire-spring-round-2026-details/)
>
> **Important**: RoF 2025 (original) had NO ships, NO Vikings, and Teutons were back. RoF Spring 2026 is a different variant WITH ships, WITH Vikings, WITHOUT Teutons. Verified on live RoF x10 server data.

## Target Server

| Property | Value |
|----------|-------|
| Name | Reign of Fire Spring Round 2026 — International x3 |
| URL | `rof.x3.international.travian.com` |
| Speed | x3 |
| Duration | 80 days |
| Tribes | Romans, Gauls, Egyptians, Huns, **Spartans (tid=8)**, **Vikings (tid=9)** |
| No Teutons | Correct — Teutons NOT available on International x3 (but available on Regional x2!) |
| Special | Ships, Harbors, Pathfinding, Regions, Cities, Item Crafting, Rebalanced Legionnaire |

> **Note**: RoF 2026 Regional x2 servers (Europe, America, etc.) have a DIFFERENT tribe set: Romans, Gauls, **Teutons**, Egyptians, Huns, Spartans — no Vikings, no rebalanced Legionnaire. Our config system handles this per-server.

## Critical Bug: Tribe ID Mismatch

**Verified on live RoF x10 data** (2025-07-24):

| Coordinates | tid in map.sql | Actual tribe | Our tribes.py |
|-------------|---------------|-------------|---------------|
| (97\|104) PeterPage | **9** | Vikings | ❌ Says tid 9 = Spartans |
| (110\|-29) spookie | **8** | Spartans | ❌ Says tid 8 = Vikings |

**Official Travian docs confirm**: tid 8 = Spartans, tid 9 = Vikings.
**Our code has them reversed.** Fix: swap tid 8↔9 in `bot/tribes.py` and `CLAUDE.md`.

---

## Architecture: Config-Driven Multi-Server

### Approach

Single codebase, multiple Docker Compose files. Each instance gets its own `.env` with `SERVER_PROFILE` selecting the server config block.

### Config Schema (`config.yaml`)

```yaml
servers:
  ts31:
    url: "https://ts31.x3.europe.travian.com"
    speed: 3
    tribes: [1, 2, 3, 6, 7]        # Romans, Teutons, Gauls, Egyptians, Huns
    our_alliances: [38]
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
    tribes: [1, 3, 6, 7, 8, 9]     # Romans, Gauls, Egyptians, Huns, Spartans, Vikings
    our_alliances: []                # TBD at server launch
    features:
      ships: true
      regions: true
      cities: true
      harbors: true
      victory_points: true
    legionnaire_rebalanced: true     # Cav def 50→70, train 26:40→22:40, speed 6→7
```

### Docker Setup

```
docker-compose.yml          # ts31 instance
docker-compose.rof.yml      # RoF x3 instance (separate DB, bot token, guild)
```

Each compose file references the same image but different `.env`:
- `DISCORD_TOKEN` — different bot per server (or same bot, 2 guilds)
- `SERVER_PROFILE` — selects config block
- `DATABASE_URL` — separate DB per instance

---

## map.sql Parser Updates

### Current Format (11 fields parsed, 5 ignored)

```
ID, X, Y, Tribe, VID, VillageName, UID, PlayerName, AID, AllianceTag, Population, NULL×5
```

### RoF Format (16 fields, all meaningful)

| # | Field | Type | Example | NULL when |
|---|-------|------|---------|-----------|
| 12 | Region | TEXT | 'Caledonia', 'Cimbri', 'Venedae' | Feature unsupported |
| 13 | Capital | BOOL | TRUE/FALSE | Feature unsupported |
| 14 | City | BOOL | TRUE/FALSE | Feature unsupported |
| 15 | Harbor | BOOL | TRUE/FALSE | Feature unsupported |
| 16 | Victory Points | INT | 0 | Feature unsupported |

### Parser Strategy

**Always parse all 16 fields** — treat map.sql as one fixed row shape with nullable trailing columns. No format detection needed:
- Fields 12-16 are always present in the SQL
- When a feature is unsupported on a server, the value is `NULL`
- Store NULLs as-is in the database (nullable columns)

This is simpler and more resilient than trying to detect "classic vs RoF" format.

### Model Changes

Add to `Village` model:
```python
region = db.Column(db.String(50), nullable=True)
is_capital = db.Column(db.Boolean, nullable=True)
is_city = db.Column(db.Boolean, nullable=True)
has_harbor = db.Column(db.Boolean, nullable=True)
victory_points = db.Column(db.Integer, nullable=True, default=0)
```

---

## Ship Mechanics

### Ship Types

| Ship | Speed (water) | Speed (Vikings) | Capacity | Farmlist? | Cost (L/C/I/Cr) | Build Time |
|------|--------------|-----------------|----------|-----------|------------------|------------|
| Trade Ship | 18 f/h | 18 f/h | 2500-3000* | N/A | 2835/1235/1985/750 | 1:15:00 |
| Warship | 18 f/h | 18 f/h | Unlimited troops | ❌ | 18500/8355/12275/7500 | 3:45:00 |
| Decoy Warship | 18 f/h | 18 f/h | ≤60 units | ❌ | 950/350/750/350 | 0:35:00 |
| Raid Ship | 18 f/h | **24 f/h** | ≤200 units | ✅ | 750/450/450/150 | 0:20:00 |

*Trade Ship capacity varies by tribe: Huns/Vikings/Teutons 3000, Gauls/Spartans 2750, Romans/Egyptians 2500.

### Deep Water Rules
- NO Tournament Square bonus
- NO hero boot bonus
- NO hero items (except map)
- NO artifact speed bonus
- Ships sink if all troops aboard die

### Harbor Requirements
- Main Building level 10 + Rally Point level 10
- Must be settled on abandoned shore tile
- Max capacity: 210 ships at harbor level 20

### Travel Time Calculation (with sea route)

```
total_time = land_time_to_harbor_A + sea_crossing_time + land_time_from_harbor_B
```

Where:
- `land_time_*` = standard travel formula (with TS, boots, artifacts)
- `sea_crossing_time` = sea_distance / ship_speed (no modifiers)

### Implementation: `/tstatki` command

```
/tstatki from:<x,y> to:<x,y> unit:<type> [ship:<type>]
```

Output: land ETA, sea ETA, total ETA, comparison with land-only route.

**Note**: We don't have sea tile data from map.sql — use checkbox "przez morze" (through sea) approach with user-estimated sea distance.

---

## Rebalanced Legionnaire

On servers with Vikings, the Roman Legionnaire gets stat changes:

| Stat | Classic | Rebalanced |
|------|---------|------------|
| Cavalry defense | 50 | **70** |
| Training time | 26:40 | **22:40** |
| Speed | 6 f/h | **7 f/h** |

Implementation: `legionnaire_rebalanced: true` in server config. `tribes.py` checks this flag and returns adjusted stats.

---

## Command Audit: Discord vs Dashboard Split

### Discord ONLY (realtime coordination)

| Command | Purpose |
|---------|---------|
| `/tatak` | Report attack (creates defense thread) |
| `/tdodaj` | Add attack to existing thread |
| `/tataki` | List recent attacks |
| `/trozwiaz` | Resolve attack + archive thread |
| `/twojska` | Register garrison troops |
| `/twsparcie` | Register support sent |
| `/tstan` | Show village defense status |
| `/tdef` | Who can send def? (sorted by ETA) |
| `/tlink`, `/tunlink`, `/twhoami` | Identity management |
| `/tinfo`, `/tstats`, `/thelp` | Bot info |
| `/tzboza` | Quick crop lookup |

### Discord + Dashboard (calculators available both ways)

| Command | Dashboard Enhancement |
|---------|--------------------|
| `/tcropper` | Map view with 9c/15c filter layer |
| `/tszukaj` | Advanced search form + results table |
| `/tileobrony` | Interactive calculator with sliders |
| `/tbezpieczne` | Time slider + distance result |
| `/tprzechwyc` | Visual timeline |
| `/tsymulacja` | Full battle simulator UI |
| `/tporownaj` | Side-by-side with charts |
| `/tnieaktywni` | Table + map markers |
| `/ttraining` | Multi-unit form with totals |
| `/tdigest` | Interactive weekly report |
| `/traporty` | Filterable report list |

### REMOVE (replaced by alerts system)

| Command | Reason |
|---------|--------|
| `/tczuwanie` | Replaced by `/tmonitor` |
| `/tmonitor` | Rework into simpler alert preferences |
| `/tmonitor_ustawienia` | Merge into `/tmonitor` |

### NEW Commands (RoF)

| Command | Purpose | Phase |
|---------|---------|-------|
| `/tstatki` | Sea travel calculator | Phase 1 |
| `/top` | Operation planning (attack coordination) | Phase 2 |

---

## Dashboard: Calculator Pages

### Phase 1 — Existing calculators on web

New route: `/tools` — grid of calculator cards linking to individual pages.

Each calculator page:
- Form inputs (styled Travian-medieval)
- Submit → JS fetch to API endpoint → display results below form
- No page reload
- Export button (copy to clipboard / CSV)

### Phase 2 — New calculators

| Calculator | Description | Data Source |
|-----------|-------------|-------------|
| **Building calc** | Time + cost for building at level N. Tribe bonuses, hero bonus. | Building data JSON (from traviantools or manual) |
| **Village planner** | Preset build orders (hammer, anvil, feeder, WWK). Shows resource timeline. | Static presets + building data |
| **Farmlist helper** | Rank nearby inactive players by distance × pop / activity. | map.sql snapshots |

---

## Deep Links in Discord Embeds

### In-Game URL Templates

```
# Open map tile
{server}/position_details.php?x={x}&y={y}

# Send troops (pre-filled coords)
{server}/build.php?id=39&tt=2&x={x}&y={y}

# Send troops with specific units (eventType: 2=reinforce, 3=attack, 4=raid)
{server}/build.php?id=39&tt=2&x={x}&y={y}&eventType=2&troop[t1]=1000

# Open marketplace for trading
{server}/build.php?gid=17&x={x}&y={y}&t=5
```

### Integration Points

| Embed | Link Added | Label |
|-------|-----------|-------|
| `/tdef` results | Send troops to defender | "🛡️ Wyślij def" |
| `/tatak` alert | Open attacker on map | "🗺️ Zobacz na mapie" |
| Attack thread | Open defender village | "📍 Otwórz wioskę" |
| `/tnieaktywni` results | Open inactive on map | "🗺️ Mapa" |

---

## Operation Planning (`/top`) — Phase 2

### Concept

Alliance leaders create attack operations with:
1. **Target** — enemy village coordinates
2. **Hit time** — exact server time when all attacks should land
3. **Participants** — members sign up with their attack villages

Bot calculates for each participant:
- "Send your troops at HH:MM:SS" (backward from hit time - travel time)
- Account for different unit speeds

### Commands

```
/top create target:<x,y> hit_time:<HH:MM:SS DD.MM> name:<op name>
/top join op:<name> from:<x,y> unit:<slowest unit type>
/top status op:<name>
/top cancel op:<name>
```

### Dashboard Integration

- `/operations` page — timeline view of planned operations
- Countdown timers for each participant's send time
- Status tracking (planned → active → completed)

---

## Smart Map Enhancements

### Default View
- Shows ONLY our alliance villages (not all 14k)
- Cluster markers enabled (Leaflet.markercluster already implemented)

### Filter Layers (toggleable)
- 🟢 Our alliances
- 🔴 Known enemies (from diplomacy)
- 🟡 Neutral (top players)
- ⚓ Harbors (RoF — from map.sql field 15)
- 🌾 Croppers (9c/15c from map.sql)
- 📍 Search results overlay

### Region Overlay (RoF)
- Color-coded regions from map.sql field 12
- Stats sidebar: "Caledonia: 450 villages, top alliance: XYZ"

---

## Database Migrations

### New Columns for Village Model

```sql
ALTER TABLE villages ADD COLUMN region VARCHAR(50);
ALTER TABLE villages ADD COLUMN is_capital BOOLEAN;
ALTER TABLE villages ADD COLUMN is_city BOOLEAN;
ALTER TABLE villages ADD COLUMN has_harbor BOOLEAN;
ALTER TABLE villages ADD COLUMN victory_points INTEGER DEFAULT 0;
```

### New Table: Operations (Phase 2)

```sql
CREATE TABLE operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target_x INTEGER NOT NULL,
    target_y INTEGER NOT NULL,
    hit_time TIMESTAMP NOT NULL,
    created_by_discord TEXT NOT NULL,
    status TEXT DEFAULT 'planned',  -- planned / active / completed / cancelled
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE operation_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER REFERENCES operations(id),
    discord_id TEXT NOT NULL,
    from_x INTEGER NOT NULL,
    from_y INTEGER NOT NULL,
    slowest_unit TEXT,
    send_time TIMESTAMP,           -- calculated backward from hit_time
    status TEXT DEFAULT 'pending',  -- pending / confirmed / sent / cancelled
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Implementation Phases

### Phase 1: Core RoF Support (Launch-Critical MVP)

1. **Fix tribe ID bug** — swap tid 8↔9 in tribes.py + CLAUDE.md
2. **Config refactor** — multi-server profiles in config.yaml
3. **Parser update** — always parse 16 fields, store NULLs for unsupported features
4. **Village model** — add region, capital, city, harbor, VP columns (via `_ensure_columns`)
5. **Rebalanced Legionnaire** — conditional stats based on server config flag
6. **Docker multi-instance** — separate compose file for RoF
7. **Deep links** — add in-game URLs to all coordinate-containing embeds
8. **Deploy validation** — verify parser + collector + DB + API end-to-end on RoF x10 data

### Phase 1b: Ship Support (first week after launch)

9. **Ship data** — add ship definitions in **separate registry** (not inside TribeDef.units)
10. **`/tstatki`** — sea travel calculator (MVP: sea-leg only with user-input sea distance + ship type)

### Phase 2: Enhanced Features

10. **Dashboard calculators** — web versions of all 11 Discord calculators
11. **Building calculator** — new, Dashboard-only
12. **Village planner** — new, Dashboard-only
13. **Farmlist helper** — new, Dashboard-only
14. **Op planning** — `/top` command + dashboard page
15. **Map region overlay** — filter by region, harbor layer
16. **Map filter improvements** — default our alliance only, toggleable layers

### Phase 3: Polish & Optimization

17. **Smart map** — default view, performance tuning
18. **Missing tests** — models, new commands, new routes
19. **Deploy** — push to GHCR, deploy RoF instance

---

## Competitor Feature Gap Analysis

### Features We Have (Unique)

| Feature | Competitors lack |
|---------|-----------------|
| Discord bot + web dashboard combo | GetterTools is web-only, TravcoTools is Discord-only |
| Chrome extension for report parsing | No competitor has this |
| Forum-based defense coordination | Unique to W.I.T.E.K |
| Smart map with alliance filtering | Others show all villages |

### Features to Add (from competitors)

| Feature | Source | Phase | Priority |
|---------|--------|-------|----------|
| Deep links in embeds | Travian official docs | Phase 1 | High |
| Op planning | GetterTools/TravcoTools | Phase 2 | Medium |
| Building calculator | traviantools GitHub | Phase 2 | Medium |
| Village planner | traviantools GitHub | Phase 2 | Medium |
| Farmlist helper | TravcoTools | Phase 2 | Medium |
| Hero change detection | TravcoTools | Backlog | Low |

### Features We Skip

| Feature | Reason |
|---------|--------|
| Artifact tracker | Requires game scraping — violates ToS |
| Auto-farming | Automation — violates ToS |
| Supply/push monitoring | Requires game API access we don't have |
| ROI calculator | Nice but not tactical priority |

---

## Testing Strategy

### New Tests Required

| Area | Tests |
|------|-------|
| `test_tribes_rof.py` | Verify tid 8=Spartans, tid 9=Vikings; ship definitions; rebalanced Legionnaire |
| `test_parser_rof.py` | Parse 16-field map.sql lines; NULL handling for unsupported features |
| `test_config_multiserver.py` | SERVER_PROFILE selection; feature flags; fallback behavior |
| `test_ships.py` | Ship speed calculations; deep water rules; no TS/boots on water |
| `test_deep_links.py` | URL generation for all link types |
| `test_statki_cog.py` | /tstatki command responses |
| `test_collector_rof.py` | End-to-end: parse RoF line → store_snapshot() → verify 16 fields in DB |
| `test_mixed_tribes.py` | Player with multi-tribe villages displays correctly |
| `test_migration.py` | _ensure_columns adds new columns without data loss |

### Existing Tests to Update

| Test File | Change |
|-----------|--------|
| `test_tribes.py` | Update tid assertions after swap |
| `test_parser.py` | Add 16-field test cases |
| `test_travel.py` | Add sea route calculations |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| RoF x3 URL different than expected | Low | Med | Verify at server launch, config-driven |
| map.sql format changes between servers | Low | High | Always parse 16 fields with nullable extras |
| Tribe ID swap breaks existing ts31 data | **None** | None | ts31 has no Vikings/Spartans — zero impact |
| Sea pathfinding inaccurate (no tile data) | High | Med | Checkbox approach, user estimates sea distance |
| 80-day server lifespan too short for all features | Med | Med | Phase 1 ready before launch, Phase 2 during game |
| Mixed tribes per player (Keep Tribe on Conquer) | High | Med | Show tribe per village, Player.tid = primary tribe or null |
| Two Docker instances with same bot token | High | High | **Separate Discord apps/tokens per server** — mandatory |

---

## Design Decisions (from spec review)

### 1. RoF Version Clarification

The rubber-duck reviewer flagged a potential ruleset mismatch. Clarification:
- **RoF 2025** (original): No ships, no Vikings, Teutons back → NOT our target
- **RoF Spring 2026** (our target): Ships ✅, Vikings ✅, No Teutons ✅, Rebalanced Legionnaire ✅
- Source: [Official announcement](https://www.travian.com/international/news/2026/03/17/reign-of-fire-spring-round-2026-details/)
- Verified: Live RoF x10 data confirms tribes, harbors, regions

### 2. Parser: Single Format, Not Detection

Instead of detecting "classic vs RoF" by checking field 12, we always parse all 16 fields. NULL values are stored as-is. This is simpler and handles any server variant without branching logic.

### 3. Mixed Tribes (Keep Tribe on Conquer)

RoF allows conquering villages of other tribes. This means one player can own villages of multiple tribes.

**MVP approach**: `Player.tid` stores the tribe of their **first/most common village**. Village-level pages always show the correct per-village tribe. Player-level displays show primary tribe with "(mixed)" indicator if they have villages of different tribes.

### 4. Ships in Separate Registry

Ships are NOT regular troops — they're transport vessels. Adding them to `TribeDef.units` would break `UNIT_SPEEDS` dict and confuse movement/detection calculators.

**Solution**: New `SHIPS` dict in `bot/tribes.py` (or separate `bot/ships.py`), separate from `TRIBES`. Travel calculators explicitly handle ship legs vs land legs.

### 5. `/tstatki` MVP Scope

Full harbor-to-harbor pathfinding requires tile data we don't have. MVP:

```
/tstatki sea_distance:<float> ship:<type> [troops:<unit type>]
```

Input: user provides estimated sea distance in fields + ship type.
Output: sea crossing time, comparison table of all ship types.

Phase 2: if harbor locations are known from map.sql (field 15), suggest nearest harbors.

### 6. Separate Discord Tokens Per Server

Running two Docker containers with the same bot token causes event duplication. **Each server instance MUST use a separate Discord application/token**. This also allows different guild configurations per server.

### 7. Database Migrations

Our codebase uses `_ensure_columns()` in `database.py`, not Alembic. New columns will be added via this mechanism:

```python
_ensure_columns('villages', [
    ('region', 'VARCHAR(50)'),
    ('is_capital', 'BOOLEAN'),
    ('is_city', 'BOOLEAN'),
    ('has_harbor', 'BOOLEAN'),
    ('victory_points', 'INTEGER DEFAULT 0'),
])
```

### 8. Testing: End-to-End Coverage

In addition to unit tests, add integration tests for:
- **Parser → collector → DB**: Parse RoF map.sql line → store_snapshot() → verify all 16 fields persisted
- **DB migration**: `_ensure_columns` adds new columns without data loss
- **API serialization**: New fields appear correctly in JSON responses
- **Mixed-tribe player**: Player with villages of different tribes displays correctly
