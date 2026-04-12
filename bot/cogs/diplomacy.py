"""Komendy dyplomatyczne — zarządzanie relacjami sojuszniczymi."""

import logging

import discord
from discord.ext import commands
from sqlalchemy import func

from bot.bot import db_query
from bot.utils import (
    COLOR_ATTACK,
    COLOR_INFO,
    COLOR_SUCCESS,
    FOOTER,
)

log = logging.getLogger(__name__)

RELATION_LABELS = {
    "ally": ("🤝 Sojusze", COLOR_SUCCESS),
    "pact": ("📜 Pakty", COLOR_INFO),
    "nap": ("📜 NAP", COLOR_INFO),
    "war": ("⚔️ Wojny", COLOR_ATTACK),
}

TYPE_CHOICES = [
    discord.OptionChoice(name="sojusz", value="ally"),
    discord.OptionChoice(name="pakt", value="pact"),
    discord.OptionChoice(name="nap", value="nap"),
    discord.OptionChoice(name="wojna", value="war"),
]


def _get_all_relations():
    from app.models import DiplomaticRelation

    relations = (
        DiplomaticRelation.query
        .filter_by(active=True)
        .order_by(DiplomaticRelation.relation_type, DiplomaticRelation.target_alliance_name)
        .all()
    )
    grouped = {}
    for r in relations:
        grouped.setdefault(r.relation_type, []).append({
            "id": r.id,
            "name": r.target_alliance_name or f"ID:{r.target_alliance_id}",
            "notes": r.notes,
            "created_by": r.created_by,
        })
    return grouped


def _add_relation(relation_type, alliance_name, created_by, notes=None):
    from app.models import Alliance, DiplomaticRelation
    from app.database import db

    # Fuzzy match against known alliances
    alliance = (
        Alliance.query
        .filter(func.lower(Alliance.name) == alliance_name.lower())
        .first()
    )
    if not alliance:
        # Try partial match
        alliance = (
            Alliance.query
            .filter(Alliance.name.ilike(f"%{alliance_name}%"))
            .first()
        )

    aid = alliance.aid if alliance else 0
    name = alliance.name if alliance else alliance_name

    # Check for existing active relation
    existing = (
        DiplomaticRelation.query
        .filter_by(target_alliance_name=name, active=True)
        .first()
    )
    if existing:
        return None, name, existing.relation_type

    rel = DiplomaticRelation(
        relation_type=relation_type,
        target_alliance_id=aid,
        target_alliance_name=name,
        created_by=created_by,
        notes=notes,
    )
    db.session.add(rel)
    db.session.commit()
    return rel.id, name, None


def _remove_relation(alliance_name):
    from app.models import DiplomaticRelation
    from app.database import db

    rel = (
        DiplomaticRelation.query
        .filter(
            DiplomaticRelation.active.is_(True),
            func.lower(DiplomaticRelation.target_alliance_name) == alliance_name.lower(),
        )
        .first()
    )
    if not rel:
        # Partial match
        rel = (
            DiplomaticRelation.query
            .filter(
                DiplomaticRelation.active.is_(True),
                DiplomaticRelation.target_alliance_name.ilike(f"%{alliance_name}%"),
            )
            .first()
        )
    if not rel:
        return None

    rel.active = False
    db.session.commit()
    return {
        "name": rel.target_alliance_name,
        "type": rel.relation_type,
    }


class Diplomacy(commands.Cog):
    """Komendy dyplomatyczne."""

    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(name="tdyplomacja", description="Pokaż relacje dyplomatyczne")
    async def tdyplomacja(self, ctx: discord.ApplicationContext):
        grouped = await db_query(self.bot, _get_all_relations)

        if not grouped:
            embed = discord.Embed(
                title="🏛️ Dyplomacja",
                description="Brak aktywnych relacji dyplomatycznych.",
                color=COLOR_INFO,
            )
            embed.set_footer(text=FOOTER)
            await ctx.respond(embed=embed)
            return

        embed = discord.Embed(title="🏛️ Dyplomacja", color=COLOR_INFO)

        for rtype in ("ally", "pact", "nap", "war"):
            items = grouped.get(rtype, [])
            if not items:
                continue
            label, _ = RELATION_LABELS[rtype]
            names = []
            for item in items:
                entry = f"**{item['name']}**"
                if item["notes"]:
                    entry += f" — {item['notes']}"
                names.append(entry)
            embed.add_field(name=label, value="\n".join(names), inline=False)

        embed.set_footer(text=FOOTER)
        await ctx.respond(embed=embed)

    @discord.slash_command(name="tdodaj_relacje", description="Dodaj relację dyplomatyczną")
    @discord.option("typ", description="Typ relacji", choices=TYPE_CHOICES)
    @discord.option("sojusz", str, description="Nazwa sojuszu")
    @discord.option("notatki", str, description="Opcjonalne notatki", required=False, default=None)
    async def tdodaj_relacje(self, ctx: discord.ApplicationContext, typ: str, sojusz: str, notatki: str):
        author = ctx.author.display_name

        rel_id, name, existing_type = await db_query(
            self.bot,
            lambda: _add_relation(typ, sojusz, author, notatki),
        )

        if existing_type:
            label, _ = RELATION_LABELS.get(existing_type, (existing_type, COLOR_INFO))
            embed = discord.Embed(
                title="⚠️ Relacja już istnieje",
                description=f"**{name}** ma już aktywną relację: {label}",
                color=COLOR_ATTACK,
            )
            embed.set_footer(text=FOOTER)
            await ctx.respond(embed=embed)
            return

        label, color = RELATION_LABELS.get(typ, (typ, COLOR_INFO))
        embed = discord.Embed(
            title="✅ Dodano relację",
            description=f"**{name}** → {label}",
            color=color,
        )
        if notatki:
            embed.add_field(name="📝 Notatki", value=notatki, inline=False)
        embed.set_footer(text=FOOTER)
        await ctx.respond(embed=embed)

    @discord.slash_command(name="tusun_relacje", description="Usuń relację dyplomatyczną")
    @discord.option("sojusz", str, description="Nazwa sojuszu")
    async def tusun_relacje(self, ctx: discord.ApplicationContext, sojusz: str):
        result = await db_query(self.bot, lambda: _remove_relation(sojusz))

        if not result:
            embed = discord.Embed(
                title="❌ Nie znaleziono",
                description=f"Brak aktywnej relacji z **{sojusz}**.",
                color=COLOR_ATTACK,
            )
            embed.set_footer(text=FOOTER)
            await ctx.respond(embed=embed)
            return

        label, _ = RELATION_LABELS.get(result["type"], (result["type"], COLOR_INFO))
        embed = discord.Embed(
            title="✅ Usunięto relację",
            description=f"**{result['name']}** ({label}) — dezaktywowano.",
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text=FOOTER)
        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Diplomacy(bot))
