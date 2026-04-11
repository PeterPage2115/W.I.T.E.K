"""Player profile route."""

from flask import Blueprint, render_template, abort, jsonify
from sqlalchemy import func
from ..database import db
from ..models import Player, Village, Snapshot, TRIBE_NAMES

bp = Blueprint("players", __name__)


def _player_history_rows(uid):
    """Fetch population history rows for a player across all snapshots."""
    return (
        db.session.query(
            Snapshot.fetched_at,
            func.sum(Village.population).label("total_pop"),
            func.count(Village.map_id).label("village_count"),
        )
        .join(Village, Village.snapshot_id == Snapshot.id)
        .filter(Village.uid == uid)
        .group_by(Snapshot.id)
        .order_by(Snapshot.fetched_at)
        .all()
    )


@bp.route("/api/player/<int:uid>/population")
def population_api(uid):
    player = db.session.get(Player, uid)
    if player is None:
        abort(404)

    rows = _player_history_rows(uid)
    history = [
        {
            "date": row.fetched_at.isoformat(),
            "total_pop": row.total_pop or 0,
            "villages": row.village_count,
        }
        for row in rows
    ]

    return jsonify({"player": player.name, "history": history})


@bp.route("/api/player/<int:uid>/history")
def history_api(uid):
    """JSON API: population and village count over time for charts."""
    player = db.session.get(Player, uid)
    if player is None:
        abort(404)

    rows = _player_history_rows(uid)
    history = [
        {
            "date": row.fetched_at.strftime("%Y-%m-%d %H:%M"),
            "population": row.total_pop or 0,
            "village_count": row.village_count,
        }
        for row in rows
    ]

    return jsonify(history)


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

    activity_status = None
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
