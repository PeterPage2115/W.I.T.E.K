"""Czuwanie nocne — /tczuwanie.

Powiadamia graczy DM-em o nowych atakach na wioski sojuszu
w wybranym przedziale czasowym (np. 22:00–06:00).
"""

import logging
import re
from datetime import datetime, time, timezone

import discord
from discord.ext import commands, tasks

from bot.bot import db_query
from bot.utils import COLOR_ATTACK, COLOR_INFO, FOOTER

logger = logging.getLogger(__name__)

MAX_DMS_PER_SESSION = 5
TIME_RANGE_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$")


def _in_time_window(now_utc: datetime, start_h: int, start_m: int,
                    end_h: int, end_m: int) -> bool:
    """Check if *now_utc* falls within the given hour:minute window.

    Handles overnight ranges (e.g. 22:00-06:00).
    """
    current = now_utc.time()
    start = time(start_h, start_m)
    end = time(end_h, end_m)
    if start <= end:
        return start <= current < end
    # overnight window
    return current >= start or current < end


def _build_attack_embed(attack: dict) -> discord.Embed:
    embed = discord.Embed(
        title="🌙 Czuwanie Nocne — Nowy Atak!",
        color=COLOR_ATTACK,
    )
    embed.add_field(
        name="⚔️ Atakujący",
        value=attack.get("attacker_name", "Nieznany"),
        inline=True,
    )
    embed.add_field(
        name="🛡️ Obrońca",
        value=attack.get("defender_name", "Nieznany"),
        inline=True,
    )
    coords = f"({attack.get('defender_x', '?')}|{attack.get('defender_y', '?')})"
    embed.add_field(name="📍 Koordynaty", value=coords, inline=True)
    embed.add_field(
        name="🕐 Czas ataku",
        value=attack.get("attack_time", "—"),
        inline=True,
    )
    embed.set_footer(text=FOOTER)
    return embed


