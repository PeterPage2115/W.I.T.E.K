"""Cog alertów — wysyła powiadomienia o zmianach na mapie do Discorda."""

import json
import logging

import discord
from discord.ext import commands, tasks

from bot.bot import db_query
from bot.utils import FOOTER, COLOR_ATTACK, COLOR_WARNING, COLOR_PURPLE

logger = logging.getLogger(__name__)


class AlertsCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.check_alerts.is_running():
            self.check_alerts.start()
            logger.info("Uruchomiono pętlę alertów")

    def cog_unload(self):
        self.check_alerts.cancel()

    @tasks.loop(seconds=60)
    async def check_alerts(self):
        """Sprawdza nowe alerty i wysyła je na kanał Discord."""
        channel_id = self.bot.flask_app.config.get("DISCORD_ALERTS_CHANNEL_ID")
        if not channel_id:
            logger.debug("DISCORD_ALERTS_CHANNEL_ID nie ustawiony — pomijam alerty")
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            logger.warning("Kanał alertów (ID: %d) nie znaleziony — bot nie ma dostępu?", channel_id)
            return

        try:
            alerts_data = await db_query(self.bot, self._fetch_pending_alerts)
            if not alerts_data:
                return

            pending_count = len(alerts_data)
            logger.info("Znaleziono %d oczekujących alertów do wysłania", pending_count)

            grouped = _group_alerts(alerts_data)
            for alert_type, items in grouped.items():
                embed = _build_embed(alert_type, items)
                await channel.send(embed=embed)

            alert_ids = [a["id"] for a in alerts_data]
            await db_query(self.bot, lambda: self._mark_notified(alert_ids))
            logger.info("Wysłano %d alertów na kanał #%s", len(alerts_data), channel.name)

        except Exception:
            logger.exception("Błąd wysyłania alertów")

    def _fetch_pending_alerts(self):
        """Pobiera niewysłane alerty z bazy (uruchamiane w db_query)."""
        from app.models import Alert

        rows = (
            Alert.query
            .filter_by(notified=False)
            .order_by(Alert.created_at.asc())
            .limit(50)
            .all()
        )
        return [
            {
                "id": row.id,
                "alert_type": row.alert_type,
                "data": json.loads(row.data),
            }
            for row in rows
        ]

    def _mark_notified(self, alert_ids):
        """Oznacza alerty jako wysłane (uruchamiane w db_query)."""
        from app.models import Alert
        from app.database import db

        Alert.query.filter(Alert.id.in_(alert_ids)).update(
            {"notified": True}, synchronize_session=False
        )
        db.session.commit()


def _group_alerts(alerts_data: list[dict]) -> dict[str, list[dict]]:
    """Grupuje alerty po typie."""
    grouped: dict[str, list[dict]] = {}
    for alert in alerts_data:
        atype = alert["alert_type"]
        if atype not in grouped:
            grouped[atype] = []
        grouped[atype].append(alert["data"])
    return grouped


def _build_embed(alert_type: str, items: list[dict]) -> discord.Embed:
    """Tworzy embed Discordowy dla grupy alertów."""
    if alert_type == "pop_drop":
        return _embed_pop_drops(items)
    elif alert_type == "new_village":
        return _embed_new_villages(items)
    elif alert_type == "alliance_change":
        return _embed_alliance_changes(items)
    else:
        embed = discord.Embed(title="⚠️ Nieznany typ alertu", color=COLOR_WARNING)
        embed.set_footer(text=FOOTER)
        return embed


def _embed_pop_drops(items: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title="🔻 Spadki populacji",
        color=COLOR_ATTACK,
    )
    lines = []
    for item in items[:25]:
        name = item.get("player_name", "?")
        alliance = item.get("alliance_name", "")
        old_pop = item.get("old_pop", 0)
        new_pop = item.get("new_pop", 0)
        drop_pct = item.get("drop_pct", 0)

        alliance_str = f" ({alliance})" if alliance else ""
        lines.append(
            f"**{name}**{alliance_str} — {old_pop:,} → {new_pop:,} (-{drop_pct}%)"
        )

    embed.description = "\n".join(lines) if lines else "Brak danych"
    if len(items) > 25:
        embed.description += f"\n\n… i {len(items) - 25} więcej"
    embed.set_footer(text=FOOTER)
    return embed


def _embed_new_villages(items: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title="🏘️ Nowe wioski wrogów w okolicy",
        color=0xE67E22,  # pomarańczowy
    )
    lines = []
    for item in items[:25]:
        vname = item.get("village_name", "?")
        x = item.get("x", 0)
        y = item.get("y", 0)
        player = item.get("player_name", "?")
        alliance = item.get("alliance_name", "")
        dist = item.get("distance", 0)

        alliance_str = f" [{alliance}]" if alliance else ""
        lines.append(
            f"**{vname}** ({x}|{y}) — {player}{alliance_str} • {dist} pól od naszych"
        )

    embed.description = "\n".join(lines) if lines else "Brak danych"
    if len(items) > 25:
        embed.description += f"\n\n… i {len(items) - 25} więcej"
    embed.set_footer(text=FOOTER)
    return embed


def _embed_alliance_changes(items: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title="🔄 Zmiany w sojuszach",
        color=COLOR_PURPLE,
    )
    lines = []
    type_emoji = {"leave": "🚪", "join": "✅", "switch": "🔀"}
    for item in items[:25]:
        name = item.get("player_name", "?")
        pop = item.get("total_pop", 0)
        old_alliance = item.get("old_alliance_name", "—")
        new_alliance = item.get("new_alliance_name", "")
        change_type = item.get("change_type", "switch")

        emoji = type_emoji.get(change_type, "🔄")
        old_str = old_alliance if old_alliance else "brak"
        new_str = new_alliance if new_alliance else "brak"
        lines.append(
            f"{emoji} **{name}** (pop: {pop:,}) — {old_str} → {new_str}"
        )

    embed.description = "\n".join(lines) if lines else "Brak danych"
    if len(items) > 25:
        embed.description += f"\n\n… i {len(items) - 25} więcej"
    embed.set_footer(text=FOOTER)
    return embed


def setup(bot: discord.Bot):
    bot.add_cog(AlertsCog(bot))
