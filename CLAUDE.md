# WITEK — Wirtualny Informator Taktyczno-Ekonomiczny Koalicji

## Project Overview

WITEK is a **Travian Legends** alliance analytics tool + Discord bot for the UFOLODZY alliance on server ts31.x3.europe.travian.com. Named after H2P_Gucio (Witold Tacikiewicz).

- **Flask** web dashboard for village/player/alliance data
- **Discord bot** (py-cord) with slash commands for attack coordination, identity linking, server stats
- **Data source**: Public `map.sql` endpoint — `GET {server_url}/map.sql` — no auth needed, ~1.6MB, 14k villages

## Architecture

```
run.py                  # Entrypoint: Flask + bot + scheduler
├── app/                # Flask application
│   ├── __init__.py     # App factory (create_app)
│   ├── config.py       # Config from .env + config/config.yaml
│   ├── database.py     # SQLAlchemy setup
│   ├── auth_utils.py    # RBAC decorators (login_required, role_required)
│   ├── models.py       # Snapshot, Village, Player, Alliance, User, AttackReport,
│   │                   # DefenseThread, VillageTroops, TroopSupport, BattleReport,
│   │                   # Alert, MonitorSettings, PersonalAlert
│   ├── map_sql/        # Parser + collector + alerts for Travian map.sql
│   │   ├── parser.py   # map.sql line parser
│   │   ├── collector.py# Fetch + store + run alert detection
│   │   └── alerts.py   # Alert engine: pop drops, new villages, alliance changes
│   ├── routes/         # Flask blueprints: dashboard, players, alliances, auth,
│   │                   # attacks, defense, map, reports
│   └── templates/      # Jinja2 templates with Travian visual style
├── bot/                # Discord bot
│   ├── bot.py          # create_bot(), db_query() helper
│   ├── utils.py        # Unit speeds, crop tables, distance calc, time parsing
│   └── cogs/           # general.py, identity.py, attacks.py, defense.py,
│                       # alerts.py (auto-send alerts), recon.py (/tnieaktywni),
│                       # economy.py (/tcropper, /tszukaj, /tporownaj, /tsymulacja),
│                       # digest.py (/tdigest), monitor.py (/tmonitor)
├── config/             # YAML config (config.yaml)
├── tests/              # pytest tests
└── docker-compose*.yml # Dev (SQLite) and prod (PostgreSQL) Docker configs
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

Real Travian map.sql uses backtick-quoted table names:
```sql
INSERT INTO `x_world` VALUES (1,-200,-200,3,10187,'01',480,'player',38,'alliance',156,NULL,FALSE,NULL,NULL,NULL);
```
16 fields: id, x, y, tid, vid, village_name, uid, player_name, aid, alliance_name, population, (5 NULLs)

### Bot Threading

The bot runs in a daemon thread alongside Flask. The Werkzeug reloader guard in `run.py` prevents duplicate bot instances in debug mode (`WERKZEUG_RUN_MAIN` check).

### Docker

- **Dev**: `docker-compose.dev.yml` — SQLite, source mounted, FLASK_DEBUG=true
- **Prod**: `docker-compose.yml` — PostgreSQL 16, health checks, named volumes

### Alert System (map.sql)

After each map.sql snapshot, `collector.py` runs `detect_alerts()` which compares the new snapshot with the previous one. Alerts are stored as `Alert` rows in the DB (persist → commit → deliver pattern). The `AlertsCog` bot cog has a 60s background loop that picks up `notified=False` alerts, sends Discord embeds, and marks them as notified.

**Alert types:**
- `pop_drop` — Player population dropped ≥ threshold% (default 15%)
- `new_village` — New non-allied village appeared within radius of allied positions
- `alliance_change` — Player joined/left/switched alliance (involving our alliances or nearby enemies)

**Snapshot validation:** `validate_snapshot_pair()` rejects new snapshots with < 50% of previous village count (truncation guard prevents false alerts from partial downloads).

### Inactive Finder (/tnieaktywni)

Cohort-based: anchors on latest snapshot to find nearby players, then checks earliest snapshot for same UIDs. Both `total_pop` AND `village_count` must be unchanged to flag as inactive. Uses bounding-box prefilter with torus wrap-around before exact distance calc.

## Commands

```bash
# Local development
python run.py                       # Flask + bot (if DISCORD_TOKEN set)
python run.py --scheduled           # Flask + bot + daily map.sql collection
python run.py --bot-only            # Discord bot only (no Flask)
python run.py --collect             # One-shot: fetch and store map.sql
python run.py --from-file map.sql   # Import from local file

# Docker
docker compose -f docker-compose.dev.yml up    # Dev mode (SQLite)
docker compose up -d                           # Production (PostgreSQL)

# Tests
python -m pytest tests/ -v
```

## Configuration

1. Copy `.env.example` → `.env` and fill in values
2. Copy `config/config.example.yaml` → `config/config.yaml` and set alliance IDs
3. Key env vars: `DISCORD_TOKEN`, `DISCORD_GUILD_ID`, `TRAVIAN_SERVER_URL`

## Discord Slash Commands

| Command | Description |
|---------|-------------|
| `/thelp` | Command list |
| `/tinfo` | Bot info + uptime |
| `/tstats` | Server statistics (players, alliances, top 5) |
| `/tlink <player>` | Link Discord account to Travian player |
| `/tunlink` | Remove link |
| `/twhoami` | Show linked Travian profile |
| `/tatak` | Report attack on alliance village (creates/reuses defense thread) |
| `/tdodaj` | Add attack to existing defense thread (auto-detects target) |
| `/tataki` | List recent attacks |
| `/trozwiaz` | Resolve attack report + archive thread |
| `/twojska` | Register garrison troops (auto-detects coords in thread) |
| `/twsparcie` | Register support sent (auto-detects target in thread) |
| `/tstan` | Show village defense status (auto-detects coords in thread) |
| `/tdef` | Who can send def? Alliance villages sorted by ETA |
| `/traport` | Parse battle report (modal) |
| `/traporty` | List recent battle reports |
| `/tnieaktywni` | Find inactive players nearby (enhanced /tafk with history) |
| `/tcropper` | Find cropper villages (9c/15c) nearby |
| `/tszukaj` | Search villages by player, alliance, population, radius |
| `/tporownaj` | Compare two alliances side-by-side |
| `/tsymulacja` | Combat simulator — calculate battle losses (modal) |
| `/tdigest` | Weekly alliance digest (population, members, attacks) |
| `/tmonitor` | Enable/disable personal village monitoring (DM alerts) |
| `/tmonitor_ustawienia` | Adjust monitoring thresholds (pop drop, radius) |

## Coding Conventions

- **Language**: Comments and UI text in Polish; code identifiers in English
- **Style**: No comments on obvious code; comment only what needs clarification
- **Discord embeds**: Tactical colors — red=attack, green=defense/success, yellow=warning, blue=info, gold=identity
- **Footer**: `"⚔️ WITEK — Na cześć Gucio"` on all embeds
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
