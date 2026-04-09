"""Komendy ekonomiczne — croppery, szukanie wiosek, porównanie sojuszy."""

import asyncio
import logging
import re
import time

import aiohttp
import discord
from discord.ext import commands
from sqlalchemy import func, or_

from bot.bot import db_query
from bot.utils import (
    COMBAT_BY_NAME,
    COLOR_ATTACK,
    COLOR_DEFENSE,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_WARNING,
    FOOTER,
    TRIBE_EMOJI,
    TRIBE_NAMES,
    TYPE_EMOJI,
    UNIT_SPEEDS,
    WALL_BONUS,
    _COMBAT_ABBREV,
    calc_needed_defense,
    calc_safe_distance,
    coords_display,
    normalize_unit_name,
    parse_army_input,
    parse_coords,
    simulate_combat,
    torus_distance,
)

log = logging.getLogger(__name__)

MAX_RESULTS = 25

# Travian landscape types → cropper classification
CROPPER_TYPES: dict[int, str] = {
    3: "15c",   # 1|1|1|15
    4: "9c",    # 3|3|3|9
    5: "9c",    # 1|1|1|9
}

# Max tiles to scan per command invocation
MAX_SCAN_TILES = 2000

# Concurrency / timeout for Travian API calls
MAX_CONCURRENT_API = 15
API_TILE_TIMEOUT = 5

# API availability cache (module-level, simple TTL)
_api_cache: dict[str, tuple[bool, float]] = {}
_API_CACHE_TTL = 300  # 5 minutes


# ------------------------------------------------------------------ #
# Shared torus bounding-box filter (same logic as recon.py)
# ------------------------------------------------------------------ #

def _bbox_filter(col, center, radius, map_size):
    """SQLAlchemy filter for one axis of a torus bounding box."""
    half = map_size // 2
    lo = center - radius
    hi = center + radius
    if lo >= -half and hi <= half:
        return col.between(lo, hi)
    elif lo < -half:
        return or_(col >= lo + map_size, col <= hi)
    else:
        return or_(col >= lo, col <= hi - map_size)


# ------------------------------------------------------------------ #
# Tile coordinate generation
# ------------------------------------------------------------------ #

def _tiles_in_radius(cx, cy, radius, map_size):
    """Generate (x, y) coordinates within circular radius on a torus map.

    Returns list sorted by distance from center (closest first).
    """
    half = map_size // 2
    r2 = radius * radius
    coords = []
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if dx * dx + dy * dy > r2:
                continue
            tx = cx + dx
            ty = cy + dy
            if tx > half:
                tx -= map_size
            elif tx < -half:
                tx += map_size
            if ty > half:
                ty -= map_size
            elif ty < -half:
                ty += map_size
            coords.append((tx, ty))
    coords.sort(key=lambda t: (t[0] - cx) ** 2 + (t[1] - cy) ** 2)
    return coords


# ------------------------------------------------------------------ #
# Travian API helpers
# ------------------------------------------------------------------ #

def _extract_landscape_type(data):
    """Extract landscape/field type from a Travian tile-details response.

    Returns int field type or None if unparseable.
    """
    if not isinstance(data, dict):
        return None

    inner = data.get("response", data)

    # Format: {"tiles": [{"landscape": {"type": N}}]}
    tiles = inner.get("tiles", [])
    if tiles and isinstance(tiles, list):
        tile = tiles[0]
        if isinstance(tile, dict):
            landscape = tile.get("landscape", {})
            if isinstance(landscape, dict) and "type" in landscape:
                return landscape["type"]
            for key in ("fieldType", "resType"):
                if key in tile and isinstance(tile[key], int):
                    return tile[key]

    # Flat format: {"fieldType": N} or {"resType": N}
    for key in ("fieldType", "resType", "landscapeType"):
        if key in inner and isinstance(inner[key], int):
            return inner[key]

    return None


async def _probe_travian_api(server_url, x, y):
    """Check if the Travian tile-details API is accessible without auth.

    Uses a module-level TTL cache to avoid repeated probes.
    Returns True if API is available, False otherwise.
    """
    cache_key = server_url.rstrip("/")
    cached = _api_cache.get(cache_key)
    if cached is not None:
        result, ts = cached
        if time.monotonic() - ts < _API_CACHE_TTL:
            return result

    url = f"{cache_key}/api/v1/map/tile-details"
    available = False
    try:
        timeout = aiohttp.ClientTimeout(total=API_TILE_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json={"x": x, "y": y}) as resp:
                if resp.status in (401, 403):
                    log.info("Travian API wymaga autoryzacji (HTTP %d)", resp.status)
                elif resp.status == 404:
                    log.info("Travian API nie istnieje na tym serwerze (HTTP 404)")
                elif resp.status == 200:
                    data = await resp.json()
                    lt = _extract_landscape_type(data)
                    if lt is not None:
                        available = True
                    else:
                        log.info(
                            "Travian API: 200 ale format nierozpoznany: %s",
                            str(data)[:200],
                        )
                else:
                    log.info("Travian API: nieoczekiwany HTTP %d", resp.status)
    except Exception as exc:
        log.debug("Travian API probe error: %s", exc)

    _api_cache[cache_key] = (available, time.monotonic())
    return available


