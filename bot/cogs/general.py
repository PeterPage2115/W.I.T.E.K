"""Ogólne komendy WITEK — /thelp, /tinfo, /tstats."""

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from bot.bot import db_query
from bot.utils import COLOR_GOLD, COLOR_MAIN, FOOTER

log = logging.getLogger(__name__)


class General(commands.Cog):
    """Ogólne komendy informacyjne."""

    def __init__(self, bot):
        self.bot = bot
        self.started_at = datetime.now(timezone.utc)

    @discord.slash_command(name="thelp", description="Wyświetla listę komend WITEK")
    async def thelp(self, ctx: discord.ApplicationContext):
        embed = discord.Embed(
            title="📜 Komendy WITEK",
            description=(
                "Wirtualny Informator Taktyczno-Ekonomiczny Koalicji\n"
                "Poniżej znajdziesz dostępne komendy:"
            ),
            color=COLOR_MAIN,
        )
        embed.add_field(
            name="📋 Ogólne",
            value=(
                "`/thelp` — Ta lista komend\n"
                "`/tinfo` — Informacje o bocie\n"
                "`/tstats` — Statystyki serwera"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔗 Tożsamość",
            value=(
                "`/tlink <gracz>` — Powiąż konto z graczem Travian\n"
                "`/tunlink` — Usuń powiązanie\n"
                "`/twhoami` — Pokaż powiązany profil"
            ),
            inline=False,
        )
        embed.add_field(
            name="⚔️ Ataki",
            value=(
                "`/tatak` — Zgłoś atak na wioskę\n"
                "`/tdodaj` — Dodaj atak do istniejącego wątku\n"
                "`/tataki` — Lista aktywnych ataków\n"
                "`/trozwiaz` — Zamknij zgłoszenie"
            ),
            inline=False,
        )
        embed.add_field(
            name="🛡️ Obrona i Wojska",
            value=(
                "`/traport` — Wklej raport bitewny (modal)\n"
                "`/traport_reczny` — Ręczny raport (telefon)\n"
                "`/traporty` — Lista raportów bitewnych\n"
                "`/tdef` — Kto może wysłać def? (ETA wiosek sojuszu)\n"
                "`/twojska` — Zarejestruj wojska w wiosce\n"
                "`/twsparcie` — Zarejestruj wysłane wsparcie\n"
                "`/tstan` — Stan obrony wioski (garnizon + wsparcie)"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔍 Rozpoznanie",
            value=(
                "`/tnieaktywni` — Szukaj nieaktywnych graczy w okolicy"
            ),
            inline=False,
        )
        embed.add_field(
            name="💰 Ekonomia",
            value=(
                "`/tcropper` — Znajdź croppery (9c/15c) w okolicy\n"
                "`/tszukaj` — Szukaj wiosek (po graczu, sojuszu, populacji)\n"
                "`/tporownaj` — Porównaj dwa sojusze\n"
                "`/tsymulacja` — Symulacja walki (kalkulator strat)\n"
                "⚔️ `/tbezpieczne` — Kalkulator bezpiecznego wysyłania (min. odległość)"
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 Analityka",
            value=(
                "`/tdigest [dni]` — Podsumowanie tygodnia sojuszu"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔔 Monitor",
            value=(
                "`/tmonitor <wlacz|wylacz|status>` — Osobisty monitoring wiosek (DM)\n"
                "`/tmonitor_ustawienia` — Zmień progi alertów"
            ),
            inline=False,
        )
        embed.set_footer(text=FOOTER)
        await ctx.respond(embed=embed)

    @discord.slash_command(name="tinfo", description="Informacje o bocie WITEK")
    async def tinfo(self, ctx: discord.ApplicationContext):
        uptime = datetime.now(timezone.utc) - self.started_at
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)

        def _get_last_sync():
            from app.models import Snapshot
            snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
            return snap.fetched_at.strftime("%Y-%m-%d %H:%M UTC") if snap else "brak danych"

        last_sync = await db_query(self.bot, _get_last_sync)

        embed = discord.Embed(title="🤖 WITEK — Informacje", color=COLOR_GOLD)
        embed.add_field(name="Wersja", value="1.0.0", inline=True)
        embed.add_field(name="Uptime", value=f"{hours}h {minutes}m", inline=True)
        embed.add_field(name="Serwery", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Ostatnia synchronizacja", value=last_sync, inline=False)
        embed.set_footer(text=FOOTER)
        await ctx.respond(embed=embed)

    @discord.slash_command(name="tstats", description="Szybkie statystyki serwera Travian")
    async def tstats(self, ctx: discord.ApplicationContext):
        def _get_stats():
            from app.models import Alliance, Player, Snapshot

            snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
            total_players = Player.query.count()
            total_alliances = Alliance.query.count()
            total_villages = snap.village_count if snap else 0
            snap_date = snap.fetched_at.strftime("%Y-%m-%d %H:%M UTC") if snap else None

            top_alliances = (
                Alliance.query.order_by(Alliance.total_pop.desc()).limit(5).all()
            )
            top_list = [
                (a.name, a.total_pop, a.member_count) for a in top_alliances
            ]
            return total_players, total_alliances, total_villages, snap_date, top_list

        total_players, total_alliances, total_villages, snap_date, top_list = (
            await db_query(self.bot, _get_stats)
        )

        embed = discord.Embed(title="📊 Statystyki serwera", color=COLOR_MAIN)
        embed.add_field(name="Gracze", value=str(total_players), inline=True)
        embed.add_field(name="Wioski", value=str(total_villages), inline=True)
        embed.add_field(name="Sojusze", value=str(total_alliances), inline=True)

        if top_list:
            lines = []
            for i, (name, pop, members) in enumerate(top_list, 1):
                lines.append(f"**{i}.** {name} — {pop:,} pop ({members} graczy)")
            embed.add_field(
                name="🏆 Top 5 sojuszy", value="\n".join(lines), inline=False,
            )

        footer = FOOTER
        if snap_date:
            footer += f" | Dane z {snap_date}"
        embed.set_footer(text=footer)
        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(General(bot))
