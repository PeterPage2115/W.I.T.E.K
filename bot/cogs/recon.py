"""Komendy rozpoznania — analiza mapy i graczy."""

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from sqlalchemy import or_

from bot.bot import db_query
from bot.utils import (
    COLOR_WARNING,
    FOOTER,
    coords_display,
    parse_coords,
    torus_distance,
)

log = logging.getLogger(__name__)

MAX_RESULTS = 20
MAX_VILLAGES_SHOWN = 3


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


def _bbox_query(snapshot_id, center_x, center_y, radius, map_size):
    """Fetch villages within bounding box from a snapshot (SQL prefilter)."""
    from app.models import Village

    return (
        Village.query
        .filter(
            Village.snapshot_id == snapshot_id,
            Village.uid > 0,
            _bbox_filter(Village.x, center_x, radius, map_size),
            _bbox_filter(Village.y, center_y, radius, map_size),
        )
        .all()
    )


def _find_inactive_players(center_x, center_y, radius, min_pop, dni,
                           our_alliances, server_url, map_size):
    """Find players with zero pop growth near center. Returns list of dicts or None."""
    from app.models import Snapshot

    cutoff = datetime.now(timezone.utc) - timedelta(days=dni)

    snapshots = (
        Snapshot.query
        .filter(Snapshot.fetched_at >= cutoff)
        .order_by(Snapshot.fetched_at)
        .all()
    )
    if len(snapshots) < 2:
        return None

    earliest = snapshots[0]
    latest = snapshots[-1]

    our_aids = {int(a) for a in our_alliances if a is not None}

    # Step 1: Define cohort from LATEST snapshot (bounding-box prefilter)
    latest_bbox = _bbox_query(latest.id, center_x, center_y, radius, map_size)

    latest_players = {}
    for v in latest_bbox:
        dist = torus_distance(center_x, center_y, v.x, v.y, map_size)
        if dist > radius:
            continue
        if int(v.aid or 0) in our_aids:
            continue

        if v.uid not in latest_players:
            latest_players[v.uid] = {
                "uid": v.uid,
                "name": v.player_name,
                "pop": 0,
                "village_count": 0,
                "villages": [],
                "distance": dist,
            }

        player = latest_players[v.uid]
        player["pop"] += v.population
        player["village_count"] += 1
        player["villages"].append({
            "name": v.name,
            "x": v.x,
            "y": v.y,
            "pop": v.population,
            "dist": dist,
        })
        if dist < player["distance"]:
            player["distance"] = dist

    if not latest_players:
        return []

    # Step 2: Look up the SAME cohort UIDs in earliest snapshot
    cohort_uids = set(latest_players.keys())
    earliest_bbox = _bbox_query(earliest.id, center_x, center_y, radius, map_size)

    earliest_data = {}
    for v in earliest_bbox:
        if v.uid not in cohort_uids:
            continue
        dist = torus_distance(center_x, center_y, v.x, v.y, map_size)
        if dist > radius:
            continue
        if v.uid not in earliest_data:
            earliest_data[v.uid] = {"pop": 0, "village_count": 0}
        earliest_data[v.uid]["pop"] += v.population
        earliest_data[v.uid]["village_count"] += 1

    # Step 3: Inactive = same total_pop AND same village_count
    inactive = []
    for uid, player in latest_players.items():
        if player["pop"] < min_pop:
            continue
        if uid not in earliest_data:
            continue
        early = earliest_data[uid]
        if (player["pop"] == early["pop"]
                and player["village_count"] == early["village_count"]):
            player["villages"].sort(key=lambda v: v["dist"])
            inactive.append(player)

    inactive.sort(key=lambda p: p["distance"])
    return inactive