async def _scan_tiles_api(server_url, coords_list):
    """Batch-fetch landscape types for multiple tiles via Travian API.

    Returns dict mapping (x, y) → landscape_type (int).
    Uses semaphore for concurrency control.
    """
    url = f"{server_url.rstrip('/')}/api/v1/map/tile-details"
    results: dict[tuple[int, int], int] = {}
    sem = asyncio.Semaphore(MAX_CONCURRENT_API)
    timeout = aiohttp.ClientTimeout(total=API_TILE_TIMEOUT)

    async def _fetch_one(session, x, y):
        async with sem:
            try:
                async with session.post(
                    url, json={"x": x, "y": y}, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        lt = _extract_landscape_type(data)
                        if lt is not None:
                            results[(x, y)] = lt
            except Exception:
                pass

    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_one(session, x, y) for x, y in coords_list]
        await asyncio.gather(*tasks)

    return results


# ------------------------------------------------------------------ #
# DB helpers (return plain dicts — never raw SQLAlchemy objects)
# ------------------------------------------------------------------ #

def _get_occupancy(cx, cy, radius, map_size):
    """Get village occupancy in radius from latest snapshot.

    Returns (dict[(x,y) → info], snap_date_str) or ({}, None).
    """
    from app.models import Snapshot, Village

    snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
    if not snap:
        return {}, None

    villages = (
        Village.query
        .filter(
            Village.snapshot_id == snap.id,
            Village.uid > 0,
            _bbox_filter(Village.x, cx, radius, map_size),
            _bbox_filter(Village.y, cy, radius, map_size),
        )
        .all()
    )
    occ = {}
    for v in villages:
        occ[(v.x, v.y)] = {
            "player": v.player_name,
            "alliance": v.alliance_name or "",
            "pop": v.population,
            "tid": v.tid,
        }
    snap_date = snap.fetched_at.strftime("%Y-%m-%d %H:%M UTC")
    return occ, snap_date


def _search_villages(cx, cy, radius, map_size, gracz, sojusz, min_pop, max_pop):
    """Search occupied villages matching criteria.

    Returns (list[dict], snap_date_str) or (None, None) if no data.
    """
    from app.models import Snapshot, Village

    snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
    if not snap:
        return None, None

    query = Village.query.filter(
        Village.snapshot_id == snap.id,
        Village.uid > 0,
        _bbox_filter(Village.x, cx, radius, map_size),
        _bbox_filter(Village.y, cy, radius, map_size),
    )
    if gracz:
        query = query.filter(Village.player_name.ilike(f"%{gracz}%"))
    if sojusz:
        query = query.filter(Village.alliance_name.ilike(f"%{sojusz}%"))
    if min_pop > 0:
        query = query.filter(Village.population >= min_pop)
    if max_pop > 0:
        query = query.filter(Village.population <= max_pop)

    villages = query.all()
    results = []
    for v in villages:
        dist = torus_distance(cx, cy, v.x, v.y, map_size)
        if dist <= radius:
            results.append({
                "x": v.x, "y": v.y,
                "name": v.name,
                "player": v.player_name,
                "alliance": v.alliance_name or "",
                "pop": v.population,
                "tid": v.tid,
                "dist": dist,
            })
    snap_date = snap.fetched_at.strftime("%Y-%m-%d %H:%M UTC")
    return results, snap_date


# ------------------------------------------------------------------ #
# Embed builders
# ------------------------------------------------------------------ #

def _build_cropper_embed(croppers, cx, cy, zasieg, typ, server_url,
                         snap_date, truncated):
    """Build Discord embed with cropper search results."""
    type_label = {"15c": "15c", "9c": "9c", "oba": "9c+15c"}[typ]
    embed = discord.Embed(
        title=f"🌾 Croppery ({type_label}) — ({cx}|{cy}), r={zasieg}",
        color=COLOR_SUCCESS,
    )

    shown = croppers[:MAX_RESULTS]
    lines = []
    for i, c in enumerate(shown, 1):
        coords = coords_display(server_url, c["x"], c["y"])
        type_icon = "🌾🌾" if c["type"] == "15c" else "🌾"

        if c["occupied"]:
            tribe_emoji = TRIBE_EMOJI.get(c.get("tid", 0), "")
            line = (
                f"**{i}.** {type_icon} **{c['type']}** {coords} "
                f"— {tribe_emoji} {c['player']} [{c['alliance']}] "
                f"({c['pop']:,} pop) • 📏 {c['dist']:.1f}"
            )
        else:
            line = (
                f"**{i}.** {type_icon} **{c['type']}** {coords} "
                f"— ✅ **WOLNE** • 📏 {c['dist']:.1f}"
            )
        lines.append(line)

    description = "\n".join(lines)
    if len(description) > 4096:
        truncated_lines = []
        total = 0
        for line in lines:
            if total + len(line) + 1 > 4000:
                truncated_lines.append("*...lista obcięta*")
                break
            truncated_lines.append(line)
            total += len(line) + 1
        description = "\n".join(truncated_lines)

    embed.description = description

    total_found = len(croppers)
    free_count = sum(1 for c in croppers if not c["occupied"])
    footer_parts = [
        f"📊 Znaleziono {total_found} cropperów ({free_count} wolnych)"
    ]
    if total_found > MAX_RESULTS:
        footer_parts[0] += f" — pokazano {MAX_RESULTS}"
    if truncated:
        footer_parts.append(
            "⚠️ Skan częściowy — zmniejsz promień dla pełnych wyników"
        )
    if snap_date:
        footer_parts.append(f"Dane: {snap_date}")
    footer_parts.append(FOOTER)
    embed.set_footer(text="\n".join(footer_parts))
    return embed


