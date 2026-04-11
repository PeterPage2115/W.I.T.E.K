# Player Profiles Enhancement — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add activity detection, population trends, and "first seen" date to the player profile page, plus a `/tprofil` Discord command.

**Architecture:** Extend the existing `profile()` route in `app/routes/players.py` to compute activity stats from snapshot history, update the `player.html` template to display them, add a `/tprofil` slash command to `bot/cogs/recon.py`, and add tests covering all new logic.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, py-cord (Discord), pytest

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/routes/players.py` | Modify | Add activity computation logic to `profile()` |
| `app/templates/player.html` | Modify | Display activity badge, pop change, daily growth, first seen |
| `bot/cogs/recon.py` | Modify | Add `/tprofil` slash command |
| `tests/test_player_routes.py` | Modify | Add tests for activity status, pop change, single/multi snapshot |

---

## Chunk 1: Backend Activity Logic + Tests

### Task 1: Write failing tests for activity computation

**Files:**
- Modify: `tests/test_player_routes.py`

These tests verify the new template context variables rendered in HTML.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_player_routes.py` inside the `TestPlayerProfile` class:

```python
class TestPlayerActivity:
    """Tests for player activity detection on profile page."""

    def test_active_player_shows_green_badge(self, client, db_session):
        """Player with pop change in last 3 snapshots = Aktywny."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=2), village_count=10)
        snap2 = Snapshot(fetched_at=now - timedelta(days=1), village_count=10)
        snap3 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2, snap3])
        db_session.flush()

        player = Player(uid=100, name="Aktywny", tid=1, total_pop=600, village_count=1)
        db_session.add(player)

        # Pop grows across snapshots: 200 -> 400 -> 600
        for snap, pop in [(snap1, 200), (snap2, 400), (snap3, 600)]:
            db_session.add(Village(
                map_id=1, snapshot_id=snap.id, x=0, y=0, tid=1, vid=100,
                name="V1", uid=100, player_name="Aktywny", aid=1,
                alliance_name="A", population=pop,
            ))
        db_session.commit()

        resp = client.get("/player/100")
        assert resp.status_code == 200
        assert "Aktywny" in resp.data.decode()
        assert "\U0001f7e2" in resp.data.decode()  # 🟢

    def test_inactive_player_shows_red_badge(self, client, db_session):
        """Player with no pop change in last 3 snapshots = Nieaktywny."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=2), village_count=10)
        snap2 = Snapshot(fetched_at=now - timedelta(days=1), village_count=10)
        snap3 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2, snap3])
        db_session.flush()

        player = Player(uid=101, name="Leniwy", tid=2, total_pop=300, village_count=1)
        db_session.add(player)

        # Pop stays the same: 300 -> 300 -> 300
        for snap in [snap1, snap2, snap3]:
            db_session.add(Village(
                map_id=2, snapshot_id=snap.id, x=5, y=5, tid=2, vid=200,
                name="V2", uid=101, player_name="Leniwy", aid=1,
                alliance_name="A", population=300,
            ))
        db_session.commit()

        resp = client.get("/player/101")
        assert resp.status_code == 200
        assert "Nieaktywny" in resp.data.decode()
        assert "\U0001f534" in resp.data.decode()  # 🔴

    def test_new_player_shows_yellow_badge(self, client, db_session):
        """Player with only 1 snapshot = Nowy gracz."""
        now = datetime.now(timezone.utc)
        snap = Snapshot(fetched_at=now, village_count=10)
        db_session.add(snap)
        db_session.flush()

        player = Player(uid=102, name="Nowy", tid=3, total_pop=100, village_count=1)
        db_session.add(player)
        db_session.add(Village(
            map_id=3, snapshot_id=snap.id, x=10, y=10, tid=3, vid=300,
            name="V3", uid=102, player_name="Nowy", aid=0,
            alliance_name="", population=100,
        ))
        db_session.commit()

        resp = client.get("/player/102")
        assert resp.status_code == 200
        assert "Nowy" in resp.data.decode()
        assert "\U0001f7e1" in resp.data.decode()  # 🟡

    def test_pop_change_display_positive(self, client, db_session):
        """Positive pop change shows green arrow ▲."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=3), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        player = Player(uid=103, name="Rosnacy", tid=1, total_pop=500, village_count=1)
        db_session.add(player)

        db_session.add(Village(
            map_id=4, snapshot_id=snap1.id, x=0, y=0, tid=1, vid=400,
            name="V4", uid=103, player_name="Rosnacy", aid=1,
            alliance_name="A", population=200,
        ))
        db_session.add(Village(
            map_id=4, snapshot_id=snap2.id, x=0, y=0, tid=1, vid=400,
            name="V4", uid=103, player_name="Rosnacy", aid=1,
            alliance_name="A", population=500,
        ))
        db_session.commit()

        resp = client.get("/player/103")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "▲" in html
        assert "+300" in html

    def test_pop_change_display_negative(self, client, db_session):
        """Negative pop change shows red arrow ▼."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=3), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        player = Player(uid=104, name="Spadajacy", tid=2, total_pop=100, village_count=1)
        db_session.add(player)

        db_session.add(Village(
            map_id=5, snapshot_id=snap1.id, x=1, y=1, tid=2, vid=500,
            name="V5", uid=104, player_name="Spadajacy", aid=1,
            alliance_name="A", population=400,
        ))
        db_session.add(Village(
            map_id=5, snapshot_id=snap2.id, x=1, y=1, tid=2, vid=500,
            name="V5", uid=104, player_name="Spadajacy", aid=1,
            alliance_name="A", population=100,
        ))
        db_session.commit()

        resp = client.get("/player/104")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "▼" in html
        assert "-300" in html

    def test_single_snapshot_no_crash(self, client, db_session):
        """Profile with only one snapshot doesn't crash or show change data."""
        now = datetime.now(timezone.utc)
        snap = Snapshot(fetched_at=now, village_count=5)
        db_session.add(snap)
        db_session.flush()

        player = Player(uid=105, name="Solo", tid=3, total_pop=250, village_count=1)
        db_session.add(player)
        db_session.add(Village(
            map_id=6, snapshot_id=snap.id, x=2, y=2, tid=3, vid=600,
            name="V6", uid=105, player_name="Solo", aid=0,
            alliance_name="", population=250,
        ))
        db_session.commit()

        resp = client.get("/player/105")
        assert resp.status_code == 200
        # Should not crash; should not show pop change arrows
        html = resp.data.decode()
        assert "Solo" in html

    def test_no_snapshots_no_crash(self, client, db_session):
        """Profile for player with no villages in any snapshot doesn't crash."""
        player = Player(uid=106, name="Pusty", tid=1, total_pop=0, village_count=0)
        db_session.add(player)
        db_session.commit()

        resp = client.get("/player/106")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Pusty" in html

    def test_first_seen_date_displayed(self, client, db_session):
        """First seen date is displayed on the profile."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=5), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        player = Player(uid=107, name="Stary", tid=1, total_pop=800, village_count=1)
        db_session.add(player)
        for snap, pop in [(snap1, 400), (snap2, 800)]:
            db_session.add(Village(
                map_id=7, snapshot_id=snap.id, x=3, y=3, tid=1, vid=700,
                name="V7", uid=107, player_name="Stary", aid=1,
                alliance_name="A", population=pop,
            ))
        db_session.commit()

        resp = client.get("/player/107")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "Pierwszy snapshot" in html

    def test_avg_daily_growth_displayed(self, client, db_session):
        """Average daily growth is displayed when history exists."""
        now = datetime.now(timezone.utc)
        snap1 = Snapshot(fetched_at=now - timedelta(days=10), village_count=10)
        snap2 = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([snap1, snap2])
        db_session.flush()

        player = Player(uid=108, name="Rosnie", tid=2, total_pop=600, village_count=1)
        db_session.add(player)
        db_session.add(Village(
            map_id=8, snapshot_id=snap1.id, x=4, y=4, tid=2, vid=800,
            name="V8", uid=108, player_name="Rosnie", aid=1,
            alliance_name="A", population=100,
        ))
        db_session.add(Village(
            map_id=8, snapshot_id=snap2.id, x=4, y=4, tid=2, vid=800,
            name="V8", uid=108, player_name="Rosnie", aid=1,
            alliance_name="A", population=600,
        ))
        db_session.commit()

        resp = client.get("/player/108")
        html = resp.data.decode()
        assert resp.status_code == 200
        # 500 pop over 10 days = ~50/day
        assert "Średni dzienny wzrost" in html
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `python -m pytest tests/test_player_routes.py::TestPlayerActivity -v --tb=short`
Expected: All tests FAIL (new context variables not rendered in template yet)

### Task 2: Implement activity computation in `profile()` route

**Files:**
- Modify: `app/routes/players.py`

- [ ] **Step 3: Add activity computation logic**

Replace the `profile()` function in `app/routes/players.py` with:

```python
@bp.route("/player/<int:uid>")
def profile(uid):
    player = db.session.get(Player, uid)
    if player is None:
        abort(404)

    latest_snapshot = (
        db.session.query(Snapshot).order_by(Snapshot.fetched_at.desc()).first()
    )
    villages = []
    if latest_snapshot:
        villages = (
            db.session.query(Village)
            .filter_by(snapshot_id=latest_snapshot.id, uid=uid)
            .order_by(Village.population.desc())
            .all()
        )

    tribe_name = TRIBE_NAMES.get(player.tid, "Nieznane")

    # --- Activity detection ---
    # All snapshots where this player has villages, ordered by date
    snapshot_rows = (
        db.session.query(
            Snapshot.id,
            Snapshot.fetched_at,
            func.sum(Village.population).label("total_pop"),
        )
        .join(Village, Village.snapshot_id == Snapshot.id)
        .filter(Village.uid == uid)
        .group_by(Snapshot.id)
        .order_by(Snapshot.fetched_at)
        .all()
    )

    activity_status = None  # "active" / "inactive" / "new"
    activity_label = ""
    pop_change = None
    pop_arrow = ""
    pop_change_class = ""
    avg_daily_growth = None
    first_seen_date = None

    if snapshot_rows:
        first_seen_date = snapshot_rows[0].fetched_at
        first_total = snapshot_rows[0].total_pop or 0
        latest_total = snapshot_rows[-1].total_pop or 0

        if len(snapshot_rows) >= 2:
            pop_change = latest_total - first_total
            if pop_change > 0:
                pop_arrow = "▲"
                pop_change_class = "text-green-600"
            elif pop_change < 0:
                pop_arrow = "▼"
                pop_change_class = "text-red-600"
            else:
                pop_arrow = "▶"
                pop_change_class = "text-trav-text-muted"

            days_between = max(
                (snapshot_rows[-1].fetched_at - snapshot_rows[0].fetched_at).total_seconds() / 86400,
                0.01,
            )
            avg_daily_growth = pop_change / days_between

        # Activity: check last 3 snapshots
        recent = snapshot_rows[-3:] if len(snapshot_rows) >= 3 else snapshot_rows
        if len(recent) >= 2:
            pops = [r.total_pop or 0 for r in recent]
            if pops[-1] != pops[0]:
                activity_status = "active"
                activity_label = "Aktywny 🟢"
            else:
                activity_status = "inactive"
                activity_label = "Nieaktywny 🔴"
        else:
            activity_status = "new"
            activity_label = "Nowy gracz 🟡"

    return render_template(
        "player.html",
        player=player,
        villages=villages,
        tribe_name=tribe_name,
        snapshot=latest_snapshot,
        activity_status=activity_status,
        activity_label=activity_label,
        pop_change=pop_change,
        pop_arrow=pop_arrow,
        pop_change_class=pop_change_class,
        avg_daily_growth=avg_daily_growth,
        first_seen_date=first_seen_date,
    )
