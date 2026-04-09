"""Alliance profile route."""

from flask import Blueprint, render_template, abort, jsonify
from sqlalchemy import func
from ..database import db
from ..models import Alliance, Player, Village, Snapshot

bp = Blueprint("alliances", __name__)


@bp.route("/api/alliance/<int:aid>/population")
def population_api(aid):
    alliance = db.session.get(Alliance, aid)
    if alliance is None:
        abort(404)

    rows = (
        db.session.query(
            Snapshot.fetched_at,
            func.sum(Village.population).label("total_pop"),
            func.count(func.distinct(Village.uid)).label("member_count"),
        )
        .join(Village, Village.snapshot_id == Snapshot.id)
        .filter(Village.aid == aid)
        .group_by(Snapshot.id)
        .order_by(Snapshot.fetched_at)
        .all()
    )

    history = [
        {
            "date": row.fetched_at.isoformat(),
            "total_pop": row.total_pop or 0,
            "members": row.member_count,
        }
        for row in rows
    ]

    return jsonify({"alliance": alliance.name, "history": history})


@bp.route("/alliance/<int:aid>")
def profile(aid):
    alliance = db.session.get(Alliance, aid)
    if alliance is None:
        abort(404)

    members = (
        db.session.query(Player)
        .filter_by(aid=aid)
        .order_by(Player.total_pop.desc())
        .all()
    )

    latest_snapshot = (
        db.session.query(Snapshot).order_by(Snapshot.fetched_at.desc()).first()
    )
    villages = []
    if latest_snapshot:
        villages = (
            db.session.query(Village)
            .filter_by(snapshot_id=latest_snapshot.id, aid=aid)
            .order_by(Village.population.desc())
            .all()
        )

    return render_template(
        "alliance.html",
        alliance=alliance,
        members=members,
        villages=villages,
        snapshot=latest_snapshot,
    )