def _build_search_embed(results, cx, cy, zasieg, server_url, snap_date,
                        gracz, sojusz):
    """Build Discord embed with village search results."""
    title_parts = [f"🔍 Wioski w okolicy ({cx}|{cy}), r={zasieg}"]
    if gracz:
        title_parts.append(f"gracz: {gracz}")
    if sojusz:
        title_parts.append(f"sojusz: {sojusz}")
    title = " — ".join(title_parts)

    embed = discord.Embed(title=title, color=COLOR_INFO)

    shown = results[:MAX_RESULTS]
    lines = []
    for i, v in enumerate(shown, 1):
        coords = coords_display(server_url, v["x"], v["y"])
        tribe_emoji = TRIBE_EMOJI.get(v.get("tid", 0), "")
        line = (
            f"**{i}.** {v['name']} {coords}\n"
            f"  {tribe_emoji} {v['player']} [{v['alliance']}] "
            f"— {v['pop']:,} pop • 📏 {v['dist']:.1f}"
        )
        lines.append(line)

    description = "\n".join(lines)
    if len(description) > 4096:
        truncated_lines = []
        total = 0
        for line in lines:
            if total + len(line) + 1 > 4000:
                truncated_lines.append("*...lista obcięta*")
                break
            truncated_lines.append(line)
            total += len(line) + 1
        description = "\n".join(truncated_lines)

    embed.description = description

    total_found = len(results)
    footer_text = f"📊 Znaleziono {total_found} wiosek"
    if total_found > MAX_RESULTS:
        footer_text += f" — pokazano {MAX_RESULTS}"
    if snap_date:
        footer_text += f"\nDane: {snap_date}"
    embed.set_footer(text=f"{footer_text}\n{FOOTER}")
    return embed


# ------------------------------------------------------------------ #
# Alliance comparison helpers (return plain dicts — no SA objects)
# ------------------------------------------------------------------ #

def _fmt(n):
    """Format number with space as thousands separator."""
    return f"{n:,}".replace(",", " ")


def _find_alliance(query_str):
    """Find an alliance by name (case-insensitive LIKE) or by aid.

    Returns dict with alliance info or None.
    """
    from app.database import db
    from app.models import Alliance

    # Try numeric aid first
    try:
        aid = int(query_str)
        a = db.session.get(Alliance, aid)
        if a:
            return {"aid": a.aid, "name": a.name}
    except (ValueError, TypeError):
        pass

    # Case-insensitive name match
    a = Alliance.query.filter(
        func.lower(Alliance.name) == func.lower(query_str)
    ).first()
    if a:
        return {"aid": a.aid, "name": a.name}

    # Partial match
    a = Alliance.query.filter(
        Alliance.name.ilike(f"%{query_str}%")
    ).first()
    if a:
        return {"aid": a.aid, "name": a.name}

    return None


def _alliance_stats(aid):
    """Gather stats for one alliance from the latest snapshot.

    Returns dict with stats or None if no data.
    """
    from app.models import Snapshot, Village

    snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
    if not snap:
        return None

    villages = (
        Village.query
        .filter(Village.snapshot_id == snap.id, Village.aid == aid)
        .all()
    )
    if not villages:
        return None

    total_pop = sum(v.population for v in villages)
    village_count = len(villages)

    # Distinct players with their aggregated pop and tribe
    players = {}
    for v in villages:
        if v.uid not in players:
            players[v.uid] = {"name": v.player_name, "pop": 0, "tid": v.tid}
        players[v.uid]["pop"] += v.population

    member_count = len(players)
    avg_pop = total_pop // member_count if member_count else 0

    # Top 5 by pop
    top5 = sorted(players.values(), key=lambda p: p["pop"], reverse=True)[:5]

    # Tribe distribution (count of players)
    tribes = {}
    for p in players.values():
        tid = p["tid"]
        tribes[tid] = tribes.get(tid, 0) + 1

    snap_date = snap.fetched_at.strftime("%Y-%m-%d %H:%M UTC")
    snap_id = snap.id

    return {
        "total_pop": total_pop,
        "village_count": village_count,
        "member_count": member_count,
        "avg_pop": avg_pop,
        "top5": [{"name": p["name"], "pop": p["pop"]} for p in top5],
        "tribes": tribes,
        "snap_date": snap_date,
        "snap_id": snap_id,
    }


def _alliance_growth(aid, current_snap_id):
    """Calculate pop growth by comparing current snapshot with the previous one.

    Returns (growth_int, True) or (None, False) if no previous data.
    """
    from app.models import Snapshot, Village

    prev_snap = (
        Snapshot.query
        .filter(Snapshot.id < current_snap_id)
        .order_by(Snapshot.fetched_at.desc())
        .first()
    )
    if not prev_snap:
        return None, False

    prev_pop = (
        Village.query
        .with_entities(func.sum(Village.population))
        .filter(Village.snapshot_id == prev_snap.id, Village.aid == aid)
        .scalar()
    ) or 0

    current_pop = (
        Village.query
        .with_entities(func.sum(Village.population))
        .filter(Village.snapshot_id == current_snap_id, Village.aid == aid)
        .scalar()
    ) or 0

    return current_pop - prev_pop, True


