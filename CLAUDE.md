# W.I.T.E.K — Wirtualny Informator Taktyczno-Ekonomiczny Koalicji

## Project Overview

W.I.T.E.K is a **Travian Legends** alliance analytics tool + Discord bot operated in a **RoF-first** setup. The default repo profile is `rof-x3`; archived classic presets live under `legacy\ts31\`. Named after H2P_Gucio (Witold Tacikiewicz).

- **Flask** web dashboard for village/player/alliance data, alerts, diplomacy, and search
- **Discord bot** (py-cord) with **9 cogs / 34 slash commands** for attack coordination, identity linking, calculators, recon, and diplomacy
- **Browser extension API** for manual import of battle reports, spy reports, troop overviews, incoming attacks, and selected `hero` / `marketplace` / `training` snapshots
- **Tests**: current repo collects **882 pytest tests**
- **Data source**: Public `map.sql` endpoint — `GET {server_url}/map.sql` — no auth needed, ~1.6MB, ~14k villages

## Architecture

```
run.py                  # Entrypoint: Flask + bot + scheduler / one-shot collector CLI
├── app/                # Flask application
│   ├── __init__.py     # App factory (create_app)
│   ├── config.py       # Config from .env + config/config.yaml
│   ├── database.py     # SQLAlchemy setup + lightweight schema sync
│   ├── auth_utils.py   # RBAC decorators (login_required, role_required)
│   ├── models.py       # Snapshot, Village, Player, Alliance, User, AttackReport,
│   │                   # DefenseThread, VillageTroops, TroopSupport, BattleReport,
│   │                   # Alert, SpyReport, DiplomaticRelation, GameData
│   ├── map_sql/        # Parser + collector + alerts for Travian map.sql
│   │   ├── parser.py   # map.sql line parser
│   │   ├── collector.py# Fetch + store + run alert detection
│   │   └── alerts.py   # Alert engine: pop drops, new villages, alliance changes
│   ├── routes/         # 12 modules: alerts_web, alliances, api_ext, attacks,
│   │                   # auth, dashboard, defense, diplomacy, map, players,
│   │                   # reports, search
│   └── templates/      # Jinja2 templates with Travian visual style
├── bot/                # Discord bot
│   ├── bot.py          # create_bot(), db_query() helper
│   ├── utils.py        # Unit speeds, crop tables, distance calc, time parsing
│   ├── tribes.py       # Single source of truth for tribe/unit data
│   ├── deep_links.py   # Travian in-game link generator
│   └── cogs/           # 9 cogs: alerts, attacks, defense, digest, diplomacy,
│                       # economy, general, identity, recon
├── extension/          # Chrome extension (content scripts, service worker, popup)
├── server_profile.py   # Multi-server profile resolver
├── config/             # YAML config (config.yaml)
├── legacy/ts31/        # Archived classic preset
├── tests/              # 882 pytest tests
├── docker-compose.yml  # Prod/default Docker stack (PostgreSQL)
└── docker-compose.dev.yml # Dev Docker stack (SQLite)
```

## Key Technical Decisions

### Database Access in Discord Bot

All DB access in bot cogs MUST go through `db_query()` from `bot.bot`:

```python
from bot.bot import db_query