```

Note: The `func` import already exists on line 4.

### Task 3: Update the player template

**Files:**
- Modify: `app/templates/player.html`

- [ ] **Step 4: Add activity badge to player header**

In the player header section (after the tribe/alliance line, around line 27), add:

```html
            {% if activity_label %}
            <span class="inline-block mt-1 px-2 py-0.5 rounded text-xs font-semibold
                {% if activity_status == 'active' %}bg-green-900/30 text-green-400
                {% elif activity_status == 'inactive' %}bg-red-900/30 text-red-400
                {% else %}bg-yellow-900/30 text-yellow-400{% endif %}">
                {{ activity_label }}
            </span>
            {% endif %}
```

- [ ] **Step 5: Add pop change, daily growth, and first seen stat cards**

Replace the existing 3-card stats grid (lines 32-47) with a 3-column + 3-column grid:

```html
<!-- Stats Row 1 -->
<div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
    <div class="trav-panel p-4">
        <div class="text-trav-text-muted text-xs uppercase tracking-wider mb-1">Populacja</div>
        <div class="text-2xl font-bold text-trav-brown-dark">{{ "{:,}".format(player.total_pop) }}</div>
        {% if pop_change is not none %}
        <div class="text-sm mt-1 {{ pop_change_class }}">
            {{ pop_arrow }} {{ "{:+,}".format(pop_change) }}
        </div>
        {% endif %}
    </div>
    <div class="trav-panel p-4">
        <div class="text-trav-text-muted text-xs uppercase tracking-wider mb-1">Wioski</div>
        <div class="text-2xl font-bold text-trav-brown-dark">{{ player.village_count }}</div>
    </div>
    <div class="trav-panel p-4">
        <div class="text-trav-text-muted text-xs uppercase tracking-wider mb-1">Średnia populacja</div>
        <div class="text-2xl font-bold text-trav-brown-dark">
            {% if player.village_count %}{{ "{:,.0f}".format(player.total_pop / player.village_count) }}{% else %}0{% endif %}
        </div>
    </div>