def _build_comparison_embed(name1, stats1, growth1, name2, stats2, growth2):
    """Build a Discord embed comparing two alliances."""
    embed = discord.Embed(
        title="🏰 Porównanie sojuszy",
        description=f"📊 **{name1}** vs **{name2}**",
        color=COLOR_INFO,
    )

    # Main stats
    lines = [
        f"👥 Członkowie: **{stats1['member_count']}** vs **{stats2['member_count']}**",
        f"🏘️ Wioski: **{stats1['village_count']}** vs **{stats2['village_count']}**",
        f"📈 Populacja: **{_fmt(stats1['total_pop'])}** vs **{_fmt(stats2['total_pop'])}**",
        f"📊 Średnia/gracz: **{_fmt(stats1['avg_pop'])}** vs **{_fmt(stats2['avg_pop'])}**",
    ]

    # Growth
    if growth1 is not None or growth2 is not None:
        g1 = f"+{_fmt(growth1)}" if growth1 and growth1 > 0 else _fmt(growth1) if growth1 else "?"
        g2 = f"+{_fmt(growth2)}" if growth2 and growth2 > 0 else _fmt(growth2) if growth2 else "?"
        lines.append(f"📉 Zmiana: **{g1}** vs **{g2}**")

    embed.add_field(name="⚖️ Statystyki", value="\n".join(lines), inline=False)

    # Tribe distribution
    tribe_lines = []
    all_tids = sorted(set(list(stats1["tribes"].keys()) + list(stats2["tribes"].keys())))
    for tid in all_tids:
        emoji = TRIBE_EMOJI.get(tid, "❓")
        tname = TRIBE_NAMES.get(tid, f"Plemię {tid}")
        c1 = stats1["tribes"].get(tid, 0)
        c2 = stats2["tribes"].get(tid, 0)
        tribe_lines.append(f"{emoji} {tname}: **{c1}** vs **{c2}**")

    if tribe_lines:
        embed.add_field(
            name="🗡️ Rozkład plemion",
            value="\n".join(tribe_lines),
            inline=False,
        )

    # Top 5 for each alliance (side by side with inline)
    top1_lines = []
    for i, p in enumerate(stats1["top5"], 1):
        top1_lines.append(f"**{i}.** {p['name']} — {_fmt(p['pop'])} pop")
    embed.add_field(
        name=f"🏆 Top 5 {name1}",
        value="\n".join(top1_lines) if top1_lines else "Brak danych",
        inline=True,
    )

    top2_lines = []
    for i, p in enumerate(stats2["top5"], 1):
        top2_lines.append(f"**{i}.** {p['name']} — {_fmt(p['pop'])} pop")
    embed.add_field(
        name=f"🏆 Top 5 {name2}",
        value="\n".join(top2_lines) if top2_lines else "Brak danych",
        inline=True,
    )

    footer = FOOTER
    if stats1.get("snap_date"):
        footer += f" | Dane z {stats1['snap_date']}"
    embed.set_footer(text=footer)

    return embed


# ------------------------------------------------------------------ #
# Time parsing helper
# ------------------------------------------------------------------ #

_TRIBE_CHOICE_MAP = {"Rzymianie": 1, "Germanie": 2, "Galowie": 3}


def _parse_hours(text: str) -> float | None:
    """Parse time input: '2.5' (hours) or '2:30' (h:mm) → float hours."""
    text = text.strip()
    m = re.match(r'^(\d+):(\d{1,2})$', text)
    if m:
        h, mins = int(m.group(1)), int(m.group(2))
        return h + mins / 60.0 if mins < 60 else None
    try:
        val = float(text.replace(',', '.'))
        return val if val >= 0 else None
    except ValueError:
        return None


# ------------------------------------------------------------------ #
# Cog
# ------------------------------------------------------------------ #

