"""Zgłaszanie ataków — /tatak, /tdodaj, /tataki, /trozwiaz (S2.3–S2.5).

All DB access through db_query() for async safety.
Village-based attack reports with map links and Discord timestamps.
Editable summary embed in forum threads, @Def role pinging.
"""

import asyncio
import json
import logging
import time as _time
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from bot.bot import db_query
from bot.utils import (
    COLOR_ATTACK, COLOR_DEFENSE, COLOR_INFO, COLOR_SUCCESS, FOOTER,
    ICON_ATTACK, ICON_DEFENSE, STATUS_EMOJI,
    TRIBE_EMOJI, TRIBE_NAMES, TYPE_EMOJI,
    calc_crop_consumption,
    coords_display, detect_possible_units, discord_timestamp,
    format_unit_analysis, parse_attack_time, parse_coords,
    torus_distance, travel_time_str, units_can_reach,
)

log = logging.getLogger(__name__)

# Per-thread lock to serialize summary updates (rubber-duck finding #3)
_thread_locks: dict[int, asyncio.Lock] = {}

# Per-coordinate lock to prevent duplicate defense thread creation
_coord_locks: dict[tuple[int, int], asyncio.Lock] = {}


def _get_thread_lock(thread_id: int) -> asyncio.Lock:
    if thread_id not in _thread_locks:
        _thread_locks[thread_id] = asyncio.Lock()
    return _thread_locks[thread_id]


def _get_coord_lock(x: int, y: int) -> asyncio.Lock:
    key = (x, y)
    if key not in _coord_locks:
        _coord_locks[key] = asyncio.Lock()
    return _coord_locks[key]


