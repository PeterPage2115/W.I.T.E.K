"""Osobisty monitoring — /tmonitor, /tmonitor_ustawienia.

Powiadamia powiązanych graczy przez DM o zmianach w ich wioskach:
spadki populacji, nowi sąsiedzi, wrogowie w pobliżu.
"""

import json
import logging

import discord
from discord.ext import commands, tasks
from sqlalchemy import or_

from bot.bot import db_query
from bot.utils import COLOR_INFO, COLOR_WARNING, FOOTER, torus_distance

logger = logging.getLogger(__name__)


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


class Monitor(commands.Cog):
    """Osobisty monitoring wiosek gracza."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.monitor_check.is_running():
            self.monitor_check.start()
            logger.info("Uruchomiono pętlę osobistego monitoringu")

    def cog_unload(self):
        self.monitor_check.cancel()

    # ------------------------------------------------------------------ #
    # /tmonitor
    # ------------------------------------------------------------------ #

    @discord.slash_command(
        name="tmonitor",
        description="Zarządzaj osobistym monitoringiem wiosek",
    )
    @discord.option(
        "akcja",
        str,
        description="Włącz/wyłącz/status monitoringu",
        choices=["wlacz", "wylacz", "status"],
    )
    async def tmonitor(self, ctx: discord.ApplicationContext, akcja: str):
        """Enable/disable/check personal monitoring."""
        await ctx.defer(ephemeral=True)

        def _handle():
            from app.database import db
            from app.models import MonitorSettings, User

            user = User.query.filter_by(discord_id=ctx.author.id).first()
            if not user or not user.travian_uid:
                return "not_linked", None

            settings = MonitorSettings.query.filter_by(
                discord_id=ctx.author.id
            ).first()

            if akcja == "wlacz":
                if not settings:
                    settings = MonitorSettings(
                        discord_id=ctx.author.id, enabled=True
                    )
                    db.session.add(settings)
                else:
                    settings.enabled = True
                db.session.commit()
                return "enabled", None

            elif akcja == "wylacz":
                if settings:
                    settings.enabled = False
                    db.session.commit()
                return "disabled", None

            else:  # status
                if not settings:
                    return "no_settings", None
                return "status", {
                    "enabled": settings.enabled,
                    "pop_drop_threshold": settings.pop_drop_threshold,
                    "neighbor_radius": settings.neighbor_radius,
                    "enemy_radius": settings.enemy_radius,
                }

        status, data = await db_query(self.bot, _handle)

        if status == "not_linked":
            await ctx.followup.send(
                "❌ Nie masz powiązanego konta. Użyj `/tlink`.", ephemeral=True
            )
            return

        if status == "enabled":
            embed = discord.Embed(
                title="🔔 Monitoring włączony",
                description=(
                    "Będziesz otrzymywać powiadomienia DM o zmianach w Twoich wioskach.\n"
                    "Użyj `/tmonitor_ustawienia` aby dostosować progi."
                ),
                color=COLOR_INFO,
            )
            embed.set_footer(text=FOOTER)
            await ctx.followup.send(embed=embed, ephemeral=True)

        elif status == "disabled":
            await ctx.followup.send(
                "🔕 Monitoring wyłączony. Nie będziesz otrzymywać powiadomień DM.",
                ephemeral=True,
            )

        elif status == "no_settings":
            await ctx.followup.send(
                "ℹ️ Monitoring nie był jeszcze skonfigurowany.\n"
                "Użyj `/tmonitor wlacz` aby go włączyć.",
                ephemeral=True,
            )

        else:  # status
            state = "✅ Włączony" if data["enabled"] else "🔕 Wyłączony"
            embed = discord.Embed(
                title="🔔 Status monitoringu",
                color=COLOR_INFO,
            )
            embed.add_field(name="Stan", value=state, inline=True)
            embed.add_field(
                name="Próg spadku populacji",
                value=f"{data['pop_drop_threshold']} pop",
                inline=True,
            )
            embed.add_field(
                name="Promień sąsiadów",
                value=f"{data['neighbor_radius']} pól",
                inline=True,
            )
            embed.add_field(
                name="Promień wrogów",
                value=f"{data['enemy_radius']} pól",
                inline=True,
            )
            embed.set_footer(text=FOOTER)
            await ctx.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------ #
    # /tmonitor_ustawienia
    # ------------------------------------------------------------------ #

    @discord.slash_command(
        name="tmonitor_ustawienia",
        description="Zmień ustawienia osobistego monitoringu",
    )
    @discord.option(
        "spadek_pop",
        int,
        description="Próg spadku populacji (min 10, max 1000)",
        required=False,
        min_value=10,
        max_value=1000,
    )
    @discord.option(
        "promien_sasiada",
        int,
        description="Promień nowych sąsiadów w polach (min 5, max 50)",
        required=False,
        min_value=5,
        max_value=50,
    )
    @discord.option(
        "promien_wroga",
        int,
        description="Promień wykrywania wrogów w polach (min 5, max 50)",
        required=False,
        min_value=5,
        max_value=50,
    )
    async def tmonitor_ustawienia(
        self,
        ctx: discord.ApplicationContext,
        spadek_pop: int | None = None,
        promien_sasiada: int | None = None,
        promien_wroga: int | None = None,
    ):
        """Change monitoring thresholds."""
        await ctx.defer(ephemeral=True)

        if spadek_pop is None and promien_sasiada is None and promien_wroga is None:
            await ctx.followup.send(
                "⚠️ Podaj przynajmniej jedną opcję do zmiany.", ephemeral=True
            )
            return

        def _update():
            from app.database import db
            from app.models import MonitorSettings, User

            user = User.query.filter_by(discord_id=ctx.author.id).first()
            if not user or not user.travian_uid:
                return "not_linked", None

            settings = MonitorSettings.query.filter_by(
                discord_id=ctx.author.id
            ).first()
            if not settings:
                settings = MonitorSettings(
                    discord_id=ctx.author.id, enabled=True
                )
                db.session.add(settings)

            if spadek_pop is not None:
                settings.pop_drop_threshold = spadek_pop
            if promien_sasiada is not None:
                settings.neighbor_radius = promien_sasiada
            if promien_wroga is not None:
                settings.enemy_radius = promien_wroga

            db.session.commit()
            return "updated", {
                "pop_drop_threshold": settings.pop_drop_threshold,
                "neighbor_radius": settings.neighbor_radius,
                "enemy_radius": settings.enemy_radius,
            }

        status, data = await db_query(self.bot, _update)

        if status == "not_linked":
            await ctx.followup.send(
                "❌ Nie masz powiązanego konta. Użyj `/tlink`.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="✅ Ustawienia zaktualizowane",
            color=COLOR_INFO,
        )
        embed.add_field(
            name="Próg spadku populacji",
            value=f"{data['pop_drop_threshold']} pop",
            inline=True,
        )
        embed.add_field(
            name="Promień sąsiadów",
            value=f"{data['neighbor_radius']} pól",
            inline=True,
        )
        embed.add_field(
            name="Promień wrogów",
            value=f"{data['enemy_radius']} pól",
            inline=True,
        )
        embed.set_footer(text=FOOTER)
        await ctx.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------ #
    # Background loop
    # ------------------------------------------------------------------ #

    @tasks.loop(minutes=30)
    async def monitor_check(self):
        """Periodic check for personal alerts."""
        try:
            users = await db_query(self.bot, self._get_monitored_users)
            if not users:
                return

            snapshots = await db_query(self.bot, self._get_two_latest_snapshots)
            if not snapshots:
                return
            latest_id, previous_id = snapshots

            # Validate snapshot pair (skip if truncated/corrupted)
            valid = await db_query(
                self.bot,
                lambda: self._validate_snapshots(latest_id, previous_id),
            )
            if not valid:
                return

            for user_info in users:
                # Skip if already checked this snapshot
                if user_info["last_checked_snapshot_id"] == latest_id:
                    continue

                try:
                    alerts = await self._check_user_alerts(
                        user_info["discord_id"],
                        user_info["travian_uid"],
                        user_info,
                        latest_id,
                        previous_id,
                    )

                    if alerts:
                        await self._send_dm(user_info["discord_id"], alerts)
                        did = user_info["discord_id"]
                        await db_query(
                            self.bot,
                            lambda: self._store_alerts(
                                did, alerts, latest_id
                            ),
                        )

                    # Update last checked snapshot
                    did = user_info["discord_id"]
                    await db_query(
                        self.bot,
                        lambda: self._update_last_checked(did, latest_id),
                    )

                except discord.Forbidden:
                    logger.warning(
                        "Nie można wysłać DM do %s — użytkownik zablokował bota",
                        user_info["discord_id"],
                    )
                    # Still update cursor so we don't retry forever
                    did = user_info["discord_id"]
                    await db_query(
                        self.bot,
                        lambda: self._update_last_checked(did, latest_id),
                    )
                except Exception:
                    logger.exception(
                        "Błąd monitoringu dla użytkownika %s",
                        user_info["discord_id"],
                    )

        except Exception:
            logger.exception("Błąd pętli monitoringu")

    @monitor_check.before_loop
    async def before_monitor_check(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------ #
    # DB helpers (run inside db_query)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_monitored_users():
        """Get all linked users with monitoring enabled."""
        from app.models import MonitorSettings, User

        rows = (
            MonitorSettings.query
            .join(User, User.discord_id == MonitorSettings.discord_id)
            .filter(MonitorSettings.enabled == True)  # noqa: E712
            .add_columns(User.travian_uid)
            .all()
        )
        return [
            {
                "discord_id": ms.discord_id,
                "travian_uid": uid,
                "pop_drop_threshold": ms.pop_drop_threshold,
                "neighbor_radius": ms.neighbor_radius,
                "enemy_radius": ms.enemy_radius,
                "last_checked_snapshot_id": ms.last_checked_snapshot_id,
            }
            for ms, uid in rows
            if uid is not None
        ]

    @staticmethod
    def _get_two_latest_snapshots():
        """Get (latest_id, previous_id) or None."""
        from app.models import Snapshot

        snaps = (
            Snapshot.query.order_by(Snapshot.fetched_at.desc()).limit(2).all()
        )
        if len(snaps) < 2:
            return None
        return snaps[0].id, snaps[1].id

    @staticmethod
    def _validate_snapshots(latest_id, previous_id):
        """Check snapshot pair is valid (not truncated)."""
        from app.map_sql.alerts import validate_snapshot_pair
        return validate_snapshot_pair(latest_id, previous_id)

    @staticmethod
    def _get_user_villages(snapshot_id, user_uid):
        """Get user's villages as list of dicts."""
        from app.models import Village

        rows = Village.query.filter_by(
            snapshot_id=snapshot_id, uid=user_uid
        ).all()
        return [
            {
                "vid": v.vid,
                "name": v.name,
                "x": v.x,
                "y": v.y,
                "pop": v.population,
            }
            for v in rows
        ]

    @staticmethod
    def _find_new_neighbors(cx, cy, radius, latest_id, previous_id, map_size):
        """Find new villages near (cx, cy) that weren't in previous snapshot."""
        from app.models import Village

        # Bounding box prefilter for latest snapshot
        new_rows = (
            Village.query.filter(
                Village.snapshot_id == latest_id,
                Village.uid > 0,
                _bbox_filter(Village.x, cx, radius, map_size),
                _bbox_filter(Village.y, cy, radius, map_size),
            )
            .all()
        )

        # Get village IDs (vid) that were present in previous snapshot near this location
        old_rows = (
            Village.query.filter(
                Village.snapshot_id == previous_id,
                Village.uid > 0,
                _bbox_filter(Village.x, cx, radius, map_size),
                _bbox_filter(Village.y, cy, radius, map_size),
            )
            .all()
        )
        old_vids = {v.vid for v in old_rows}

        results = []
        for v in new_rows:
            if v.vid in old_vids:
                continue
            dist = torus_distance(cx, cy, v.x, v.y, map_size)
            if dist <= radius:
                results.append({
                    "player": v.player_name,
                    "name": v.name,
                    "x": v.x,
                    "y": v.y,
                    "distance": round(dist, 1),
                })
        return results

    @staticmethod
    def _find_new_enemies(cx, cy, radius, latest_id, previous_id,
                          our_alliances, map_size):
        """Find new enemy villages near (cx, cy)."""
        from app.models import Village

        new_rows = (
            Village.query.filter(
                Village.snapshot_id == latest_id,
                Village.uid > 0,
                Village.aid > 0,
                _bbox_filter(Village.x, cx, radius, map_size),
                _bbox_filter(Village.y, cy, radius, map_size),
            )
            .all()
        )

        old_rows = (
            Village.query.filter(
                Village.snapshot_id == previous_id,
                Village.uid > 0,
                Village.aid > 0,
                _bbox_filter(Village.x, cx, radius, map_size),
                _bbox_filter(Village.y, cy, radius, map_size),
            )
            .all()
        )
        old_vids = {v.vid for v in old_rows}

        our_aids = set(our_alliances) if our_alliances else set()
        results = []
        for v in new_rows:
            if v.vid in old_vids:
                continue
            if v.aid in our_aids:
                continue
            dist = torus_distance(cx, cy, v.x, v.y, map_size)
            if dist <= radius:
                results.append({
                    "player": v.player_name,
                    "alliance": v.alliance_name or "?",
                    "x": v.x,
                    "y": v.y,
                    "distance": round(dist, 1),
                })
        return results

    @staticmethod
    def _store_alerts(discord_id, alerts, snapshot_id):
        """Store PersonalAlert records in DB."""
        from app.database import db
        from app.models import PersonalAlert

        for a in alerts:
            record = PersonalAlert(
                discord_id=discord_id,
                snapshot_id=snapshot_id,
                alert_type=a["type"],
                data=json.dumps(a, ensure_ascii=False),
                notified=True,
            )
            db.session.add(record)
        db.session.commit()

    @staticmethod
    def _update_last_checked(discord_id, snapshot_id):
        """Update last_checked_snapshot_id for a user."""
        from app.database import db
        from app.models import MonitorSettings

        ms = MonitorSettings.query.filter_by(discord_id=discord_id).first()
        if ms:
            ms.last_checked_snapshot_id = snapshot_id
            db.session.commit()

    # ------------------------------------------------------------------ #
    # Alert detection
    # ------------------------------------------------------------------ #

    async def _check_user_alerts(self, discord_id, user_uid, settings,
                                 latest_id, previous_id):
        """Check all alert types for a single user."""
        alerts = []

        map_size = self.bot.flask_app.config.get("TRAVIAN_MAP_SIZE", 401)

        uid = user_uid
        lid = latest_id
        pid = previous_id

        user_villages_new = await db_query(
            self.bot, lambda: self._get_user_villages(lid, uid)
        )
        user_villages_old = await db_query(
            self.bot, lambda: self._get_user_villages(pid, uid)
        )

        # 1. Population drops
        old_by_vid = {v["vid"]: v for v in user_villages_old}
        for v in user_villages_new:
            old = old_by_vid.get(v["vid"])
            if old and old["pop"] - v["pop"] >= settings["pop_drop_threshold"]:
                alerts.append({
                    "type": "pop_drop",
                    "village": v["name"],
                    "coords": f"{v['x']}|{v['y']}",
                    "old_pop": old["pop"],
                    "new_pop": v["pop"],
                    "drop": old["pop"] - v["pop"],
                })

        # 2. New neighbors
        our_alliances = self.bot.flask_app.config.get(
            "TRAVIAN_OUR_ALLIANCES", []
        )
        nr = settings["neighbor_radius"]
        er = settings["enemy_radius"]

        for v in user_villages_new:
            vx, vy = v["x"], v["y"]

            new_neighbors = await db_query(
                self.bot,
                lambda: self._find_new_neighbors(
                    vx, vy, nr, lid, pid, map_size
                ),
            )
            for n in new_neighbors:
                alerts.append({
                    "type": "new_neighbor",
                    "your_village": v["name"],
                    "your_coords": f"{v['x']}|{v['y']}",
                    "neighbor_player": n["player"],
                    "neighbor_village": n["name"],
                    "neighbor_coords": f"{n['x']}|{n['y']}",
                    "distance": n["distance"],
                })

            # 3. Enemy villages appearing nearby
            enemies = await db_query(
                self.bot,
                lambda: self._find_new_enemies(
                    vx, vy, er, lid, pid, our_alliances, map_size
                ),
            )
            for e in enemies:
                alerts.append({
                    "type": "enemy_nearby",
                    "your_village": v["name"],
                    "your_coords": f"{v['x']}|{v['y']}",
                    "enemy_player": e["player"],
                    "enemy_alliance": e["alliance"],
                    "enemy_coords": f"{e['x']}|{e['y']}",
                    "distance": e["distance"],
                })

        return alerts

    # ------------------------------------------------------------------ #
    # DM sending
    # ------------------------------------------------------------------ #

    async def _send_dm(self, discord_id, alerts):
        """Send DM with alert summary to user."""
        user = self.bot.get_user(discord_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(discord_id)
            except discord.NotFound:
                logger.warning("Nie znaleziono użytkownika %s", discord_id)
                return

        embed = discord.Embed(
            title="🔔 Osobisty raport — W.I.T.E.K",
            color=COLOR_WARNING,
        )

        # Group alerts by type
        pop_drops = [a for a in alerts if a["type"] == "pop_drop"]
        neighbors = [a for a in alerts if a["type"] == "new_neighbor"]
        enemies = [a for a in alerts if a["type"] == "enemy_nearby"]

        if pop_drops:
            lines = []
            for a in pop_drops[:10]:
                lines.append(
                    f"**{a['village']}** ({a['coords']}): "
                    f"{a['old_pop']:,} → {a['new_pop']:,} (**-{a['drop']:,}**)"
                )
            embed.add_field(
                name="📉 Spadki populacji",
                value="\n".join(lines),
                inline=False,
            )

        if neighbors:
            lines = []
            for a in neighbors[:10]:
                lines.append(
                    f"Gracz **{a['neighbor_player']}** "
                    f"({a['neighbor_coords']}) — "
                    f"{a['distance']} pól od **{a['your_village']}**"
                )
            embed.add_field(
                name="🏘️ Nowi sąsiedzi",
                value="\n".join(lines),
                inline=False,
            )

        if enemies:
            lines = []
            for a in enemies[:10]:
                lines.append(
                    f"**{a['enemy_player']}** [{a['enemy_alliance']}] "
                    f"({a['enemy_coords']}) — "
                    f"{a['distance']} pól od **{a['your_village']}**"
                )
            embed.add_field(
                name="⚠️ Wrogowie w pobliżu",
                value="\n".join(lines),
                inline=False,
            )

        embed.set_footer(text=FOOTER)

        # May raise discord.Forbidden if user blocks DMs
        await user.send(embed=embed)


def setup(bot: discord.Bot):
    bot.add_cog(Monitor(bot))