# Inside a cog command:
result = await db_query(self.bot, lambda: Player.query.get(uid))
```

This runs blocking SQLAlchemy queries in an executor with Flask app context, preventing Discord event loop blocking. **Never** use `with app.app_context()` directly in async handlers.

**CRITICAL**: Never return raw SQLAlchemy model objects from `db_query()`. They become detached from the session after the executor completes. Always return plain dicts or tuples.

### map.sql Format

Real Travian `map.sql` uses backtick-quoted table names:

```sql
INSERT INTO `x_world` VALUES (1,-200,-200,3,10187,'01',480,'player',38,'alliance',156,NULL,FALSE,NULL,NULL,NULL);
```

16 fields total: id, x, y, tid, vid, village_name, uid, player_name, aid, alliance_name, population, plus 5 RoF-era metadata slots.

**Tribe IDs (tid):** 1=Romans, 2=Teutons, 3=Gauls, 4=Nature, 5=Natars, 6=Egyptians, 7=Huns, 8=Spartans, 9=Vikings. RoF profiles exclude tid=2 Teutons.

`bot/tribes.py` is the single source of truth for all tribe/unit data (speeds, crop, combat stats). `bot/utils.py` generates its legacy dicts from it.

### Bot Threading

The bot runs in a daemon thread alongside Flask. The Werkzeug reloader guard in `run.py` prevents duplicate bot instances in debug mode (`WERKZEUG_RUN_MAIN` check).

### Docker / Runtime Reality

- **Prod/default**: `docker-compose.yml` — PostgreSQL 16 + app container
- **Dev**: `docker-compose.dev.yml` — SQLite + bind mounts
- **Container command**: Dockerfile defaults to `python run.py --scheduled --port 5000`
- **Collector cadence**: `scheduler.fetch_interval_minutes` in YAML, default `60`
- **No separate RoF compose file**: standard `docker compose up -d` is already the RoF-first path

### Alert System (map.sql)

After each map.sql snapshot, `collector.py` runs `detect_alerts()` which compares the new snapshot with the previous one. Alerts are stored as `Alert` rows in the DB (persist → commit → deliver pattern). The `AlertsCog` bot cog has a 60s background loop that picks up `notified=False` alerts, sends Discord embeds, and marks them as notified.

**Alert types:**
- `pop_drop` — Player population dropped ≥ threshold% → Discord + dashboard
- `new_village` — New non-allied village appeared within radius of allied positions → dashboard only
- `alliance_change` — Player joined/left/switched alliance → dashboard only

**`discord_eligible` flag:** Only `pop_drop` alerts are sent to Discord by default.

**Snapshot validation:** `validate_snapshot_pair()` rejects new snapshots with < 50% of previous village count (truncation guard prevents false alerts from partial downloads).

### Browser Extension API

The extension posts manually collected Travian data to Flask endpoints protected by `EXT_API_TOKEN`:

- `POST /api/ext/report`
- `POST /api/ext/spy-report`
- `POST /api/ext/troops`
- `POST /api/ext/incoming`
- `POST /api/ext/game-data`

Extension submissions are user-triggered, not background scraping.

### Inactive Finder (`/tnieaktywni`)

Cohort-based: anchors on latest snapshot to find nearby players, then checks earliest snapshot for same UIDs. Both `total_pop` AND `village_count` must be unchanged to flag as inactive. Uses bounding-box prefilter before exact distance calc.

### Rise of Factions (RoF) Support

Config-driven server profiles in `config/config.yaml` let the same codebase support both RoF and archived classic presets.

**Repo default / temporary x10 tests:**
- Default workflow uses `SERVER_PROFILE=rof-x3`
- For short smoke tests, temporarily override `TRAVIAN_SERVER_URL=https://rof.x10.international.travian.com`
- Remove the override after tests so startup returns to RoF x3

**Map Edge Wrapping** (`features.map_edge_wrapping`, default `false` on RoF):
- Controls whether distance calculations wrap around map edges
- RoF uses flat-map distance; classic profiles can enable wrapping

**Legionnaire Rebalance** (`legionnaire_rebalanced`, `true` on RoF x3):
- Applies RoF stats to Legionnaire: def_cav 50→70, speed 6→7
- `apply_legionnaire_rebalance()` in `tribes.py` runs at import time

## Commands

```bash
# Local development
python run.py                       # Flask + bot (if DISCORD_TOKEN set)
python run.py --scheduled           # Flask + bot + interval map.sql collection
python run.py --bot-only            # Discord bot only (no Flask)
python run.py --collect             # One-shot: fetch and store map.sql
python run.py --from-file map.sql   # Import from local file

# Docker
docker compose -f docker-compose.dev.yml up    # Dev mode (SQLite)
docker compose up -d                           # Prod/default RoF-first stack

# Tests
python -m pytest tests/ -v
```