class Attacks(commands.Cog):
    """Zgłaszanie i śledzenie ataków na wioski koalicji."""

    def __init__(self, bot):
        self.bot = bot

    def cog_load(self):
        if not getattr(self.bot, '_testing', False):
            self.auto_resolve_loop.start()

    def cog_unload(self):
        if self.auto_resolve_loop.is_running():
            self.auto_resolve_loop.cancel()

    def _server_url(self) -> str:
        return self.bot.flask_app.config.get("TRAVIAN_SERVER_URL", "")

    # ------------------------------------------------------------------ #
    # /tatak — report a new attack
    # ------------------------------------------------------------------ #
    @discord.slash_command(name="tatak", description="Zgłoś atak na wioskę koalicji")
    @discord.option("cel", str, description="Koordynaty atakowanej wioski np. 76|43", required=True)
    @discord.option("zrodlo", str, description="Koordynaty wioski atakującego np. 55|22", required=True)
    @discord.option("czas", str, description="Czas uderzenia np. 14:30 lub 08.04 14:30", required=True)
    @discord.option("atakujacy", str, description="Nazwa atakującego gracza (opcjonalne — odczytane z mapy)", required=False, default="")
    @discord.option("mur", int, description="Poziom muru (0-20)", required=False, default=None, min_value=0, max_value=20)
    @discord.option("zboze", int, description="Ilość zboża w spichlerzu", required=False, default=None)
    @discord.option("produkcja", int, description="Produkcja zboża na godzinę", required=False, default=None)
    @discord.option("notatki", str, description="Dodatkowe informacje", required=False, default="")
    async def tatak(
        self,
        ctx: discord.ApplicationContext,
        cel: str,
        zrodlo: str,
        czas: str,
        atakujacy: str,
        mur: int | None,
        zboze: int | None,
        produkcja: int | None,
        notatki: str,
    ):
        await ctx.defer()

        # Parse defender coordinates
        def_x, def_y = parse_coords(cel)
        if def_x is None:
            await ctx.followup.send(
                "❌ Nieprawidłowe koordynaty celu. Użyj formatu `76|43` lub `76 43`.",
                ephemeral=True,
            )
            return

        # Parse attacker source coordinates (required)
        atk_x, atk_y = parse_coords(zrodlo)
        if atk_x is None:
            await ctx.followup.send(
                "❌ Nieprawidłowe koordynaty źródła. Użyj formatu `55|22`.",
                ephemeral=True,
            )
            return

        # Parse attack time → Unix timestamp
        attack_unix = parse_attack_time(czas)
        if attack_unix is None:
            await ctx.followup.send(
                "❌ Nieprawidłowy czas. Użyj formatu `14:30` lub `08.04 14:30`.",
                ephemeral=True,
            )
            return

        server_url = self._server_url()

        def _save_and_enrich():
            from app.database import db
            from app.models import AttackReport, Player, Village, Snapshot

            snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
            def_village = None
            def_player = None
            atk_village_info = None
            attacker_name = atakujacy  # may be empty
            if snap:
                def_village = Village.query.filter_by(
                    snapshot_id=snap.id, x=def_x, y=def_y
                ).first()
                if def_village:
                    def_player = Player.query.get(def_village.uid)

                # Lookup attacker source village
                atk_v = Village.query.filter_by(
                    snapshot_id=snap.id, x=atk_x, y=atk_y
                ).first()
                if atk_v:
                    atk_village_info = {
                        "name": atk_v.name, "x": atk_v.x, "y": atk_v.y,
                        "pop": atk_v.population, "player": atk_v.player_name,
                    }
                    # Auto-fill attacker name from map data if not provided
                    if not attacker_name:
                        attacker_name = atk_v.player_name or "Nieznany"

            if not attacker_name:
                attacker_name = "Nieznany"

            # Find attacker player
            atk_player = Player.query.filter(Player.name == attacker_name).first()

            report = AttackReport(
                reported_by_discord=str(ctx.author.id),
                reported_by_name=str(ctx.author),
                attacker_name=attacker_name,
                attacker_alliance=atk_player.alliance_name if atk_player else None,
                attacker_x=atk_x,
                attacker_y=atk_y,
                defender_name=def_village.player_name if def_village else None,
                defender_village=def_village.name if def_village else f"({def_x}|{def_y})",
                defender_x=def_x,
                defender_y=def_y,
                attack_time=czas,
                attack_unix=attack_unix,
                wall_level=mur,
                crop_amount=zboze,
                crop_production=produkcja,
                notes=notatki or None,
                status="reported",
            )
            db.session.add(report)
            db.session.commit()

            def _info(p):
                if not p:
                    return None
                return {
                    "name": p.name, "uid": p.uid, "tid": p.tid,
                    "pop": p.total_pop or 0, "villages": p.village_count or 0,
                    "alliance": p.alliance_name or "—",
                    "tribe_emoji": TRIBE_EMOJI.get(p.tid, "❓"),
                    "tribe_name": TRIBE_NAMES.get(p.tid, "?"),
                }

            def _vill(v):
                if not v:
                    return None
                return {
                    "name": v.name, "x": v.x, "y": v.y,
                    "pop": v.population, "player": v.player_name,
                }

            return (
                report.id,
                attacker_name,
                _vill(def_village),
                _info(def_player),
                _info(atk_player),
                atk_village_info,
                {"wall": mur, "crop": zboze, "production": produkcja},
            )

        report_id, resolved_attacker, def_vill, def_info, atk_info, atk_vill, defense_info = await db_query(
            self.bot, _save_and_enrich
        )

        embed = self._build_attack_embed(
            report_id, server_url,
            def_x, def_y, def_vill, def_info,
            resolved_attacker, atk_info, atk_vill, atk_x, atk_y,
            attack_unix, notatki, ctx.author.display_name,
            defense_info=defense_info,
        )

        await ctx.followup.send(embed=embed)

        # Check for existing active defense thread for this village
        def _check_existing_thread():
            from app.database import db
            from app.models import AttackReport, DefenseThread
            dt = DefenseThread.query.filter_by(
                defender_x=def_x, defender_y=def_y, status="active",
            ).first()
            if dt:
                report = AttackReport.query.get(report_id)
                if report:
                    report.forum_thread_id = dt.forum_thread_id
                    db.session.commit()
                return dt.forum_thread_id
            return None

        async with _get_coord_lock(def_x, def_y):
            existing_thread_id = await db_query(self.bot, _check_existing_thread)

            if existing_thread_id:
                # Add to existing thread instead of creating a new one
                try:
                    thread = await self.bot.fetch_channel(existing_thread_id)
                    await thread.send(
                        content=f"➕ **Kolejny atak #{report_id}** dodany do wątku",
                        embed=embed,
                    )
                except Exception:
                    log.exception("Nie udało się dodać ataku do istniejącego wątku %d", existing_thread_id)
                await self._update_thread_summary(existing_thread_id)
            else:
                # Create new forum thread for defense coordination
                defender_name = def_vill["player"] if def_vill else None
                await self._create_defense_thread(
                    ctx, report_id, embed, def_vill, def_x, def_y,
                    defender_name, resolved_attacker, attack_unix,
                    defense_info=defense_info,
                )

        log.info(
            "⚔️ Atak #%d: %s → (%d|%d) o %s (przez %s)",
            report_id, resolved_attacker, def_x, def_y, czas, ctx.author,
        )

    # ------------------------------------------------------------------ #
    # /tdodaj — add attack to existing thread
    # ------------------------------------------------------------------ #
    @discord.slash_command(name="tdodaj", description="Dodaj atak do istniejącego wątku obrony")
    @discord.option("numer", int, description="Numer oryginalnego zgłoszenia z wątkiem", required=True)
    @discord.option("czas", str, description="Czas uderzenia np. 14:30", required=True)
    @discord.option("cel", str, description="Koordynaty celu (auto w wątku obrony)", required=False, default="")
    @discord.option("zrodlo", str, description="Koordynaty wioski atakującego np. 55|22", required=False, default="")
    @discord.option("atakujacy", str, description="Nazwa atakującego (domyślnie z oryginału)", required=False, default="")
    @discord.option("notatki", str, description="Dodatkowe informacje", required=False, default="")
    async def tdodaj(
        self,
        ctx: discord.ApplicationContext,
        numer: int,
        czas: str,
        cel: str,
        zrodlo: str,
        atakujacy: str,
        notatki: str,
    ):
        await ctx.defer()

        # Auto-detect target coords from defense thread if not provided
        if not cel:
            def _get_original_coords():
                from app.models import AttackReport, DefenseThread
                orig = AttackReport.query.get(numer)
                if orig and orig.forum_thread_id:
                    dt = DefenseThread.query.filter_by(
                        forum_thread_id=orig.forum_thread_id, status="active",
                    ).first()
                    if dt:
                        return (dt.defender_x, dt.defender_y)
                return None
            thread_coords = await db_query(self.bot, _get_original_coords)
            if thread_coords:
                def_x, def_y = thread_coords
            else:
                await ctx.followup.send(
                    "❌ Podaj koordynaty celu lub użyj numeru zgłoszenia z aktywnym wątkiem.",
                    ephemeral=True,
                )
                return
        else:
            def_x, def_y = parse_coords(cel)
            if def_x is None:
                await ctx.followup.send("❌ Nieprawidłowe koordynaty celu.", ephemeral=True)
                return

        atk_x, atk_y = (None, None)
        if zrodlo:
            atk_x, atk_y = parse_coords(zrodlo)
            if atk_x is None:
                await ctx.followup.send("❌ Nieprawidłowe koordynaty źródła.", ephemeral=True)
                return

        attack_unix = parse_attack_time(czas)
        if attack_unix is None:
            await ctx.followup.send("❌ Nieprawidłowy czas.", ephemeral=True)
            return

        server_url = self._server_url()

        def _add_to_thread():
            from app.database import db
            from app.models import AttackReport, Player, Village, Snapshot

            original = AttackReport.query.get(numer)
            if not original:
                return None, "not_found"
            if not original.forum_thread_id:
                return None, "no_thread"

            # Validate target coords match the thread's defended village
            from app.models import DefenseThread
            dt = DefenseThread.query.filter_by(
                forum_thread_id=original.forum_thread_id, status="active",
            ).first()
            if dt and (def_x != dt.defender_x or def_y != dt.defender_y):
                return None, "coord_mismatch"

            attacker_name = atakujacy or original.attacker_name

            snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
            def_village = None
            def_player = None
            atk_village_info = None
            atk_player = None
            if snap:
                def_village = Village.query.filter_by(
                    snapshot_id=snap.id, x=def_x, y=def_y
                ).first()
                if def_village:
                    def_player = Player.query.get(def_village.uid)
                if atk_x is not None:
                    atk_v = Village.query.filter_by(
                        snapshot_id=snap.id, x=atk_x, y=atk_y
                    ).first()
                    if atk_v:
                        atk_village_info = {
                            "name": atk_v.name, "x": atk_v.x, "y": atk_v.y,
                            "pop": atk_v.population, "player": atk_v.player_name,
                        }
                        # Auto-fill attacker from source village if not explicitly provided
                        if not atakujacy and atk_v.player_name:
                            attacker_name = atk_v.player_name
                atk_player = Player.query.filter(Player.name == attacker_name).first()

            report = AttackReport(
                reported_by_discord=str(ctx.author.id),
                reported_by_name=str(ctx.author),
                attacker_name=attacker_name,
                attacker_alliance=atk_player.alliance_name if atk_player else original.attacker_alliance,
                attacker_x=atk_x,
                attacker_y=atk_y,
                defender_name=def_village.player_name if def_village else original.defender_name,
                defender_village=def_village.name if def_village else f"({def_x}|{def_y})",
                defender_x=def_x,
                defender_y=def_y,
                attack_time=czas,
                attack_unix=attack_unix,
                notes=notatki or None,
                forum_thread_id=original.forum_thread_id,
                status="reported",
            )
            db.session.add(report)
            db.session.commit()

            def _info(p):
                if not p:
                    return None
                return {
                    "name": p.name, "uid": p.uid, "tid": p.tid,
                    "pop": p.total_pop or 0, "villages": p.village_count or 0,
                    "alliance": p.alliance_name or "—",
                    "tribe_emoji": TRIBE_EMOJI.get(p.tid, "❓"),
                    "tribe_name": TRIBE_NAMES.get(p.tid, "?"),
                }

            def _vill(v):
                if not v:
                    return None
                return {
                    "name": v.name, "x": v.x, "y": v.y,
                    "pop": v.population, "player": v.player_name,
                }

            return {
                "id": report.id,
                "thread_id": original.forum_thread_id,
                "attacker": attacker_name,
                "def_vill": _vill(def_village),
                "def_info": _info(def_player),
                "atk_info": _info(atk_player),
                "atk_vill": atk_village_info,
            }, "ok"

        result, status = await db_query(self.bot, _add_to_thread)

        if status == "not_found":
            await ctx.followup.send(f"❌ Zgłoszenie #{numer} nie istnieje.", ephemeral=True)
            return
        if status == "no_thread":
            await ctx.followup.send(
                f"❌ Zgłoszenie #{numer} nie ma jeszcze wątku na forum. "
                "Wątek może być w trakcie tworzenia — spróbuj ponownie za chwilę, "
                "lub użyj `/tatak` aby zgłosić nowy atak.",
                ephemeral=True,
            )
            return
        if status == "coord_mismatch":
            await ctx.followup.send(
                "❌ Koordynaty celu nie zgadzają się z wątkiem obrony. "
                "Użyj `/tatak` aby zgłosić atak na inną wioskę.",
                ephemeral=True,
            )
            return

        embed = self._build_attack_embed(
            result["id"], server_url,
            def_x, def_y, result["def_vill"], result["def_info"],
            result["attacker"], result["atk_info"], result["atk_vill"], atk_x, atk_y,
            attack_unix, notatki, ctx.author.display_name,
        )

        # Post in the existing forum thread
        try:
            thread = await self.bot.fetch_channel(result["thread_id"])
            await thread.send(
                content=f"➕ **Kolejny atak #{result['id']}** dodany do wątku",
                embed=embed,
            )
        except discord.NotFound:
            log.warning("Wątek %d nie znaleziony", result["thread_id"])
        except discord.Forbidden:
            log.warning("Brak uprawnień do wątku %d", result["thread_id"])
        except Exception:
            log.exception("Błąd wysyłania do wątku")

        # Update the summary embed in the thread starter message
        await self._update_thread_summary(result["thread_id"])

        await ctx.followup.send(
            f"✅ Atak **#{result['id']}** dodany do wątku zgłoszenia #{numer}",
            embed=embed,
        )

    # ------------------------------------------------------------------ #
    # /tataki — list active attacks
    # ------------------------------------------------------------------ #
    @discord.slash_command(name="tataki", description="Lista aktywnych ataków na sojusz")
    @discord.option("godziny", int, description="Pokaż ataki z ostatnich N godzin", required=False, default=24)
    async def tataki(self, ctx: discord.ApplicationContext, godziny: int):
        await ctx.defer()

        server_url = self._server_url()

        def _get_attacks():
            from datetime import timedelta
            from app.models import AttackReport
            cutoff = datetime.now(timezone.utc) - timedelta(hours=godziny)
            cutoff_unix = int(cutoff.timestamp())
            attacks = (
                AttackReport.query
                .filter(
                    AttackReport.attack_unix >= cutoff_unix,
                    AttackReport.status != "resolved",
                )
                .order_by(AttackReport.attack_unix.asc())
                .limit(10)
                .all()
            )
            return [
                {
                    "id": a.id, "attacker": a.attacker_name,
                    "defender": a.defender_name or "?",
                    "village": a.defender_village or "?",
                    "x": a.defender_x, "y": a.defender_y,
                    "time_raw": a.attack_time,
                    "time_unix": a.attack_unix,
                    "status": a.status,
                    "thread_id": a.forum_thread_id,
                }
                for a in attacks
            ]

        attacks = await db_query(self.bot, _get_attacks)

        if not attacks:
            embed = discord.Embed(
                title="📋 Brak ataków",
                description=f"Nie zgłoszono ataków w ostatnich {godziny}h. ✌️",
                color=COLOR_SUCCESS,
            )
            embed.set_footer(text=FOOTER)
            await ctx.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title=f"⚔️ Ataki na sojusz (ostatnie {godziny}h)",
            description=f"Znaleziono **{len(attacks)}** zgłoszeń",
            color=COLOR_ATTACK,
        )
        embed.set_thumbnail(url=ICON_ATTACK)

        for atk in attacks:
            status = STATUS_EMOJI.get(atk["status"], "⚪")
            coord = ""
            if atk["x"] is not None and atk["y"] is not None:
                coord = f" {coords_display(server_url, atk['x'], atk['y'])}"

            time_str = ""
            if atk["time_unix"]:
                time_str = f" | {discord_timestamp(atk['time_unix'], 'R')}"

            thread_link = ""
            if atk["thread_id"]:
                thread_link = f" | [wątek](https://discord.com/channels/{ctx.guild_id}/{atk['thread_id']})"

            embed.add_field(
                name=f"{status} #{atk['id']} — {atk['village']}{coord}",
                value=(
                    f"⚔️ {atk['attacker']} → 🛡️ {atk['defender']}"
                    f"{time_str} | {atk['status']}{thread_link}"
                ),
                inline=False,
            )
        embed.set_footer(text=FOOTER)
        await ctx.followup.send(embed=embed)

    # ------------------------------------------------------------------ #
    # /trozwiaz — resolve attack(s) and archive thread
    # ------------------------------------------------------------------ #
    @discord.slash_command(name="trozwiaz", description="Zamknij zgłoszenie ataku i archiwizuj wątek")
    @discord.option("numer", int, description="Numer zgłoszenia ataku", required=True)
    async def trozwiaz(self, ctx: discord.ApplicationContext, numer: int):
        await ctx.defer()

        def _resolve():
            from app.database import db
            from app.models import AttackReport, DefenseThread

            report = AttackReport.query.get(numer)
            if not report:
                return "not_found"
            if report.status == "resolved":
                return "already_resolved"

            thread_id = report.forum_thread_id
            now = datetime.now(timezone.utc)

            # Close ALL reports linked to the same thread
            closed_ids = [report.id]
            if thread_id:
                linked = AttackReport.query.filter(
                    AttackReport.forum_thread_id == thread_id,
                    AttackReport.status != "resolved",
                ).all()
                for r in linked:
                    r.status = "resolved"
                    r.resolved_at = now
                    if r.id != report.id:
                        closed_ids.append(r.id)
                # Update DefenseThread status
                dt = DefenseThread.query.filter_by(forum_thread_id=thread_id).first()
                if dt:
                    dt.status = "resolved"
            else:
                report.status = "resolved"
                report.resolved_at = now

            db.session.commit()
            return {
                "id": report.id,
                "attacker": report.attacker_name,
                "defender": report.defender_name or "?",
                "village": report.defender_village or "?",
                "thread_id": thread_id,
                "closed_ids": closed_ids,
            }

        result = await db_query(self.bot, _resolve)

        if result == "not_found":
            await ctx.followup.send(f"❌ Atak #{numer} nie istnieje.", ephemeral=True)
            return
        if result == "already_resolved":
            await ctx.followup.send(f"ℹ️ Atak #{numer} jest już rozwiązany.", ephemeral=True)
            return

        closed_text = ", ".join(f"#{i}" for i in result["closed_ids"])
        embed = discord.Embed(
            title="✅ Atak rozwiązany",
            description=(
                f"Zamknięte zgłoszenia: **{closed_text}**\n"
                f"({result['attacker']} → {result['village']})"
            ),
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text=FOOTER)
        await ctx.followup.send(embed=embed)

        # Update summary embed and archive the forum thread
        if result["thread_id"]:
            await self._update_thread_summary(result["thread_id"])
            try:
                thread = await self.bot.fetch_channel(result["thread_id"])
                await thread.send(
                    f"✅ **Ataki {closed_text} rozwiązane** przez {ctx.author.display_name}\n"
                    f"Wątek zostanie zarchiwizowany."
                )
                await thread.edit(archived=True)
                log.info("🗄️ Wątek %d zarchiwizowany", result["thread_id"])
            except discord.NotFound:
                log.warning("Wątek %d nie znaleziony — być może usunięty", result["thread_id"])
            except discord.Forbidden:
                log.warning("Brak uprawnień do archiwizacji wątku %d", result["thread_id"])
            except Exception:
                log.exception("Nie udało się zarchiwizować wątku obrony")
            # Clean up per-thread lock (no longer needed after archive)
            _thread_locks.pop(result["thread_id"], None)

    # ------------------------------------------------------------------ #
    # Shared embed builder — individual attack embed (no tribe thumbnail)
    # ------------------------------------------------------------------ #
    def _build_attack_embed(
        self, report_id, server_url,
        def_x, def_y, def_vill, def_info,
        attacker_name, atk_info, atk_vill, atk_x, atk_y,
        attack_unix, notes, author_name,
        defense_info=None,
    ):
        embed = discord.Embed(
            title="🚨 ATAK NA SOJUSZ!",
            description=f"Zgłoszenie **#{report_id}**",
            color=COLOR_ATTACK,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name="System Alertów W.I.T.E.K", icon_url=ICON_ATTACK)

        # --- Defender (target) ---
        def_coord = coords_display(server_url, def_x, def_y)
        if def_vill:
            def_text = (
                f"🏘️ **{def_vill['name']}** {def_coord}\n"
                f"👤 {def_vill['player']} | 📊 Pop: {def_vill['pop']:,}"
            )
        else:
            def_text = f"📍 Koordynaty: {def_coord}\n⚠️ _Wioska nie znaleziona w danych_"
        if def_info:
            alliance_part = f"[{def_info['alliance']}] | " if def_info.get('alliance', '').strip() else ""
            def_text += f"\n🛡️ {alliance_part}{def_info['tribe_emoji']} {def_info['tribe_name']}"
        embed.add_field(name="🛡️ Cel ataku", value=def_text, inline=False)

        # --- Attacker ---
        atk_text = f"👤 **{attacker_name}**"
        if atk_info:
            alliance_part = f" | ⚔️ [{atk_info['alliance']}]" if atk_info.get('alliance', '').strip() else ""
            atk_text += (
                f"\n🏰 {atk_info['tribe_emoji']} {atk_info['tribe_name']}"
                f"{alliance_part}"
                f"\n📊 Pop: {atk_info['pop']:,} | 🏘️ {atk_info['villages']} wiosek"
            )
        else:
            atk_text += "\n⚠️ _Gracz nie znaleziony w danych_"

        # Attacker source village
        if atk_x is not None and atk_y is not None:
            atk_coord = coords_display(server_url, atk_x, atk_y)
            if atk_vill:
                atk_text += f"\n📍 Z: **{atk_vill['name']}** {atk_coord} (pop {atk_vill['pop']:,})"
            else:
                atk_text += f"\n📍 Z: {atk_coord}"

        embed.add_field(name="⚔️ Agresor", value=atk_text, inline=False)

        # --- Attack time ---
        time_text = (
            f"{discord_timestamp(attack_unix, 'f')} "
            f"({discord_timestamp(attack_unix, 'R')})"
        )
        embed.add_field(name="⏰ Uderzenie", value=time_text, inline=False)

        # --- Distance & travel time analysis ---
        if atk_x is not None and atk_y is not None:
            cfg = self.bot.flask_app.config
            _ms = cfg.get("TRAVIAN_MAP_SIZE", 401)
            _features = cfg.get("TRAVIAN_FEATURES", {})
            _wr = _features.get("map_edge_wrapping", True)
            dist = torus_distance(atk_x, atk_y, def_x, def_y, _ms, wrap=_wr)
            seconds_left = attack_unix - int(_time.time())
            embed.add_field(
                name="📏 Dystans",
                value=f"**{dist:.2f}** pól",
                inline=True,
            )

            tribe_id = atk_info["tid"] if atk_info else None
            if tribe_id and seconds_left > 0:
                units = units_can_reach(tribe_id, dist, seconds_left)
                if units:
                    can_lines = []
                    cant_lines = []
                    for u in units:
                        emoji = TYPE_EMOJI.get(u["type"], "")
                        line = f"{emoji} {u['name']}: {u['travel']} ({u['speed']}f/h)"
                        if u["can_reach"]:
                            can_lines.append(f"✅ {line}")
                        else:
                            cant_lines.append(f"❌ {line}")

                    travel_text = ""
                    if can_lines:
                        travel_text += "**Zdążą:**\n" + "\n".join(can_lines)
                    if cant_lines:
                        if travel_text:
                            travel_text += "\n"
                        travel_text += "**Nie zdążą:**\n" + "\n".join(cant_lines)
                    travel_text += "\n_⚠️ Przybliżenie — bez Placu Turniejowego/butów_"

                    embed.add_field(
                        name=f"🕐 Analiza podróży ({atk_info['tribe_name']})",
                        value=travel_text[:1024],
                        inline=False,
                    )

            # --- Reverse unit detection (S4.2) ---
            if seconds_left > 0:
                analysis = detect_possible_units(dist, seconds_left, tribe_id)
                if analysis:
                    embed.add_field(
                        name="🔍 Analiza jednostek",
                        value=format_unit_analysis(analysis),
                        inline=False,
                    )
            elif seconds_left <= 0:
                embed.add_field(
                    name="⚠️ Czas uderzenia",
                    value="Atak już nastąpił lub zaraz nastąpi!",
                    inline=True,
                )

        # --- Defense info (wall, crop) ---
        if defense_info:
            di_parts = []
            if defense_info.get("wall") is not None:
                di_parts.append(f"🧱 Mur: **{defense_info['wall']}**")
            if defense_info.get("crop") is not None:
                di_parts.append(f"🌾 Zboże: **{defense_info['crop']:,}**")
            if defense_info.get("production") is not None:
                di_parts.append(f"📈 Produkcja: **{defense_info['production']:,}/h**")
            if di_parts:
                embed.add_field(
                    name="🏰 Info o wiosce",
                    value="\n".join(di_parts),
                    inline=False,
                )

        if notes:
            embed.add_field(name="📝 Notatki", value=notes, inline=False)

        embed.set_footer(text=f"{FOOTER} | Zgłosił: {author_name}")
        return embed

    # ------------------------------------------------------------------ #
    # Summary embed — aggregated view of all attacks for a thread
    # ------------------------------------------------------------------ #
    def _build_summary_embed(self, server_url, thread_data, attacks_data, defense_data):
        """Build an editable summary embed for the defense thread.

        Args:
            server_url: Travian server URL
            thread_data: dict from DefenseThread (defender coords, village, wall, crop)
            attacks_data: list of dicts from AttackReport (attacker, coords, time, status)
            defense_data: dict with garrison/support info
        """
        def_x = thread_data["defender_x"]
        def_y = thread_data["defender_y"]
        village_name = thread_data.get("defender_village") or f"({def_x}|{def_y})"
        def_coord = coords_display(server_url, def_x, def_y)

        active = [a for a in attacks_data if a["status"] != "resolved"]
        resolved = [a for a in attacks_data if a["status"] == "resolved"]

        embed = discord.Embed(
            title=f"🚨 OBRONA — {village_name} {def_coord}",
            description=(
                f"Gracz: **{thread_data.get('defender_player', '?')}**\n"
                f"Łącznie ataków: **{len(attacks_data)}** "
                f"(aktywnych: {len(active)}, rozwiązanych: {len(resolved)})"
            ),
            color=COLOR_ATTACK if active else COLOR_SUCCESS,
        )
        embed.set_author(name="System Obrony W.I.T.E.K", icon_url=ICON_DEFENSE)

        # --- Attack list (bounded to 10, rubber-duck finding #4) ---
        if active:
            atk_lines = []
            for a in active[:10]:
                status_e = STATUS_EMOJI.get(a["status"], "⚪")
                time_str = discord_timestamp(a["attack_unix"], "R") if a.get("attack_unix") else "?"
                atk_line = f"{status_e} **#{a['id']}**: {a['attacker']}"
                if a.get("attacker_x") is not None and a.get("attacker_y") is not None:
                    atk_line += f" ({a['attacker_x']}|{a['attacker_y']})"
                atk_line += f" → {time_str}"
                atk_lines.append(atk_line)
            if len(active) > 10:
                atk_lines.append(f"_...i {len(active) - 10} więcej_")
            embed.add_field(
                name="⚔️ Aktywne ataki",
                value="\n".join(atk_lines)[:1024],
                inline=False,
            )

        if resolved:
            embed.add_field(
                name="✅ Rozwiązane",
                value=f"{len(resolved)} ataków rozwiązanych",
                inline=True,
            )

        # --- Defense info (wall, crop) ---
        di_parts = []
        wall = thread_data.get("wall_level")
        crop = thread_data.get("crop_amount")
        prod = thread_data.get("crop_production")
        if wall is not None:
            di_parts.append(f"🧱 Mur: **{wall}**")
        if crop is not None:
            di_parts.append(f"🌾 Zboże: **{crop:,}**")
        if prod is not None:
            di_parts.append(f"📈 Produkcja: **{prod:,}/h**")
        if di_parts:
            embed.add_field(name="🏰 Info o wiosce", value="\n".join(di_parts), inline=False)

        # --- Garrison + Support ---
        total_crop = 0
        if defense_data.get("garrison"):
            g = defense_data["garrison"]
            g_crop = g.get("crop", 0)
            total_crop += g_crop
            troops = g.get("troops", {})
            lines = [f"{name}: **{count}**" for name, count in list(troops.items())[:8]]
            if len(troops) > 8:
                lines.append(f"_...i {len(troops) - 8} więcej_")
            embed.add_field(
                name=f"🛡️ Garnizon ({g.get('player', '?')}) — 🌾 {g_crop}/h",
                value="\n".join(lines)[:1024] if lines else "_brak danych_",
                inline=False,
            )

        supports = defense_data.get("supports", [])
        if supports:
            for i, s in enumerate(supports[:5], 1):
                s_crop = s.get("crop", 0)
                total_crop += s_crop
                troops = s.get("troops", {})
                troop_lines = [f"{name}: **{count}**" for name, count in list(troops.items())[:6]]
                if len(troops) > 6:
                    troop_lines.append(f"_...i {len(troops) - 6} więcej_")
                troop_lines.append(f"🌾 {s_crop}/h")
                embed.add_field(
                    name=f"📤 Wsparcie #{i} od {s.get('player', '?')} ({s['from_x']}|{s['from_y']})",
                    value="\n".join(troop_lines)[:1024],
                    inline=False,
                )
            if len(supports) > 5:
                extra_crop = sum(s.get("crop", 0) for s in supports[5:])
                total_crop += extra_crop
                embed.add_field(
                    name="📤 Pozostałe wsparcie",
                    value=f"_+{len(supports) - 5} więcej (🌾 {extra_crop}/h)_",
                    inline=False,
                )

        if total_crop > 0:
            embed.add_field(
                name="📊 Łączne zużycie zboża",
                value=f"**{total_crop}** zboża/h",
                inline=True,
            )

        # --- Commands reminder ---
        first_id = attacks_data[0]["id"] if attacks_data else "?"
        embed.add_field(
            name="📌 Komendy",
            value=(
                f"`/tdodaj {first_id}` — dodaj kolejny atak\n"
                f"`/twsparcie` — zarejestruj wsparcie\n"
                f"`/trozwiaz {first_id}` — zamknij"
            ),
            inline=False,
        )

        embed.set_footer(text=FOOTER)
        return embed

    # ------------------------------------------------------------------ #
    # /tdef — who can send defense?
    # ------------------------------------------------------------------ #

    # Key defensive units per tribe: (inf_name, inf_speed, cav_name, cav_speed)
    _DEF_UNITS = {
        1: ("Pretorianin", 10, "Eq. Caesaris", 20),   # Romans
        3: ("Falanga", 14, "Druid", 32),                # Gauls
        6: ("Ash Warden", 6, "Resheph Chariot", 10),   # Egyptians
        7: ("Mercenary", 7, "Marksman", 15),            # Huns
        8: ("Shieldsman", 8, "Elpida Rider", 16),       # Spartans
        9: ("Shield Maiden", 7, "Huskarl Rider", 12),   # Vikings
    }

    @discord.slash_command(name="tdef", description="Kto może wysłać def? Lista wiosek sojuszu z ETA")
    @discord.option("cel", str, description="Koordynaty atakowanej wioski np. 76|43", required=False, default=None)
    async def tdef(self, ctx: discord.ApplicationContext, cel: str | None):
        await ctx.defer()

        # Parse or auto-detect coordinates
        if cel is not None:
            def_x, def_y = parse_coords(cel)
            if def_x is None:
                await ctx.followup.send(
                    "❌ Nieprawidłowe koordynaty. Użyj formatu `76|43`.",
                    ephemeral=True,
                )
                return
        else:
            def _detect():
                from app.models import DefenseThread
                dt = DefenseThread.query.filter_by(
                    forum_thread_id=ctx.channel_id, status="active",
                ).first()
                if dt:
                    return (dt.defender_x, dt.defender_y)
                return None

            coords = await db_query(self.bot, _detect)
            if coords:
                def_x, def_y = coords
            else:
                await ctx.followup.send(
                    "❌ Podaj koordynaty lub użyj komendy w wątku obrony.",
                    ephemeral=True,
                )
                return

        server_url = self._server_url()
        alliance_ids = self.bot.flask_app.config.get("TRAVIAN_OUR_ALLIANCES", [])

        if not alliance_ids:
            await ctx.followup.send(
                "⚠️ Brak skonfigurowanych sojuszy (`our_alliances` w config.yaml).",
                ephemeral=True,
            )
            return

        # Query alliance villages from latest snapshot
        def _get_villages():
            from app.models import Snapshot, Village

            snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
            if not snap:
                return None, None

            villages = Village.query.filter(
                Village.snapshot_id == snap.id,
                Village.aid.in_(alliance_ids),
            ).all()

            target = Village.query.filter_by(
                snapshot_id=snap.id, x=def_x, y=def_y,
            ).first()
            target_info = None
            if target:
                target_info = {
                    "name": target.name,
                    "player": target.player_name,
                    "tid": target.tid,
                    "pop": target.population,
                }

            result = []
            for v in villages:
                if v.x == def_x and v.y == def_y:
                    continue
                result.append({
                    "x": v.x, "y": v.y,
                    "name": v.name, "player_name": v.player_name,
                    "tid": v.tid, "population": v.population,
                })

            return result, target_info

        villages, target_info = await db_query(self.bot, _get_villages)

        if villages is None:
            await ctx.followup.send(
                "❌ Brak danych — najpierw pobierz snapshot.",
                ephemeral=True,
            )
            return

        if not villages:
            await ctx.followup.send(
                "⚠️ Nie znaleziono wiosek sojuszu w aktualnym snapshocie.",
                ephemeral=True,
            )
            return

        # Calculate distances and ETAs, sort by distance
        _features = self.bot.flask_app.config.get("TRAVIAN_FEATURES", {})
        _wrap = _features.get("map_edge_wrapping", True)
        _map_sz = self.bot.flask_app.config.get("TRAVIAN_MAP_SIZE", 401)
        entries = []
        for v in villages:
            dist = torus_distance(v["x"], v["y"], def_x, def_y, _map_sz, wrap=_wrap)
            tid = v.get("tid") or 0
            def_info = self._DEF_UNITS.get(tid)
            if def_info:
                inf_name, inf_speed, cav_name, cav_speed = def_info
                inf_eta = travel_time_str(dist, inf_speed)
                cav_eta = travel_time_str(dist, cav_speed)
            else:
                inf_name, inf_eta = "?", "?"
                cav_name, cav_eta = "?", "?"

            entries.append({
                **v, "dist": dist,
                "inf_name": inf_name, "inf_eta": inf_eta,
                "cav_name": cav_name, "cav_eta": cav_eta,
            })

        entries.sort(key=lambda e: e["dist"])
        top = entries[:20]

        # Build embed
        target_label = coords_display(server_url, def_x, def_y)
        desc_parts = []
        if target_info:
            tribe_emoji = TRIBE_EMOJI.get(target_info.get("tid"), "")
            info_line = f"**Cel:** {target_info['name']} — {target_info['player']}"
            if tribe_emoji:
                info_line += f" {tribe_emoji}"
            info_line += f" (pop: {target_info['pop']})"
            desc_parts.append(info_line)
        desc_parts.append(f"**Link:** {target_label}")
        desc_parts.append(f"**Wiosek sojuszu:** {len(entries)} | Pokazano top {len(top)}")

        embed = discord.Embed(
            title=f"🛡️ Potencjalna obrona dla ({def_x}|{def_y})",
            description="\n".join(desc_parts),
            color=COLOR_DEFENSE,
        )
        embed.set_thumbnail(url=ICON_DEFENSE)

        for i, e in enumerate(top, 1):
            tribe_emoji = TRIBE_EMOJI.get(e.get("tid"), "❓")
            v_link = coords_display(server_url, e["x"], e["y"])
            name = e["name"] or "?"
            player = e["player_name"] or "?"
            dist_str = f"{e['dist']:.1f}"

            field_name = f"{i}. {tribe_emoji} {name} — {player}"
            field_value = (
                f"📍 {v_link} • 📏 {dist_str} pól\n"
                f"🚶 {e['inf_name']}: **{e['inf_eta']}** • "
                f"🐴 {e['cav_name']}: **{e['cav_eta']}**"
            )
            embed.add_field(name=field_name, value=field_value, inline=False)

        embed.set_footer(text=FOOTER)
        await ctx.followup.send(embed=embed)

    # ------------------------------------------------------------------ #
    # Forum thread helpers
    # ------------------------------------------------------------------ #
    async def _get_forum(self):
        """Get the defense forum channel, or None."""
        forum_id = self.bot.flask_app.config.get("DISCORD_DEFENSE_FORUM_ID")
        if not forum_id:
            return None
        forum = self.bot.get_channel(forum_id)
        if not forum:
            try:
                forum = await self.bot.fetch_channel(forum_id)
            except Exception:
                log.warning("Forum obrony (ID: %s) nie znaleziony", forum_id)
                return None
        if not isinstance(forum, discord.ForumChannel):
            log.warning("Kanał %s nie jest ForumChannel", forum_id)
            return None
        return forum

    async def _create_defense_thread(
        self, ctx, report_id, embed, def_vill, def_x, def_y,
        defender_name, attacker, attack_unix,
        defense_info=None,
    ):
        """Create a thread in the defense forum with @Def ping and summary embed."""
        forum = await self._get_forum()
        if not forum:
            return

        try:
            village_name = def_vill["name"] if def_vill else f"({def_x}|{def_y})"
            thread_name = f"🚨 Obrona: {village_name} ({def_x}|{def_y})"

            # @Def role ping
            def_role_id = self.bot.flask_app.config.get("DISCORD_DEF_ROLE_ID")
            if not def_role_id:
                log.warning("DISCORD_DEF_ROLE_ID nie ustawiony — brak pingu @Def")
            ping_text = f"<@&{def_role_id}> " if def_role_id else ""
            content = (
                f"{ping_text}**Wioska pod atakiem!**\n\n"
                f"📌 `/tdodaj {report_id}` — dodaj kolejny atak\n"
                f"📤 `/twsparcie` — zarejestruj wsparcie\n"
                f"✅ `/trozwiaz {report_id}` — zamknij"
            )

            # AllowedMentions with roles=True (rubber-duck finding #5)
            mentions = discord.AllowedMentions(roles=True, users=False, everyone=False)

            thread = await forum.create_thread(
                name=thread_name[:100],
                embed=embed,
                content=content,
                allowed_mentions=mentions,
            )

            # Save thread ID + create DefenseThread record
            def _save_thread():
                from app.database import db
                from app.models import AttackReport, DefenseThread
                report = AttackReport.query.get(report_id)
                if report:
                    report.forum_thread_id = thread.id
                # Prevent duplicate active threads for same village coords
                existing_dt = DefenseThread.query.filter_by(
                    defender_x=def_x, defender_y=def_y, status="active",
                ).first()
                if existing_dt:
                    log.warning(
                        "Aktywny wątek już istnieje dla (%d|%d) — thread %s, linkuję do istniejącego",
                        def_x, def_y, existing_dt.forum_thread_id,
                    )
                    report.forum_thread_id = existing_dt.forum_thread_id
                    db.session.commit()
                    return

                dt = DefenseThread(
                    forum_thread_id=thread.id,
                    defender_x=def_x,
                    defender_y=def_y,
                    defender_village=village_name,
                    defender_player=defender_name,
                    wall_level=defense_info.get("wall") if defense_info else None,
                    crop_amount=defense_info.get("crop") if defense_info else None,
                    crop_production=defense_info.get("production") if defense_info else None,
                    status="active",
                )
                db.session.add(dt)
                db.session.commit()

            await db_query(self.bot, _save_thread)
            log.info("📋 Wątek obrony utworzony: %s (thread: %d)", thread_name, thread.id)

        except discord.Forbidden:
            log.warning("Brak uprawnień do tworzenia wątków na forum obrony")
        except Exception:
            log.exception("Błąd tworzenia wątku obrony")

    async def _gather_thread_data(self, thread_id):
        """Collect all data needed for summary embed from DB."""
        def _query():
            from app.models import AttackReport, DefenseThread, VillageTroops, TroopSupport

            dt = DefenseThread.query.filter_by(forum_thread_id=thread_id).first()
            if not dt:
                return None

            thread_data = {
                "defender_x": dt.defender_x,
                "defender_y": dt.defender_y,
                "defender_village": dt.defender_village,
                "defender_player": dt.defender_player,
                "wall_level": dt.wall_level,
                "crop_amount": dt.crop_amount,
                "crop_production": dt.crop_production,
            }

            attacks = AttackReport.query.filter_by(forum_thread_id=thread_id).order_by(
                AttackReport.attack_unix.asc()
            ).all()
            attacks_data = [
                {
                    "id": a.id,
                    "attacker": a.attacker_name or "?",
                    "attacker_x": a.attacker_x,
                    "attacker_y": a.attacker_y,
                    "status": a.status,
                    "attack_unix": a.attack_unix,
                }
                for a in attacks
            ]

            # Garrison (scoped by forum_thread_id coordinates)
            garrison = VillageTroops.query.filter_by(
                village_x=dt.defender_x, village_y=dt.defender_y
            ).order_by(VillageTroops.updated_at.desc()).first()
            garrison_data = None
            if garrison:
                troops = json.loads(garrison.troops) if garrison.troops else {}
                garrison_data = {
                    "player": garrison.player_name,
                    "troops": troops,
                    "crop": garrison.crop_consumption or 0,
                }

            # Supports scoped by thread (attack_report_id in this thread's attacks)
            attack_ids = [a.id for a in attacks]
            supports_data = []
            if attack_ids:
                supports = TroopSupport.query.filter(
                    TroopSupport.attack_report_id.in_(attack_ids),
                    TroopSupport.status == "in_transit",
                ).all()
                for s in supports:
                    troops = json.loads(s.troops) if s.troops else {}
                    supports_data.append({
                        "player": s.player_name,
                        "from_x": s.from_x,
                        "from_y": s.from_y,
                        "troops": troops,
                        "crop": s.crop_consumption or 0,
                    })

            # Also supports by coords (fallback for supports not linked to specific attack)
            coord_supports = TroopSupport.query.filter_by(
                to_x=dt.defender_x, to_y=dt.defender_y,
                status="in_transit",
            ).filter(
                TroopSupport.attack_report_id.is_(None)
            ).all()
            for s in coord_supports:
                troops = json.loads(s.troops) if s.troops else {}
                supports_data.append({
                    "player": s.player_name,
                    "from_x": s.from_x,
                    "from_y": s.from_y,
                    "troops": troops,
                    "crop": s.crop_consumption or 0,
                })

            defense_data = {"garrison": garrison_data, "supports": supports_data}
            return thread_data, attacks_data, defense_data

        return await db_query(self.bot, _query)

    async def _update_thread_summary(self, thread_id):
        """Rebuild and edit the forum starter message with current summary.

        Uses asyncio.Lock per thread to prevent race conditions (rubber-duck #3).
        """
        lock = _get_thread_lock(thread_id)
        async with lock:
            result = await self._gather_thread_data(thread_id)
            if not result:
                log.warning("Brak DefenseThread dla thread_id %d", thread_id)
                return

            thread_data, attacks_data, defense_data = result
            server_url = self._server_url()
            embed = self._build_summary_embed(server_url, thread_data, attacks_data, defense_data)

            try:
                thread = await self.bot.fetch_channel(thread_id)
                # Forum starter message ID == thread ID (rubber-duck finding #1)
                starter = await thread.fetch_message(thread_id)
                await starter.edit(embed=embed)
                log.info("📝 Summary zaktualizowane dla wątku %d", thread_id)
            except discord.NotFound:
                log.warning("Starter message %d nie znaleziony — wątek usunięty?", thread_id)
            except discord.Forbidden:
                log.warning("Brak uprawnień do edycji starter message %d", thread_id)
            except Exception:
                log.exception("Błąd edycji summary w wątku %d", thread_id)

    # ------------------------------------------------------------------ #
    # Auto-resolve expired attacks
    # ------------------------------------------------------------------ #

    def _do_auto_resolve(self, threshold_minutes: int) -> list[dict]:
        """DB-side auto-resolve logic. Returns list of resolved thread info dicts."""
        from app.database import db
        from app.models import AttackReport, DefenseThread

        now = datetime.now(timezone.utc)
        now_unix = int(now.timestamp())
        threshold_unix = now_unix - (threshold_minutes * 60)

        resolved = []

        # Thread-level: find active DefenseThreads
        active_threads = DefenseThread.query.filter_by(status="active").all()
        for dt in active_threads:
            reports = AttackReport.query.filter(
                AttackReport.forum_thread_id == dt.forum_thread_id,
                AttackReport.status != "resolved",
            ).all()

            if not reports:
                continue

            all_expired = all(
                r.attack_unix and r.attack_unix < threshold_unix
                for r in reports
            )
            if not all_expired:
                continue

            report_ids = []
            for r in reports:
                r.status = "resolved"
                r.resolved_at = now
                r.auto_resolved = True
                report_ids.append(r.id)

            dt.status = "resolved"
            resolved.append({"thread_id": dt.forum_thread_id, "report_ids": report_ids})

        # Orphan reports (no thread)
        orphans = AttackReport.query.filter(
            AttackReport.forum_thread_id.is_(None),
            AttackReport.status != "resolved",
            AttackReport.attack_unix.isnot(None),
            AttackReport.attack_unix < threshold_unix,
        ).all()
        for r in orphans:
            r.status = "resolved"
            r.resolved_at = now
            r.auto_resolved = True

        db.session.commit()
        return resolved

    @tasks.loop(minutes=5)
    async def auto_resolve_loop(self):
        """Automatically resolve expired attack reports."""
        try:
            if not getattr(self.bot, 'flask_app', None):
                return

            from app.config import Config
            threshold_minutes = Config.AUTO_RESOLVE_AFTER_MINUTES

            resolved_threads = await db_query(self.bot, lambda: self._do_auto_resolve(threshold_minutes))

            for thread_info in (resolved_threads or []):
                try:
                    thread = await self.bot.fetch_channel(thread_info["thread_id"])
                    ids_text = ", ".join(f"#{i}" for i in thread_info["report_ids"])
                    await thread.send(f"🕐 Ataki {ids_text} automatycznie rozwiązane (czas ataku minął)")
                    await thread.edit(archived=True)
                except Exception:
                    log.exception("Auto-resolve: nie udało się zarchiwizować wątku %s",
                                  thread_info.get("thread_id"))
        except Exception:
            log.exception("Auto-resolve loop error")

    @auto_resolve_loop.before_loop
    async def before_auto_resolve(self):
        await self.bot.wait_until_ready()


def setup(bot):
    bot.add_cog(Attacks(bot))