class NightWatchCog(commands.Cog):
    """Czuwanie nocne — powiadomienia DM o atakach w nocy."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.nightwatch_loop.is_running():
            self.nightwatch_loop.start()
            logger.info("Uruchomiono pętlę czuwania nocnego")

    def cog_unload(self):
        self.nightwatch_loop.cancel()

    # ------------------------------------------------------------------ #
    # /tczuwanie
    # ------------------------------------------------------------------ #

    @discord.slash_command(
        name="tczuwanie",
        description="Zarządzaj czuwaniem nocnym — alerty DM o atakach",
    )
    @discord.option(
        "akcja",
        str,
        description="Włącz/wyłącz/status czuwania",
        choices=["wlacz", "wylacz", "status"],
    )
    @discord.option(
        "godziny",
        str,
        description="Przedział czasowy UTC, np. 22:00-06:00",
        required=False,
        default=None,
    )
    async def tczuwanie(
        self,
        ctx: discord.ApplicationContext,
        akcja: str,
        godziny: str | None,
    ):
        await ctx.defer(ephemeral=True)

        # Parse time range when enabling
        start_h, start_m, end_h, end_m = 22, 0, 6, 0
        if akcja == "wlacz" and godziny:
            match = TIME_RANGE_RE.match(godziny.strip())
            if not match:
                await ctx.followup.send(
                    "❌ Nieprawidłowy format godzin. Użyj np. `22:00-06:00`.",
                    ephemeral=True,
                )
                return
            start_h, start_m = int(match.group(1)), int(match.group(2))
            end_h, end_m = int(match.group(3)), int(match.group(4))
            if start_h > 23 or start_m > 59 or end_h > 23 or end_m > 59:
                await ctx.followup.send(
                    "❌ Godziny muszą być w zakresie 0-23, minuty 0-59.",
                    ephemeral=True,
                )
                return

        discord_id = ctx.author.id

        def _handle():
            from app.database import db
            from app.models import NightWatchSetting

            setting = NightWatchSetting.query.filter_by(
                discord_id=discord_id
            ).first()

            if akcja == "wlacz":
                if not setting:
                    setting = NightWatchSetting(
                        discord_id=discord_id,
                        enabled=True,
                        start_hour=start_h,
                        start_minute=start_m,
                        end_hour=end_h,
                        end_minute=end_m,
                        dm_count=0,
                        session_date=None,
                    )
                    db.session.add(setting)
                else:
                    setting.enabled = True
                    setting.start_hour = start_h
                    setting.start_minute = start_m
                    setting.end_hour = end_h
                    setting.end_minute = end_m
                    setting.dm_count = 0
                    setting.session_date = None
                db.session.commit()
                return "enabled", {
                    "start": f"{start_h:02d}:{start_m:02d}",
                    "end": f"{end_h:02d}:{end_m:02d}",
                }

            elif akcja == "wylacz":
                if setting:
                    setting.enabled = False
                    db.session.commit()
                return "disabled", None

            else:  # status
                if not setting:
                    return "no_settings", None
                return "status", {
                    "enabled": setting.enabled,
                    "start": f"{setting.start_hour:02d}:{setting.start_minute:02d}",
                    "end": f"{setting.end_hour:02d}:{setting.end_minute:02d}",
                    "dm_count": setting.dm_count,
                }

        status, data = await db_query(self.bot, _handle)

        if status == "enabled":
            embed = discord.Embed(
                title="🌙 Czuwanie nocne włączone",
                description=(
                    f"Będziesz otrzymywać powiadomienia DM o atakach\n"
                    f"w godzinach **{data['start']} – {data['end']}** (UTC).\n"
                    f"Limit: {MAX_DMS_PER_SESSION} DM-ów na sesję."
                ),
                color=COLOR_INFO,
            )
            embed.set_footer(text=FOOTER)
            await ctx.followup.send(embed=embed, ephemeral=True)

        elif status == "disabled":
            embed = discord.Embed(
                title="🌙 Czuwanie nocne wyłączone",
                description="Nie będziesz otrzymywać nocnych powiadomień.",
                color=COLOR_INFO,
            )
            embed.set_footer(text=FOOTER)
            await ctx.followup.send(embed=embed, ephemeral=True)

        elif status == "no_settings":
            await ctx.followup.send(
                "💡 Czuwanie nocne nie jest skonfigurowane. "
                "Użyj `/tczuwanie wlacz 22:00-06:00` aby włączyć.",
                ephemeral=True,
            )

        elif status == "status":
            state = "✅ Aktywne" if data["enabled"] else "❌ Wyłączone"
            embed = discord.Embed(
                title="🌙 Status czuwania nocnego",
                color=COLOR_INFO,
            )
            embed.add_field(name="Stan", value=state, inline=True)
            embed.add_field(
                name="Godziny (UTC)",
                value=f"{data['start']} – {data['end']}",
                inline=True,
            )
            embed.add_field(
                name="DM-y w sesji",
                value=f"{data['dm_count']} / {MAX_DMS_PER_SESSION}",
                inline=True,
            )
            embed.set_footer(text=FOOTER)
            await ctx.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------ #
    # Background loop
    # ------------------------------------------------------------------ #

    @tasks.loop(minutes=2)
    async def nightwatch_loop(self):
        """Check for new attacks and DM users with active night watch."""
        try:
            now_utc = datetime.now(timezone.utc)
            watchers = await db_query(self.bot, lambda: self._get_active_watchers(now_utc))

            if not watchers:
                return

            new_attacks = await db_query(self.bot, lambda: self._get_recent_attacks(now_utc))
            if not new_attacks:
                return

            for watcher in watchers:
                if watcher["dm_count"] >= MAX_DMS_PER_SESSION:
                    continue

                user = self.bot.get_user(watcher["discord_id"])
                if user is None:
                    try:
                        user = await self.bot.fetch_user(watcher["discord_id"])
                    except discord.NotFound:
                        continue

                sent = 0
                for attack in new_attacks:
                    if watcher["dm_count"] + sent >= MAX_DMS_PER_SESSION:
                        break
                    embed = _build_attack_embed(attack)
                    try:
                        await user.send(embed=embed)
                        sent += 1
                    except discord.Forbidden:
                        logger.warning(
                            "Nie można wysłać DM do %s — DM wyłączone",
                            watcher["discord_id"],
                        )
                        break

                if sent > 0:
                    await db_query(
                        self.bot,
                        lambda did=watcher["discord_id"], s=sent: self._increment_dm_count(did, s),
                    )
                    logger.info(
                        "Czuwanie nocne: wysłano %d DM do %s", sent, watcher["discord_id"]
                    )

        except Exception:
            logger.exception("Błąd pętli czuwania nocnego")

    def _get_active_watchers(self, now_utc: datetime) -> list[dict]:
        """Return users whose night watch window covers *now_utc*."""
        from app.models import NightWatchSetting

        today_str = now_utc.strftime("%Y-%m-%d")
        rows = NightWatchSetting.query.filter_by(enabled=True).all()
        result = []
        for r in rows:
            if not _in_time_window(now_utc, r.start_hour, r.start_minute,
                                   r.end_hour, r.end_minute):
                continue
            # Reset DM counter for new session day
            session_date = r.session_date
            dm_count = r.dm_count or 0
            if session_date != today_str:
                dm_count = 0
            result.append({
                "discord_id": r.discord_id,
                "dm_count": dm_count,
                "session_date": today_str,
            })
        return result

    def _get_recent_attacks(self, now_utc: datetime) -> list[dict]:
        """Return unresolved attacks created in the last 5 minutes."""
        from app.models import AttackReport
        from datetime import timedelta

        cutoff = now_utc - timedelta(minutes=5)
        rows = (
            AttackReport.query
            .filter(AttackReport.status != "resolved")
            .filter(AttackReport.created_at >= cutoff)
            .order_by(AttackReport.created_at.desc())
            .limit(10)
            .all()
        )
        return [
            {
                "attacker_name": r.attacker_name or "Nieznany",
                "defender_name": r.defender_name or "Nieznany",
                "defender_x": r.defender_x,
                "defender_y": r.defender_y,
                "attack_time": r.attack_time or "—",
            }
            for r in rows
        ]

    def _increment_dm_count(self, discord_id: int, sent: int):
        from app.database import db
        from app.models import NightWatchSetting
        from datetime import datetime, timezone

        setting = NightWatchSetting.query.filter_by(discord_id=discord_id).first()
        if setting:
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if setting.session_date != today_str:
                setting.dm_count = sent
                setting.session_date = today_str
            else:
                setting.dm_count = (setting.dm_count or 0) + sent
            setting.last_checked_at = datetime.now(timezone.utc)
            db.session.commit()


def setup(bot: discord.Bot):
    bot.add_cog(NightWatchCog(bot))
