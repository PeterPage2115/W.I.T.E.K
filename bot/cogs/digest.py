"""Tygodniowy digest sojuszu — /tdigest + automatyczny post (S5.7)."""

import logging
from datetime import datetime, time, timedelta, timezone

import discord
from discord.ext import commands, tasks

from bot.bot import db_query
from bot.utils import COLOR_INFO, FOOTER

log = logging.getLogger(__name__)

# Monday = 0 in Python's weekday()
_DIGEST_WEEKDAY = 0
_DIGEST_TIME = time(hour=8, minute=0, tzinfo=timezone.utc)

# Display caps per section
_TOP_GROWERS_LIMIT = 5
_TOP_DECLINERS_LIMIT = 5
_NEW_VILLAGES_LIMIT = 10


def _fmt_pop(n: int) -> str:
    """Format population with space as thousands separator (Polish style)."""
    return f"{n:,}".replace(",", " ")


def _sign(n: int) -> str:
    return f"+{_fmt_pop(n)}" if n >= 0 else f"{_fmt_pop(n)}"


class Digest(commands.Cog):
    """Tygodniowy przegląd sojuszu."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.weekly_digest.is_running():
            self.weekly_digest.start()
            log.info("Uruchomiono pętlę tygodniowego digestu")

    def cog_unload(self):
        self.weekly_digest.cancel()

    # ------------------------------------------------------------------ #
    # Slash command
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="tdigest",
        description="Podsumowanie tygodnia sojuszu",
    )
    @discord.option(
        "dni",
        int,
        description="Ile dni wstecz (domyślnie 7)",
        required=False,
        default=7,
        min_value=1,
        max_value=30,
    )
    async def tdigest(self, ctx: discord.ApplicationContext, dni: int):
        await ctx.defer()
        data = await db_query(self.bot, lambda: _gather_digest_data(self.bot, dni))
        embed = build_digest_embed(data, dni)
        await ctx.followup.send(embed=embed)

    # ------------------------------------------------------------------ #
    # Automated weekly post
    # ------------------------------------------------------------------ #
    @tasks.loop(time=_DIGEST_TIME)
    async def weekly_digest(self):
        """Post weekly digest every Monday at 08:00 UTC."""
        now = datetime.now(timezone.utc)
        if now.weekday() != _DIGEST_WEEKDAY:
            return

        channel_id = self.bot.flask_app.config.get("DISCORD_ALERTS_CHANNEL_ID")
        if not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return

        try:
            data = await db_query(self.bot, lambda: _gather_digest_data(self.bot, 7))
            embed = build_digest_embed(data, 7)
            await channel.send(embed=embed)
            log.info("Wysłano tygodniowy digest na kanał #%s", channel.name)
        except Exception:
            log.exception("Błąd wysyłania tygodniowego digestu")

    @weekly_digest.before_loop
    async def before_weekly_digest(self):
        await self.bot.wait_until_ready()


# ------------------------------------------------------------------ #
# Data gathering (runs inside db_query — has Flask app context)
# ------------------------------------------------------------------ #

def _gather_digest_data(bot, days: int) -> dict | None:
    """Gather all digest stats for the last *days* days.

    Returns a plain dict (no SQLAlchemy objects) or None if no data.
    """
    from app.models import AttackReport, Snapshot, Village

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    latest_snapshot = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
    if not latest_snapshot:
        return None

    # Pick baseline: latest snapshot before cutoff; else earliest after cutoff
    oldest_snapshot = (
        Snapshot.query
        .filter(Snapshot.fetched_at <= cutoff)
        .order_by(Snapshot.fetched_at.desc())
        .first()
    )
    if oldest_snapshot is None:
        oldest_snapshot = (
            Snapshot.query
            .filter(Snapshot.fetched_at >= cutoff)
            .order_by(Snapshot.fetched_at.asc())
            .first()
        )

    if oldest_snapshot is None:
        return None

    our_alliances = bot.flask_app.config.get("TRAVIAN_OUR_ALLIANCES", [])
    if not our_alliances:
        return None

    single_snapshot = oldest_snapshot.id == latest_snapshot.id

    # Sanity check: skip snapshots with suspiciously low village counts
    if not single_snapshot:
        if (oldest_snapshot.village_count and latest_snapshot.village_count
                and latest_snapshot.village_count > 0):
            ratio = oldest_snapshot.village_count / latest_snapshot.village_count
            if ratio < 0.5 or ratio > 2.0:
                # Likely a bad snapshot — fall back to single-snapshot mode
                single_snapshot = True

    # --- Query villages for our alliances ----------------------------- #
    old_villages = _get_alliance_villages(oldest_snapshot.id, our_alliances)
    new_villages = _get_alliance_villages(latest_snapshot.id, our_alliances)

    # --- Alliance name(s) -------------------------------------------- #
    alliance_names = sorted({v["alliance_name"] for v in new_villages if v["alliance_name"]})
    if not alliance_names:
        alliance_names = sorted({v["alliance_name"] for v in old_villages if v["alliance_name"]})
    alliance_name = " + ".join(alliance_names) if alliance_names else "Nasz sojusz"

    # --- Current state ------------------------------------------------ #
    pop_new = sum(v["population"] for v in new_villages)
    village_count_new = len(new_villages)
    member_uids_new = {v["uid"] for v in new_villages if v["uid"] and v["uid"] > 0}
    member_count_new = len(member_uids_new)

    if single_snapshot:
        return {
            "single_snapshot": True,
            "alliance_name": alliance_name,
            "snapshot_date": latest_snapshot.fetched_at.strftime("%d.%m.%Y"),
            "pop_new": pop_new,
            "village_count_new": village_count_new,
            "member_count_new": member_count_new,
        }

    # --- Comparison --------------------------------------------------- #
    pop_old = sum(v["population"] for v in old_villages)
    village_count_old = len(old_villages)
    member_uids_old = {v["uid"] for v in old_villages if v["uid"] and v["uid"] > 0}
    member_count_old = len(member_uids_old)

    pop_change = pop_new - pop_old
    pop_change_pct = round((pop_change / pop_old * 100), 1) if pop_old > 0 else 0.0

    # --- Per-player population ---------------------------------------- #
    player_pop_old = _player_populations(old_villages)
    player_pop_new = _player_populations(new_villages)

    # Player name lookup (prefer newer names)
    player_names: dict[int, str] = {}
    for v in old_villages:
        if v["uid"] and v["uid"] > 0:
            player_names[v["uid"]] = v["player_name"]
    for v in new_villages:
        if v["uid"] and v["uid"] > 0:
            player_names[v["uid"]] = v["player_name"]

    # Top growers / decliners (only players in both snapshots)
    all_uids = set(player_pop_old.keys()) | set(player_pop_new.keys())
    player_changes = []
    for uid in all_uids:
        if uid <= 0:
            continue
        old_p = player_pop_old.get(uid, 0)
        new_p = player_pop_new.get(uid, 0)
        change = new_p - old_p
        name = player_names.get(uid, f"UID {uid}")
        player_changes.append((name, change))

    player_changes.sort(key=lambda x: x[1], reverse=True)
    top_growers = [(n, c) for n, c in player_changes if c > 0][:_TOP_GROWERS_LIMIT]
    top_decliners = [(n, c) for n, c in player_changes if c < 0]
    top_decliners.sort(key=lambda x: x[1])
    top_decliners = top_decliners[:_TOP_DECLINERS_LIMIT]

    # --- Member changes ----------------------------------------------- #
    new_member_uids = member_uids_new - member_uids_old
    lost_member_uids = member_uids_old - member_uids_new

    new_members = [player_names.get(uid, f"UID {uid}") for uid in sorted(new_member_uids)]
    lost_members = [player_names.get(uid, f"UID {uid}") for uid in sorted(lost_member_uids)]

    # --- Attack reports ----------------------------------------------- #
    attacks_total = (
        AttackReport.query
        .filter(AttackReport.created_at >= cutoff)
        .count()
    )
    attacks_resolved = (
        AttackReport.query
        .filter(AttackReport.created_at >= cutoff)
        .filter(AttackReport.status == "resolved")
        .count()
    )

    # --- New villages (map_id in new but not in old for our alliances) - #
    old_map_ids = {v["map_id"] for v in old_villages}
    new_village_entries = []
    for v in new_villages:
        if v["map_id"] not in old_map_ids:
            new_village_entries.append({
                "player_name": v["player_name"],
                "village_name": v["name"],
                "x": v["x"],
                "y": v["y"],
            })

    return {
        "single_snapshot": False,
        "period_days": days,
        "old_date": oldest_snapshot.fetched_at.strftime("%d.%m.%Y"),
        "new_date": latest_snapshot.fetched_at.strftime("%d.%m.%Y"),
        "alliance_name": alliance_name,
        "pop_old": pop_old,
        "pop_new": pop_new,
        "pop_change": pop_change,
        "pop_change_pct": pop_change_pct,
        "village_count_old": village_count_old,
        "village_count_new": village_count_new,
        "member_count_old": member_count_old,
        "member_count_new": member_count_new,
        "top_growers": top_growers,
        "top_decliners": top_decliners,
        "new_members": new_members,
        "lost_members": lost_members,
        "attacks_total": attacks_total,
        "attacks_resolved": attacks_resolved,
        "new_villages": new_village_entries[:_NEW_VILLAGES_LIMIT],
        "new_villages_total": len(new_village_entries),
    }


def _get_alliance_villages(snapshot_id: int, alliance_ids: list[int]) -> list[dict]:
    """Get villages for given alliances in a snapshot as plain dicts."""
    from app.models import Village

    rows = (
        Village.query
        .filter(Village.snapshot_id == snapshot_id)
        .filter(Village.aid.in_(alliance_ids))
        .filter(Village.uid > 0)
        .all()
    )
    return [
        {
            "map_id": v.map_id,
            "x": v.x,
            "y": v.y,
            "vid": v.vid,
            "name": v.name,
            "uid": v.uid,
            "player_name": v.player_name,
            "aid": v.aid,
            "alliance_name": v.alliance_name,
            "population": v.population or 0,
        }
        for v in rows
    ]


def _player_populations(villages: list[dict]) -> dict[int, int]:
    """Sum population per player uid."""
    pops: dict[int, int] = {}
    for v in villages:
        uid = v["uid"]
        if uid and uid > 0:
            pops[uid] = pops.get(uid, 0) + (v["population"] or 0)
    return pops


# ------------------------------------------------------------------ #
# Embed builder (pure function — no DB access)
# ------------------------------------------------------------------ #

def build_digest_embed(data: dict | None, days: int) -> discord.Embed:
    """Build the digest Discord embed from gathered data."""
    if data is None:
        embed = discord.Embed(
            title="📊 Podsumowanie — brak danych",
            description=(
                "❌ Brak snapshotów w bazie danych.\n"
                "Poczekaj na pierwszą synchronizację map.sql."
            ),
            color=COLOR_INFO,
        )
        embed.set_footer(text=FOOTER)
        return embed

    alliance_name = data["alliance_name"]

    # Single snapshot — show current state only
    if data.get("single_snapshot"):
        embed = discord.Embed(
            title=f"📊 Stan sojuszu — {alliance_name}",
            description=(
                f"⚠️ Dostępny tylko jeden snapshot ({data['snapshot_date']}).\n"
                "Porównanie będzie możliwe po kolejnej synchronizacji.\n\n"
                f"📈 Populacja: **{_fmt_pop(data['pop_new'])}**\n"
                f"🏘️ Wioski: **{data['village_count_new']}**\n"
                f"👥 Członkowie: **{data['member_count_new']}**"
            ),
            color=COLOR_INFO,
        )
        embed.set_footer(text=FOOTER)
        return embed

    # Full digest
    title = f"📊 Podsumowanie tygodnia — {alliance_name}"
    lines: list[str] = []

    # Period
    lines.append(f"📅 **Okres:** {data['old_date']} — {data['new_date']}")
    lines.append("")

    # Population
    pop_arrow = "📈" if data["pop_change"] >= 0 else "📉"
    pct_str = f"+{data['pop_change_pct']}%" if data["pop_change_pct"] >= 0 else f"{data['pop_change_pct']}%"
    lines.append(
        f"{pop_arrow} **Populacja:** {_fmt_pop(data['pop_old'])} → "
        f"{_fmt_pop(data['pop_new'])} ({_sign(data['pop_change'])}, {pct_str})"
    )

    # Villages
    vc_change = data["village_count_new"] - data["village_count_old"]
    vc_str = f" ({_sign(vc_change)})" if vc_change != 0 else ""
    lines.append(
        f"🏘️ **Wioski:** {data['village_count_old']} → {data['village_count_new']}{vc_str}"
    )

    # Members
    mc_change = data["member_count_new"] - data["member_count_old"]
    mc_str = f" ({_sign(mc_change)})" if mc_change != 0 else ""
    lines.append(
        f"👥 **Członkowie:** {data['member_count_old']} → {data['member_count_new']}{mc_str}"
    )

    # Top growers
    if data["top_growers"]:
        lines.append("")
        lines.append("🏆 **Największy wzrost:**")
        for i, (name, change) in enumerate(data["top_growers"], 1):
            lines.append(f"{i}. {name} — +{_fmt_pop(change)} pop")

    # Top decliners
    if data["top_decliners"]:
        lines.append("")
        lines.append("📉 **Spadki:**")
        for i, (name, change) in enumerate(data["top_decliners"], 1):
            lines.append(f"{i}. {name} — {_fmt_pop(change)} pop")

    # New members
    if data["new_members"]:
        lines.append("")
        names = ", ".join(data["new_members"])
        lines.append(f"👋 **Nowi członkowie:** {names}")

    # Lost members
    if data["lost_members"]:
        if not data["new_members"]:
            lines.append("")
        lines.append(f"🚪 **Odeszli:** {', '.join(data['lost_members'])}")

    # Attacks
    if data["attacks_total"] > 0:
        lines.append("")
        lines.append(
            f"⚔️ **Ataki:** {data['attacks_total']} zgłoszonych, "
            f"{data['attacks_resolved']} rozwiązanych"
        )

    # New villages
    if data["new_villages"]:
        lines.append("")
        village_parts = []
        for nv in data["new_villages"]:
            village_parts.append(f"{nv['player_name']} ({nv['x']}|{nv['y']})")
        lines.append(f"🏘️ **Nowe wioski:** {', '.join(village_parts)}")
        if data["new_villages_total"] > _NEW_VILLAGES_LIMIT:
            lines.append(f"… i {data['new_villages_total'] - _NEW_VILLAGES_LIMIT} więcej")

    embed = discord.Embed(
        title=title,
        description="\n".join(lines),
        color=COLOR_INFO,
    )
    embed.set_footer(text=FOOTER)
    return embed


def setup(bot: discord.Bot):
    bot.add_cog(Digest(bot))