class Economy(commands.Cog):
    """Komendy ekonomiczne — croppery, szukanie wiosek, porównanie sojuszy."""

    def __init__(self, bot):
        self.bot = bot

    def _server_url(self):
        return self.bot.flask_app.config.get("TRAVIAN_SERVER_URL", "")

    def _map_size(self):
        return self.bot.flask_app.config.get("TRAVIAN_MAP_SIZE", 401)

    # ------------------------------------------------------------------ #
    # /tcropper
    # ------------------------------------------------------------------ #

    @discord.slash_command(
        name="tcropper",
        description="Znajdź croppery (9c/15c) w okolicy",
    )
    @discord.option("kordy", str, description="Centrum szukania np. 76|43")
    @discord.option(
        "zasieg", int, description="Promień szukania (domyślnie 30)",
        required=False, default=30, min_value=5, max_value=100,
    )
    @discord.option(
        "typ", str, description="Typ croppera",
        required=False, choices=["15c", "9c", "oba"], default="oba",
    )
    @discord.option(
        "wolne", bool, description="Tylko wolne (niezajęte)",
        required=False, default=False,
    )
    async def tcropper(self, ctx, kordy: str, zasieg: int,
                       typ: str, wolne: bool):
        cx, cy = parse_coords(kordy)
        if cx is None:
            await ctx.respond(
                "❌ Nieprawidłowe koordynaty. Użyj formatu np. `76|43`",
                ephemeral=True,
            )
            return

        await ctx.defer()

        server_url = self._server_url()
        map_size = self._map_size()

        # 1. Probe API availability (cached)
        api_ok = await _probe_travian_api(server_url, cx, cy)
        if not api_ok:
            embed = discord.Embed(
                title="🌾 Crop Finder — API niedostępne",
                description=(
                    "Serwer Travian nie udostępnia API potrzebnego do "
                    "identyfikacji typów pól (9c/15c).\n\n"
                    "**Alternatywy:**\n"
                    "• [Kirilloid Crop Finder]"
                    "(https://kirilloid.github.io/travian/#cropFinder) "
                    "— wklej dane serwera\n"
                    "• [Travian Crop Finder]"
                    "(https://www.traviantools.com/crop-finder)\n\n"
                    f"💡 Użyj `/tszukaj kordy:{kordy} zasieg:{zasieg}` "
                    "aby przeszukać wioski w okolicy."
                ),
                color=COLOR_WARNING,
            )
            embed.set_footer(text=FOOTER)
            await ctx.followup.send(embed=embed)
            return

        # 2. Generate tiles to scan
        all_tiles = _tiles_in_radius(cx, cy, zasieg, map_size)
        truncated = False
        if len(all_tiles) > MAX_SCAN_TILES:
            all_tiles = all_tiles[:MAX_SCAN_TILES]
            truncated = True

        # 3. Scan via API
        tile_types = await _scan_tiles_api(server_url, all_tiles)

        if not tile_types:
            await ctx.followup.send(
                "⚠️ Nie udało się pobrać danych z serwera Travian. "
                "Serwer może blokować zapytania. Spróbuj ponownie później."
            )
            return

        # 4. Filter for croppers
        croppers = []
        for (x, y), lt in tile_types.items():
            crop_type = CROPPER_TYPES.get(lt)
            if crop_type is None:
                continue
            if typ != "oba" and crop_type != typ:
                continue
            dist = torus_distance(cx, cy, x, y, map_size)
            croppers.append({
                "x": x, "y": y, "type": crop_type,
                "dist": dist, "lt": lt,
            })

        if not croppers:
            type_label = {"15c": "15c", "9c": "9c", "oba": "9c/15c"}[typ]
            await ctx.followup.send(
                f"✅ Brak cropperów **{type_label}** w promieniu "
                f"{zasieg} pól od ({cx}|{cy})."
            )
            return

        # 5. Cross-reference with DB for occupancy
        occupancy, snap_date = await db_query(
            self.bot,
            lambda: _get_occupancy(cx, cy, zasieg, map_size),
        )

        for c in croppers:
            occ = occupancy.get((c["x"], c["y"]))
            if occ:
                c["occupied"] = True
                c["player"] = occ["player"]
                c["alliance"] = occ["alliance"]
                c["pop"] = occ["pop"]
                c["tid"] = occ["tid"]
            else:
                c["occupied"] = False

        if wolne:
            croppers = [c for c in croppers if not c["occupied"]]

        if not croppers:
            type_label = {"15c": "15c", "9c": "9c", "oba": "9c/15c"}[typ]
            await ctx.followup.send(
                f"✅ Brak **wolnych** cropperów {type_label} w promieniu "
                f"{zasieg} pól od ({cx}|{cy})."
            )
            return

        # 6. Sort: 15c first, then by distance
        croppers.sort(key=lambda c: (0 if c["type"] == "15c" else 1, c["dist"]))

        embed = _build_cropper_embed(
            croppers, cx, cy, zasieg, typ, server_url, snap_date, truncated,
        )
        await ctx.followup.send(embed=embed)

    # ------------------------------------------------------------------ #
    # /tszukaj
    # ------------------------------------------------------------------ #

    @discord.slash_command(
        name="tszukaj",
        description="Szukaj wiosek w okolicy",
    )
    @discord.option("kordy", str, description="Centrum szukania np. 76|43")
    @discord.option(
        "zasieg", int, description="Promień szukania (domyślnie 20)",
        required=False, default=20, min_value=5, max_value=100,
    )
    @discord.option(
        "gracz", str, description="Filtruj po nazwie gracza",
        required=False, default="",
    )
    @discord.option(
        "sojusz", str, description="Filtruj po nazwie sojuszu",
        required=False, default="",
    )
    @discord.option(
        "min_pop", int, description="Minimalna populacja",
        required=False, default=0,
    )
    @discord.option(
        "max_pop", int, description="Maksymalna populacja (0=bez limitu)",
        required=False, default=0,
    )
    async def tszukaj(self, ctx, kordy: str, zasieg: int,
                      gracz: str, sojusz: str,
                      min_pop: int, max_pop: int):
        cx, cy = parse_coords(kordy)
        if cx is None:
            await ctx.respond(
                "❌ Nieprawidłowe koordynaty. Użyj formatu np. `76|43`",
                ephemeral=True,
            )
            return

        await ctx.defer()

        server_url = self._server_url()
        map_size = self._map_size()

        results, snap_date = await db_query(
            self.bot,
            lambda: _search_villages(
                cx, cy, zasieg, map_size, gracz, sojusz, min_pop, max_pop,
            ),
        )

        if results is None:
            await ctx.followup.send(
                "💡 Brak danych — najpierw wykonaj import map.sql."
            )
            return

        if not results:
            filters = []
            if gracz:
                filters.append(f"gracz: {gracz}")
            if sojusz:
                filters.append(f"sojusz: {sojusz}")
            if min_pop > 0:
                filters.append(f"min pop: {min_pop}")
            if max_pop > 0:
                filters.append(f"max pop: {max_pop}")
            filter_str = f" ({', '.join(filters)})" if filters else ""
            await ctx.followup.send(
                f"✅ Brak wiosek w promieniu {zasieg} pól "
                f"od ({cx}|{cy}){filter_str}."
            )
            return

        results.sort(key=lambda v: v["dist"])

        embed = _build_search_embed(
            results, cx, cy, zasieg, server_url, snap_date, gracz, sojusz,
        )
        await ctx.followup.send(embed=embed)

    # ------------------------------------------------------------------ #
    # /tporownaj
    # ------------------------------------------------------------------ #

    @discord.slash_command(
        name="tporownaj",
        description="Porównaj dwa sojusze",
    )
    @discord.option("sojusz1", str, description="Nazwa lub ID pierwszego sojuszu")
    @discord.option("sojusz2", str, description="Nazwa lub ID drugiego sojuszu")
    async def tporownaj(self, ctx: discord.ApplicationContext,
                        sojusz1: str, sojusz2: str):
        await ctx.defer()

        # Look up both alliances
        a1 = await db_query(self.bot, lambda: _find_alliance(sojusz1))
        if not a1:
            await ctx.followup.send(
                f"❌ Nie znaleziono sojuszu: **{sojusz1}**", ephemeral=True,
            )
            return

        a2 = await db_query(self.bot, lambda: _find_alliance(sojusz2))
        if not a2:
            await ctx.followup.send(
                f"❌ Nie znaleziono sojuszu: **{sojusz2}**", ephemeral=True,
            )
            return

        if a1["aid"] == a2["aid"]:
            await ctx.followup.send(
                "⚠️ Podano ten sam sojusz dwa razy.", ephemeral=True,
            )
            return

        # Gather stats
        stats1 = await db_query(self.bot, lambda: _alliance_stats(a1["aid"]))
        stats2 = await db_query(self.bot, lambda: _alliance_stats(a2["aid"]))

        if not stats1 or not stats2:
            missing = a1["name"] if not stats1 else a2["name"]
            await ctx.followup.send(
                f"💡 Brak danych dla sojuszu **{missing}** — "
                "najpierw wykonaj import map.sql."
            )
            return

        # Growth (compare with previous snapshot)
        growth1, _ = await db_query(
            self.bot, lambda: _alliance_growth(a1["aid"], stats1["snap_id"]),
        )
        growth2, _ = await db_query(
            self.bot, lambda: _alliance_growth(a2["aid"], stats2["snap_id"]),
        )

        embed = _build_comparison_embed(
            a1["name"], stats1, growth1,
            a2["name"], stats2, growth2,
        )
        await ctx.followup.send(embed=embed)

    # ------------------------------------------------------------------ #
    # /tsymulacja — combat simulator
    # ------------------------------------------------------------------ #

    @discord.slash_command(
        name="tsymulacja",
        description="Symulacja walki — oblicz straty",
    )
    async def tsymulacja(self, ctx: discord.ApplicationContext):
        """Open combat simulation modal."""
        modal = CombatSimModal()
        await ctx.send_modal(modal)


