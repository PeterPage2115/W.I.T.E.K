"""Alliance profile route."""

import csv
import io

from flask import Blueprint, render_template, abort, jsonify, Response
from sqlalchemy import func
from ..auth_utils import login_required, role_required
from ..database import db
from ..models import Alliance, Player, Village, Snapshot
from ..snapshot_helpers import get_latest_snapshot

bp = Blueprint("alliances", __name__)


def _alliance_history_rows(aid):
    """Fetch population + member count history for an alliance across all snapshots."""
    return (
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


@bp.route("/api/alliance/<int:aid>/population")
def population_api(aid):
    alliance = db.session.get(Alliance, aid)
    if alliance is None:
        abort(404)

    rows = _alliance_history_rows(aid)

    history = [
        {
            "date": row.fetched_at.isoformat(),
            "total_pop": row.total_pop or 0,
            "members": row.member_count,
        }
        for row in rows
    ]

    return jsonify({"alliance": alliance.name, "history": history})


@bp.route("/api/alliance/<int:aid>/history")
def history_api(aid):
    """JSON API: population and member count over time (flat array)."""
    alliance = db.session.get(Alliance, aid)
    if alliance is None:
        abort(404)

    rows = _alliance_history_rows(aid)
    history = [
        {
            "date": row.fetched_at.strftime("%Y-%m-%d %H:%M"),
            "total_pop": row.total_pop or 0,
            "player_count": row.member_count,
        }
        for row in rows
    ]

    return jsonify(history)


def _member_pop_changes(aid):
    """Compute per-member pop change between the two most recent snapshots.

    Returns dict mapping uid -> pop_change (int). Empty if only one snapshot.
    """
    latest_two = (
        db.session.query(Snapshot)
        .order_by(Snapshot.fetched_at.desc())
        .limit(2)
        .all()
    )
    if len(latest_two) < 2:
        return {}

    current_snap, prev_snap = latest_two[0], latest_two[1]

    current_rows = (
        db.session.query(
            Village.uid,
            func.sum(Village.population).label("pop"),
        )
        .filter(Village.snapshot_id == current_snap.id, Village.aid == aid)
        .group_by(Village.uid)
        .all()
    )

    prev_rows = (
        db.session.query(
            Village.uid,
            func.sum(Village.population).label("pop"),
        )
        .filter(Village.snapshot_id == prev_snap.id, Village.aid == aid)
        .group_by(Village.uid)
        .all()
    )

    prev_map = {r.uid: r.pop for r in prev_rows}
    changes = {}
    for r in current_rows:
        prev_pop = prev_map.get(r.uid)
        if prev_pop is not None:
            changes[r.uid] = r.pop - prev_pop
    return changes


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

    latest_snapshot = get_latest_snapshot()
    villages = []
    if latest_snapshot:
        villages = (
            db.session.query(Village)
            .filter_by(snapshot_id=latest_snapshot.id, aid=aid)
            .order_by(Village.population.desc())
            .all()
        )

    pop_changes = _member_pop_changes(aid)

    return render_template(
        "alliance.html",
        alliance=alliance,
        members=members,
        villages=villages,
        pop_changes=pop_changes,
    )


@bp.route("/alliances/export")
@login_required
@role_required("leader", "officer")
def export_csv():
    """Export all alliances as CSV."""
    alliances = (
        db.session.query(Alliance)
        .order_by(Alliance.total_pop.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Sojusz", "Gracze", "Populacja"])
    for a in alliances:
        writer.writerow([
            a.name,
            a.member_count or 0,
            a.total_pop or 0,
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=sojusze_eksport.csv",
        },
    )