class Recon(commands.Cog):
    """Komendy rozpoznania — analiza mapy i graczy."""

    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(
        name="tnieaktywni",
        description="Szukaj nieaktywnych graczy w okolicy",
    )
    @discord.option(
        "kordy", str,
        description="Środek szukania np. 76|43",
        required=True,
    )
    @discord.option(
        "radius", int,
        description="Promień szukania w polach",
        required=True, min_value=5, max_value=100,
    )
    @discord.option(
        "min_pop", int,
        description="Minimalna populacja gracza (domyślnie 50)",
        required=False, default=50,
    )
    @discord.option(
        "dni", int,
        description="Ile dni bez wzrostu (domyślnie 3)",
        required=False, default=3, min_value=1, max_value=30,
    )
    async def tnieaktywni(self, ctx: discord.ApplicationContext,
                          kordy: str, radius: int,
                          min_pop: int = 50, dni: int = 3):
        cx, cy = parse_coords(kordy)
        if cx is None:
            await ctx.respond(
                "❌ Nieprawidłowe koordynaty. Użyj formatu np. `76|43`",
                ephemeral=True,
            )
            return

        await ctx.defer()

        cfg = self.bot.flask_app.config
        our_alliances = cfg.get("TRAVIAN_OUR_ALLIANCES", [])
        server_url = cfg.get("TRAVIAN_SERVER_URL", "")
        map_size = cfg.get("TRAVIAN_MAP_SIZE", 401)

        result = await db_query(
            self.bot,
            lambda: _find_inactive_players(
                cx, cy, radius, min_pop, dni,
                our_alliances, server_url, map_size,
            ),
        )

        if result is None:
            await ctx.followup.send(
                "💡 Za mało danych — potrzeba co najmniej 2 snapshotów "
                f"z ostatnich {dni} dni.",
            )
            return

        if not result:
            await ctx.followup.send(
                f"✅ Brak nieaktywnych graczy w promieniu {radius} pól "
                f"od ({cx}|{cy}) z populacją ≥ {min_pop}.",
            )
            return

        # Build embed
        embed = discord.Embed(
            title=f"💤 Nieaktywni gracze w okolicy ({cx}|{cy}), r={radius}",
            color=COLOR_WARNING,
        )

        shown = result[:MAX_RESULTS]
        lines = []
        for i, player in enumerate(shown, 1):
            village_count = len(player["villages"])
            dist = player["distance"]

            # Village list (max 3)
            village_parts = []
            for v in player["villages"][:MAX_VILLAGES_SHOWN]:
                village_parts.append(
                    f"{v['name']} {coords_display(server_url, v['x'], v['y'])}"
                )
            villages_str = ", ".join(village_parts)
            extra = village_count - MAX_VILLAGES_SHOWN
            if extra > 0:
                villages_str += f" ...+{extra} więcej"

            lines.append(
                f"**{i}.** {player['name']} — {player['pop']:,} pop "
                f"({village_count} {'wioska' if village_count == 1 else 'wioski' if 2 <= village_count <= 4 else 'wiosek'}) "
                f"• 📏 {dist:.1f} pól\n"
                f"  ↳ {villages_str}"
            )

        # Discord embed field limit is 1024 chars — split if needed
        description = "\n\n".join(lines)
        if len(description) <= 4096:
            embed.description = description
        else:
            # Truncate to fit
            truncated = []
            total_len = 0
            for line in lines:
                if total_len + len(line) + 2 > 4000:
                    truncated.append("*...lista obcięta*")
                    break
                truncated.append(line)
                total_len += len(line) + 2
            embed.description = "\n\n".join(truncated)

        total_found = len(result)
        footer_text = (
            f"📊 Znaleziono {total_found} nieaktywnych graczy "
            f"(min. {dni} dni bez wzrostu)"
        )
        if total_found > MAX_RESULTS:
            footer_text += f" — pokazano {MAX_RESULTS}"
        embed.set_footer(text=f"{footer_text}\n{FOOTER}")

        await ctx.followup.send(embed=embed)


def setup(bot):
    bot.add_cog(Recon(bot))