# ------------------------------------------------------------------ #
# Combat Simulation Modal
# ------------------------------------------------------------------ #

def _fmt_num(n: float) -> str:
    """Format number with space as thousands separator."""
    if isinstance(n, float):
        n = int(n)
    return f"{n:,}".replace(",", " ")


def _build_combat_embed(result: dict, attackers: dict, defenders: dict, wall_level: int) -> discord.Embed:
    """Build Discord embed with combat simulation results."""
    if result["result"] == "att_wins":
        title = "⚔️ Zwycięstwo atakujących"
        color = COLOR_ATTACK
    elif result["result"] == "def_wins":
        title = "🛡️ Zwycięstwo obrońców"
        color = COLOR_SUCCESS
    else:
        title = "💀 Remis — obie strony zniszczone"
        color = COLOR_WARNING

    embed = discord.Embed(title="⚔️ Symulacja walki", color=color)

    # Attack power
    att_lines = [f"**Łącznie:** {_fmt_num(result['total_att'])}"]
    att_lines.append(
        f"🚶 Piechota: {_fmt_num(result['inf_att'])} | "
        f"🐴 Kawaleria: {_fmt_num(result['cav_att'])}"
    )
    embed.add_field(name="🗡️ Siła ataku", value="\n".join(att_lines), inline=False)

    # Defense power
    def_lines = []
    wall_note = f" (mur poz. {wall_level}: +{result['wall_bonus_pct']}%)" if wall_level > 0 else ""
    if wall_level > 0:
        def_lines.append(
            f"vs 🚶: {_fmt_num(result['def_power_inf'])} → "
            f"{_fmt_num(result['def_power_inf_wall'])} | "
            f"vs 🐴: {_fmt_num(result['def_power_cav'])} → "
            f"{_fmt_num(result['def_power_cav_wall'])}"
        )
    else:
        def_lines.append(
            f"vs 🚶: {_fmt_num(result['def_power_inf'])} | "
            f"vs 🐴: {_fmt_num(result['def_power_cav'])}"
        )
    att_type_label = "🐴 kawalerii" if result["att_type"] == "cav" else "🚶 piechoty"
    def_lines.append(f"Typ ataku: {att_type_label} → obrona: {_fmt_num(result['effective_def'])}")
    embed.add_field(
        name=f"🛡️ Siła obrony{wall_note}",
        value="\n".join(def_lines),
        inline=False,
    )

    # Result
    embed.add_field(
        name="📊 Wynik",
        value=(
            f"{title}\n"
            f"Straty ataku: **~{result['att_losses_pct']}%** | "
            f"Straty obrony: **~{result['def_losses_pct']}%**"
        ),
        inline=False,
    )

    # Surviving attackers
    att_surv = result["att_remaining"]
    if any(v > 0 for v in att_surv.values()):
        surv_parts = []
        for name, orig in attackers.items():
            left = att_surv.get(name, 0)
            surv_parts.append(f"{name}: **{_fmt_num(left)}**/{_fmt_num(orig)}")
        embed.add_field(
            name="🗡️ Ocalałe jednostki ataku",
            value=" | ".join(surv_parts),
            inline=False,
        )
    else:
        embed.add_field(
            name="🗡️ Ocalałe jednostki ataku",
            value="_(żadne)_",
            inline=False,
        )

    # Surviving defenders
    def_surv = result["def_remaining"]
    if any(v > 0 for v in def_surv.values()):
        surv_parts = []
        for name, orig in defenders.items():
            left = def_surv.get(name, 0)
            surv_parts.append(f"{name}: **{_fmt_num(left)}**/{_fmt_num(orig)}")
        embed.add_field(
            name="🛡️ Ocalałe jednostki obrony",
            value=" | ".join(surv_parts),
            inline=False,
        )
    else:
        embed.add_field(
            name="🛡️ Ocalałe jednostki obrony",
            value="_(żadne)_",
            inline=False,
        )

    embed.add_field(
        name="",
        value="💡 _Symulacja przybliżona. Nie uwzględnia premii morale i bonusów populacyjnych._",
        inline=False,
    )
    embed.set_footer(text=FOOTER)
    return embed


