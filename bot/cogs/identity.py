"""Tożsamość — powiązanie Discord ↔ Travian (/tlink, /tunlink, /twhoami).

All DB access goes through db_query() to avoid blocking the event loop.
"""

import logging

import discord
from discord.ext import commands

from bot.bot import db_query
from bot.utils import COLOR_GOLD, COLOR_MAIN, FOOTER, TRIBE_EMOJI, TRIBE_ICONS, TRIBE_NAMES

log = logging.getLogger(__name__)


class Identity(commands.Cog):
    """Powiązanie konta Discord z graczem Travian."""

    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(
        name="tlink", description="Powiąż swoje konto Discord z graczem Travian"
    )
    @discord.option("player_name", str, description="Nazwa gracza w Travian", required=True)
    async def tlink(self, ctx: discord.ApplicationContext, player_name: str):
        await ctx.defer(ephemeral=True)

        def _do_link():
            from app.database import db
            from app.models import Player, User

            def _player_info(p):
                """Convert Player model to plain dict (avoids detached session)."""
                return {
                    "name": p.name, "uid": p.uid, "tid": p.tid,
                    "alliance": p.alliance_name or "—",
                    "pop": p.total_pop or 0, "villages": p.village_count or 0,
                }

            # Exact match
            exact = Player.query.filter(Player.name == player_name).all()
            if len(exact) == 1:
                player = exact[0]
                # Check if someone else already linked this player
                other = User.query.filter_by(travian_uid=player.uid).first()
                if other and other.discord_id != ctx.author.id:
                    return "taken", _player_info(player), None

                existing = User.query.filter_by(discord_id=ctx.author.id).first()
                if existing:
                    existing.travian_uid = player.uid
                    existing.travian_name = player.name
                else:
                    existing = User(
                        discord_id=ctx.author.id,
                        discord_name=str(ctx.author),
                        travian_uid=player.uid,
                        travian_name=player.name,
                    )
                    db.session.add(existing)
                db.session.commit()
                return "linked", _player_info(player), None

            if len(exact) > 1:
                return "multiple", None, [(p.uid, p.name, p.alliance_name) for p in exact[:5]]

            # Fuzzy (LIKE)
            like = Player.query.filter(Player.name.ilike(f"%{player_name}%")).limit(5).all()
            if like:
                return "fuzzy", None, [(p.uid, p.name, p.alliance_name) for p in like]

            return "not_found", None, None

        status, player, suggestions = await db_query(self.bot, _do_link)

        if status == "linked":
            tribe = TRIBE_NAMES.get(player["tid"], "?")
            emoji = TRIBE_EMOJI.get(player["tid"], "❓")
            embed = discord.Embed(
                title="🔗 Powiązano konto",
                description=(
                    f"**{player['name']}** ({emoji} {tribe})\n"
                    f"Sojusz: {player['alliance']}\n"
                    f"Populacja: {player['pop']:,} | Wioski: {player['villages']}"
                ),
                color=COLOR_GOLD,
            )
            if player["tid"] in TRIBE_ICONS:
                embed.set_thumbnail(url=TRIBE_ICONS[player["tid"]])
            embed.set_footer(text=FOOTER)
            await ctx.followup.send(embed=embed, ephemeral=True)

        elif status == "taken":
            await ctx.followup.send(
                f"⚠️ Gracz **{player['name']}** jest już połączony z innym kontem Discord.",
                ephemeral=True,
            )

        elif status == "multiple":
            names = "\n".join(f"• **{n}** ({a or '—'})" for _, n, a in suggestions)
            await ctx.followup.send(
                f"Znaleziono kilku graczy o nazwie **{player_name}**:\n{names}\n"
                "Podaj dokładną nazwę.",
                ephemeral=True,
            )

        elif status == "fuzzy":
            names = "\n".join(f"• **{n}** ({a or '—'})" for _, n, a in suggestions)
            await ctx.followup.send(
                f"❌ Nie znaleziono **{player_name}**. Może chodziło o:\n{names}",
                ephemeral=True,
            )

        else:
            await ctx.followup.send(
                f"❌ Nie znaleziono gracza **{player_name}** w danych map.sql.\n"
                "💡 Upewnij się, że nazwa jest dokładna. "
                "Jeśli to nowe konto, poczekaj na następny snapshot.",
                ephemeral=True,
            )

    @discord.slash_command(name="tunlink", description="Usuń powiązanie Discord ↔ Travian")
    async def tunlink(self, ctx: discord.ApplicationContext):
        def _do_unlink():
            from app.database import db
            from app.models import User
            user = User.query.filter_by(discord_id=ctx.author.id).first()
            if not user:
                return False
            db.session.delete(user)
            db.session.commit()
            return True

        removed = await db_query(self.bot, _do_unlink)

        if removed:
            await ctx.respond("✅ Powiązanie usunięte.", ephemeral=True)
        else:
            await ctx.respond("ℹ️ Nie masz powiązanego konta.", ephemeral=True)

    @discord.slash_command(name="twhoami", description="Pokaż powiązany profil Travian")
    async def twhoami(self, ctx: discord.ApplicationContext):
        def _get_profile():
            from app.models import Player, User
            user = User.query.filter_by(discord_id=ctx.author.id).first()
            if not user or not user.travian_uid:
                return None
            player = Player.query.get(user.travian_uid)
            if not player:
                return None
            return {
                "name": player.name,
                "tid": player.tid,
                "alliance": player.alliance_name,
                "pop": player.total_pop,
                "villages": player.village_count,
                "linked_at": user.linked_at.strftime("%Y-%m-%d %H:%M UTC") if user.linked_at else "—",
            }

        profile = await db_query(self.bot, _get_profile)

        if not profile:
            await ctx.respond(
                "ℹ️ Nie masz powiązanego konta. Użyj `/tlink`.", ephemeral=True
            )
            return

        tribe = TRIBE_NAMES.get(profile["tid"], "?")
        emoji = TRIBE_EMOJI.get(profile["tid"], "❓")

        embed = discord.Embed(title=f"👤 {profile['name']}", color=COLOR_GOLD)
        if profile["tid"] in TRIBE_ICONS:
            embed.set_thumbnail(url=TRIBE_ICONS[profile["tid"]])
        embed.add_field(name="Plemię", value=f"{emoji} {tribe}", inline=True)
        embed.add_field(name="Sojusz", value=profile["alliance"] or "—", inline=True)
        embed.add_field(name="Populacja", value=f"{profile['pop']:,}", inline=True)
        embed.add_field(name="Wioski", value=str(profile["villages"]), inline=True)
        embed.add_field(name="Powiązano", value=profile["linked_at"], inline=False)
        embed.set_footer(text=FOOTER)

        await ctx.respond(embed=embed, ephemeral=True)


def setup(bot):
    bot.add_cog(Identity(bot))
