"""Player profile route."""

from flask import Blueprint, render_template, abort, jsonify
from sqlalchemy import func
from ..database import db
from ..models import Player, Village, Snapshot, TRIBE_NAMES

bp = Blueprint("players", __name__)


@bp.route("/api/player/<int:uid>/population")
def population_api(uid):
    player = db.session.get(Player, uid)
    if player is None:
        abort(404)

    rows = (
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

    history = [
        {
            "date": row.fetched_at.isoformat(),
            "total_pop": row.total_pop or 0,
            "villages": row.village_count,
        }
        for row in rows
    ]

    return jsonify({"player": player.name, "history": history})


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

    return render_template(
        "player.html",
        player=player,
        villages=villages,
        tribe_name=tribe_name,
        snapshot=latest_snapshot,
    )