## Configuration

1. Copy `.env.example` → `.env` and fill in values
2. Copy `config/config.example.yaml` → `config/config.yaml` and set alliance IDs
3. Key env vars: `DISCORD_TOKEN`, `DISCORD_GUILD_ID`, `SERVER_PROFILE`
4. Optional overrides/features: `TRAVIAN_SERVER_URL`, `EXT_API_TOKEN`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`

## Discord Slash Commands

| Command | Description |
|---------|-------------|
| `/thelp` | Command list |
| `/tinfo` | Bot info + uptime |
| `/tstats` | Server statistics (players, alliances, top 5) |
| `/tlink <player>` | Link Discord account to Travian player |
| `/tunlink` | Remove link |
| `/twhoami` | Show linked Travian profile |
| `/tprofil` | Show Travian player profile |
| `/tatak` | Report attack on alliance village |
| `/tdodaj` | Add attack to existing defense thread |
| `/tataki` | List active attacks |
| `/trozwiaz` | Resolve attack report + archive thread |
| `/tdef` | Who can send def? Alliance villages sorted by ETA |
| `/traport` | Parse battle report |
| `/traport_reczny` | Add battle report manually |
| `/traporty` | List recent battle reports |
| `/twojska` | Register garrison troops |
| `/twsparcie` | Register support sent |
| `/tstan` | Show village defense status |
| `/tzboza` | Show village crop balance |
| `/tenemy` | Find nearby enemies (excluding allies/pacts) |
| `/tnieaktywni` | Find inactive players nearby |
| `/tcropper` | Find cropper villages nearby |
| `/tszukaj` | Search villages by filters / area |
| `/tporownaj` | Compare two alliances |
| `/tsymulacja` | Combat simulator |
| `/tbezpieczne` | Safe-send calculator |
| `/tileobrony` | Defense calculator |
| `/tprzechwyc` | Interception calculator |
| `/tbuildtime` | Training time / cost calculator |
| `/ttraining` | Training resources / time calculator |
| `/tdigest` | Weekly alliance digest |
| `/tdyplomacja` | Show diplomatic relations |
| `/tdodaj_relacje` | Add diplomatic relation |
| `/tusun_relacje` | Remove diplomatic relation |

## Coding Conventions

- **Language**: Comments and UI text in Polish; code identifiers in English
- **Style**: No comments on obvious code; comment only what needs clarification
- **Discord embeds**: Tactical colors — red=attack, green=defense/success, yellow=warning, blue=info, gold=identity
- **Footer**: `⚔️ W.I.T.E.K — Na cześć H2P_Gucio` on all embeds
- **Error handling**: Polish user-facing messages with emoji indicators (✅ ❌ ⚠️ 💡)
- **Testing**: pytest; run `python -m pytest tests/ -v` before any commit
- **User context**: Beginner programmer — explain choices clearly in plan docs

## Travian CDN Assets

Icon base URL: `https://cdn.legends.travian.com/gpack/417.3/img_ltr/`
- Tribe icons: `global/tribes/{roman|teuton|gaul}_medium.png` (also `_small.png`; `_large.png` does NOT exist)
- Resources: `global/resources/{lumber|clay|iron|crop}_small.png` (also `_tiny.png`)
- Attack icons (legacy GIF): `legacy/a/att1.gif` (raid), `att2.gif` (attack), `att3.gif` (spy), `def1.gif` (defense)
- Hero: `hud/topBar/hero/states/heroHome.png`
- All URLs verified as of gpack 417.3; Discord can embed these as thumbnail/image

## Visual Style

Templates use Travian-inspired dark/medieval theme:
- Body: olive green `rgb(103, 119, 46)`
- Panels: warm brown `#5e463a`
- Accents: Travian green `#5a9a0a`
- Font: MedievalSharp (Google Fonts) with serif fallback