</div>

<!-- Stats Row 2 -->
<div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
    {% if avg_daily_growth is not none %}
    <div class="trav-panel p-4">
        <div class="text-trav-text-muted text-xs uppercase tracking-wider mb-1">Średni dzienny wzrost</div>
        <div class="text-2xl font-bold {{ 'text-green-600' if avg_daily_growth > 0 else 'text-red-600' if avg_daily_growth < 0 else 'text-trav-brown-dark' }}">
            {{ "{:+,.1f}".format(avg_daily_growth) }} / dzień
        </div>
    </div>
    {% endif %}
    {% if first_seen_date %}
    <div class="trav-panel p-4">
        <div class="text-trav-text-muted text-xs uppercase tracking-wider mb-1">Pierwszy snapshot</div>
        <div class="text-lg font-bold text-trav-brown-dark">
            {{ first_seen_date.strftime('%d.%m.%Y %H:%M') }}
        </div>
    </div>
    {% endif %}
    {% if activity_label and not avg_daily_growth is none %}
    <div class="trav-panel p-4">
        <div class="text-trav-text-muted text-xs uppercase tracking-wider mb-1">Status aktywności</div>
        <div class="text-lg font-bold">{{ activity_label }}</div>
    </div>
    {% endif %}
</div>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_player_routes.py -v --tb=short`
Expected: All tests PASS (old + new)

- [ ] **Step 7: Commit**

```bash
git add app/routes/players.py app/templates/player.html tests/test_player_routes.py
git commit -m "feat: add activity detection and pop trends to player profile"
```

---

## Chunk 2: Discord `/tprofil` Command

### Task 4: Add `/tprofil` command to recon cog

**Files:**
- Modify: `bot/cogs/recon.py`

- [ ] **Step 8: Add the `/tprofil` command**

Add the following imports at the top of `bot/cogs/recon.py` (merge with existing):

```python
from bot.utils import (
    COLOR_ATTACK,
    COLOR_INFO,
    COLOR_WARNING,
    FOOTER,
    TRIBE_EMOJI,
    TRIBE_ICONS,
    TRIBE_NAMES,
    coords_display,
    parse_coords,
    torus_distance,
)
```

Add this method to the `Recon` class (before the `tnieaktywni` command):

```python
    @discord.slash_command(
        name="tprofil",
        description="Pokaż profil gracza Travian",
    )
    @discord.option(
        "player_name", str,
        description="Nazwa gracza",
        required=True,
    )
    async def tprofil(self, ctx: discord.ApplicationContext, player_name: str):
        await ctx.defer()

        def _get_profile():
            from app.models import Player, Village, Snapshot
            from app.database import db
            from sqlalchemy import func

            # Exact match first, then LIKE fallback
            player = Player.query.filter(Player.name == player_name).first()
            if not player:
                like = Player.query.filter(
                    Player.name.ilike(f"%{player_name}%")
                ).limit(5).all()
                if not like:
                    return None, None
                if len(like) == 1:
                    player = like[0]
                else:
                    return "multiple", [
                        {"name": p.name, "uid": p.uid, "alliance": p.alliance_name or "—"}
                        for p in like
                    ]

            # Snapshot history
            snapshot_rows = (
                db.session.query(
                    Snapshot.fetched_at,
                    func.sum(Village.population).label("total_pop"),
                )
                .join(Village, Village.snapshot_id == Snapshot.id)
                .filter(Village.uid == player.uid)
                .group_by(Snapshot.id)
                .order_by(Snapshot.fetched_at)
                .all()
            )

            # Activity detection
            activity = "Nowy gracz 🟡"
            trend = "➡️ Stabilny"
            pop_change = 0
            first_seen = None

            if snapshot_rows:
                first_seen = snapshot_rows[0].fetched_at.strftime("%d.%m.%Y")
                first_total = snapshot_rows[0].total_pop or 0
                latest_total = snapshot_rows[-1].total_pop or 0

                if len(snapshot_rows) >= 2:
                    pop_change = latest_total - first_total
                    if pop_change > 0:
                        trend = "↗️ Rosnący"
                    elif pop_change < 0:
                        trend = "↘️ Spadający"

                    recent = snapshot_rows[-3:] if len(snapshot_rows) >= 3 else snapshot_rows
                    pops = [r.total_pop or 0 for r in recent]
                    if pops[-1] != pops[0]:
                        activity = "Aktywny 🟢"
                    else:
                        activity = "Nieaktywny 🔴"

            return "ok", {
                "name": player.name,
                "uid": player.uid,
                "tid": player.tid,
                "aid": player.aid,
                "alliance": player.alliance_name or "Bez sojuszu",
                "pop": player.total_pop or 0,
                "villages": player.village_count or 0,
                "activity": activity,
                "trend": trend,
                "pop_change": pop_change,
                "first_seen": first_seen,
            }

        status, data = await db_query(self.bot, _get_profile)

        if status is None:
            await ctx.followup.send(
                f"❌ Nie znaleziono gracza **{player_name}**.",
            )
            return

        if status == "multiple":
            lines = [f"• **{p['name']}** ({p['alliance']})" for p in data]
            await ctx.followup.send(
                f"⚠️ Znaleziono wielu graczy pasujących do **{player_name}**:\n"
                + "\n".join(lines)
                + "\n\nPodaj dokładną nazwę.",
            )
            return

        p = data
        tribe = TRIBE_NAMES.get(p["tid"], "Nieznane")
        emoji = TRIBE_EMOJI.get(p["tid"], "❓")

        embed = discord.Embed(
            title=f"{emoji} {p['name']}",
            color=COLOR_INFO,
        )

        # Tribe icon as thumbnail
        icon = TRIBE_ICONS.get(p["tid"])
        if icon:
            embed.set_thumbnail(url=icon)

        embed.add_field(name="🏛️ Plemię", value=tribe, inline=True)
        embed.add_field(name="🤝 Sojusz", value=p["alliance"], inline=True)
        embed.add_field(name="👥 Populacja", value=f"{p['pop']:,}", inline=True)
        embed.add_field(name="🏘️ Wioski", value=str(p["villages"]), inline=True)
        embed.add_field(name="📊 Status", value=p["activity"], inline=True)
        embed.add_field(name="📈 Trend", value=p["trend"], inline=True)

        if p["pop_change"] != 0:
            sign = "+" if p["pop_change"] > 0 else ""
            embed.add_field(
                name="📉 Zmiana populacji",
                value=f"{sign}{p['pop_change']:,}",
                inline=True,
            )

        if p["first_seen"]:
            embed.add_field(
                name="📅 Pierwszy snapshot",
                value=p["first_seen"],
                inline=True,
            )

        # Dashboard link
        cfg = self.bot.flask_app.config
        server_url = cfg.get("TRAVIAN_SERVER_URL", "")
        if server_url:
            embed.add_field(
                name="🔗 Profil na mapie",
                value=f"[Travian]({server_url}/position_details.php?x=0&y=0&uid={p['uid']})",
                inline=False,
            )

        embed.set_footer(text=FOOTER)
        await ctx.followup.send(embed=embed)
```

- [ ] **Step 9: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 10: Commit**

```bash
git add bot/cogs/recon.py
git commit -m "feat: add /tprofil Discord command for player profiles"
```