class CombatSimModal(discord.ui.Modal):
    """Modal for combat simulation input."""

    def __init__(self):
        super().__init__(title="⚔️ Symulacja walki")
        self.attackers_input = discord.ui.InputText(
            label="Atakujący (nazwa:ilość, ...)",
            placeholder="Imperians:500, EC:200, Taran:50",
            style=discord.InputTextStyle.paragraph,
            required=True,
        )
        self.defenders_input = discord.ui.InputText(
            label="Obrońcy (nazwa:ilość, ...)",
            placeholder="Falangita:800, Druid:300",
            style=discord.InputTextStyle.paragraph,
            required=True,
        )
        self.wall_input = discord.ui.InputText(
            label="Poziom muru (0-20)",
            placeholder="10",
            required=False,
            max_length=2,
        )
        self.add_item(self.attackers_input)
        self.add_item(self.defenders_input)
        self.add_item(self.wall_input)

    async def callback(self, interaction: discord.Interaction):
        # Parse wall level
        wall_level = 0
        wall_raw = self.wall_input.value.strip() if self.wall_input.value else ""
        if wall_raw:
            if not wall_raw.isdigit() or not (0 <= int(wall_raw) <= 20):
                await interaction.response.send_message(
                    "❌ Poziom muru musi być liczbą 0-20.",
                    ephemeral=True,
                )
                return
            wall_level = int(wall_raw)

        # Parse armies
        attackers, att_errors = parse_army_input(self.attackers_input.value)
        defenders, def_errors = parse_army_input(self.defenders_input.value)
        all_errors = att_errors + def_errors

        if not attackers and not defenders:
            msg = "❌ Nie podano żadnych jednostek.\n"
            if all_errors:
                msg += "\n".join(all_errors)
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if not attackers:
            msg = "❌ Brak jednostek atakujących.\n"
            if att_errors:
                msg += "\n".join(att_errors)
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if not defenders:
            msg = "❌ Brak jednostek obrońców.\n"
            if def_errors:
                msg += "\n".join(def_errors)
            await interaction.response.send_message(msg, ephemeral=True)
            return

        # Run simulation
        result = simulate_combat(attackers, defenders, wall_level)
        embed = _build_combat_embed(result, attackers, defenders, wall_level)

        # If there were some parsing errors, note them
        content = None
        if all_errors:
            content = "⚠️ Część jednostek pominięto:\n" + "\n".join(all_errors)

        await interaction.response.send_message(content=content, embed=embed)

    # ------------------------------------------------------------------ #
    # /tbezpieczne — safe-send distance calculator
    # ------------------------------------------------------------------ #

    async def _find_safe_targets(self, cx, cy, min_dist, max_dist, map_size):
        """Find villages in distance range [min_dist, max_dist] from (cx, cy).

        Returns list of dicts sorted: unoccupied first, then by distance.
        Limited to 15 results.
        """
        search_radius = int(max_dist) + 1

        def _query():
            from app.models import Snapshot, Village

            snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
            if not snap:
                return []

            rows = Village.query.filter(
                Village.snapshot_id == snap.id,
                _bbox_filter(Village.x, cx, search_radius, map_size),
                _bbox_filter(Village.y, cy, search_radius, map_size),
            ).all()

            results = []
            for v in rows:
                dist = torus_distance(cx, cy, v.x, v.y, map_size)
                if min_dist <= dist <= max_dist:
                    results.append({
                        "x": v.x, "y": v.y,
                        "name": v.name,
                        "player": v.player_name or "",
                        "alliance": v.alliance_name or "",
                        "pop": v.population,
                        "uid": v.uid,
                        "dist": round(dist, 1),
                    })
            # Unoccupied first (uid == 0), then by distance
            results.sort(key=lambda r: (r["uid"] != 0, r["dist"]))
            return results[:15]

        return await db_query(self.bot, _query)

    @discord.slash_command(
        name="tbezpieczne",
        description="Kalkulator bezpiecznego wysyłania (min. odległość)",
    )
    @discord.option(
        "czas", str,
        description="Czas nieobecności: godziny (np. 2.5) lub h:mm (np. 2:30)",
    )
    @discord.option(
        "plemie", str,
        description="Plemię jednostek",
        choices=["Rzymianie", "Germanie", "Galowie"],
    )
    @discord.option(
        "ts", int,
        description="Poziom Placu Turniejowego (0-20, domyślnie 0)",
        required=False, default=0, min_value=0, max_value=20,
    )
    @discord.option(
        "buty", float,
        description="Bonus z butów bohatera (np. 0.25 = 25%, domyślnie 0)",
        required=False, default=0.0,
    )
    @discord.option(
        "kordy", str,
        description="Twoje koordynaty (np. 76|43) — pokaże sugerowane cele",
        required=False, default=None,
    )
    async def tbezpieczne(self, ctx: discord.ApplicationContext,
                          czas: str, plemie: str, ts: int,
                          buty: float, kordy: str | None):
        hours = _parse_hours(czas)
        if hours is None or hours <= 0:
            await ctx.respond(
                "❌ Nieprawidłowy czas. Użyj formatu `2.5` (godziny) "
                "lub `2:30` (h:mm).",
                ephemeral=True,
            )
            return

        tribe_id = _TRIBE_CHOICE_MAP[plemie]
        tribe_emoji = TRIBE_EMOJI.get(tribe_id, "")
        units = UNIT_SPEEDS[tribe_id]

        await ctx.defer()

        # Calculate safe distance for each unit type
        distances = []
        for unit in units:
            dist = calc_safe_distance(
                speed=unit["speed"],
                hours_away=hours,
                ts_level=ts,
                boots_bonus=buty,
            )
            distances.append({
                "name": unit["name"],
                "type": unit["type"],
                "speed": unit["speed"],
                "dist": dist,
            })

        # Sort by distance (shortest first)
        distances.sort(key=lambda d: d["dist"])

        # Build description
        h_int = int(hours)
        m_int = int((hours - h_int) * 60)
        time_str = f"{h_int}h {m_int:02d}m" if h_int > 0 else f"{m_int}m"

        desc_parts = [f"⏱️ Czas nieobecności: **{time_str}**"]
        if ts > 0:
            desc_parts.append(f"🏟️ Plac Turniejowy: **{ts}**")
        if buty > 0:
            desc_parts.append(f"👢 Buty bohatera: **+{buty:.0%}**")
        desc = "\n".join(desc_parts)

        embed = discord.Embed(
            title=f"🛡️ Bezpieczne wysyłanie — {tribe_emoji} {plemie}",
            description=desc,
            color=COLOR_SUCCESS,
        )

        # Distance list
        lines = []
        for d in distances:
            emoji = TYPE_EMOJI.get(d["type"], "")
            lines.append(
                f"{emoji} **{d['name']}** — {d['dist']:.1f} pól "
                f"(💨 {d['speed']} pól/h)"
            )
        embed.add_field(
            name="📏 Minimalne odległości (w jedną stronę)",
            value="\n".join(lines) or "Brak danych",
            inline=False,
        )

        # Optional: find nearby villages as targets
        if kordy:
            cx, cy = parse_coords(kordy)
            if cx is not None:
                # Use the slowest unit's distance as min, fastest as max (+20% margin)
                min_dist = distances[0]["dist"]
                max_dist = distances[-1]["dist"] * 1.2
                map_size = self._map_size()
                server_url = self._server_url()

                targets = await self._find_safe_targets(
                    cx, cy, min_dist, max_dist, map_size,
                )

                if targets:
                    target_lines = []
                    for t in targets:
                        c = coords_display(server_url, t["x"], t["y"])
                        if t["uid"] == 0:
                            target_lines.append(
                                f"🏜️ {c} — niezajęta ({t['dist']} pól)"
                            )
                        else:
                            target_lines.append(
                                f"🏘️ {c} — {t['player']} "
                                f"[{t['alliance']}] pop {t['pop']} "
                                f"({t['dist']} pól)"
                            )
                    embed.add_field(
                        name="🎯 Sugerowane cele",
                        value="\n".join(target_lines),
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name="🎯 Sugerowane cele",
                        value="Brak wiosek w zakresie odległości.",
                        inline=False,
                    )
            else:
                embed.add_field(
                    name="🎯 Sugerowane cele",
                    value="⚠️ Nieprawidłowe koordynaty — pominięto.",
                    inline=False,
                )

        embed.set_footer(text=FOOTER + " | Pamiętaj o czasie powrotu!")
        await ctx.respond(embed=embed)

    # ------------------------------------------------------------------
    # /tileobrony — defense calculator
    # ------------------------------------------------------------------

    @discord.slash_command(
        name="tileobrony",
        description="Kalkulator obrony — ile wojsk potrzeba do odparcia ataku",
    )
    @discord.option(
        "atakujacy", str,
        description="Skład armii np. Imperians:500,EC:200 lub imp:500,ec:200",
    )
    @discord.option(
        "jednostka", str,
        description="Jednostka obronna np. Pretorianin, Falangita, pret",
    )
    @discord.option(
        "mur", int, description="Poziom muru (0-20)", required=False, default=0,
        min_value=0, max_value=20,
    )
    async def tileobrony(
        self, ctx: discord.ApplicationContext,
        atakujacy: str, jednostka: str, mur: int,
    ):
        await ctx.defer()

        army, errors = parse_army_input(atakujacy)
        if not army:
            await ctx.followup.send(
                "❌ Nie rozpoznano żadnych jednostek.\n"
                "💡 Format: `Imperians:500,EC:200` lub `imp:500,ec:200`",
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


def setup(bot):
    bot.add_cog(Economy(bot))
