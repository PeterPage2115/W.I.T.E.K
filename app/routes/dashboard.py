"""Dashboard route — main page."""

from flask import Blueprint, render_template
from sqlalchemy import func
from ..database import db
from ..models import Snapshot, Alliance, Player, AttackReport, Alert, Village

bp = Blueprint("dashboard", __name__)


def _recent_alerts(limit=5):
    """Last N alerts ordered by newest first."""
    return (
        db.session.query(Alert)
        .order_by(Alert.created_at.desc())
        .limit(limit)
        .all()
    )


def _server_pop_trend(limit=7):
    """Total server population for the last N snapshots.

    Returns list of dicts with snapshot_id, fetched_at, total_pop
    ordered oldest-first (for sparkline rendering).
    """
    recent_snapshots = (
        db.session.query(Snapshot.id, Snapshot.fetched_at)
        .order_by(Snapshot.fetched_at.desc())
        .limit(limit)
        .all()
    )
    if not recent_snapshots:
        return []

    snapshot_ids = [s.id for s in recent_snapshots]
    pop_rows = (
        db.session.query(
            Village.snapshot_id,
            func.sum(Village.population).label("total_pop"),
        )
        .filter(Village.snapshot_id.in_(snapshot_ids))
        .group_by(Village.snapshot_id)
        .all()
    )
    pop_map = {r.snapshot_id: r.total_pop or 0 for r in pop_rows}

    result = [
        {
            "snapshot_id": s.id,
            "fetched_at": s.fetched_at,
            "total_pop": pop_map.get(s.id, 0),
        }
        for s in recent_snapshots
    ]
    result.reverse()  # oldest first
    return result


def _top_movers(limit=5):
    """Top population gainers and losers between the two most recent snapshots.

    Returns (gainers, losers) — each a list of dicts with
    uid, name, old_pop, new_pop, diff.
    """
    snapshots = (
        db.session.query(Snapshot.id)
        .order_by(Snapshot.fetched_at.desc())
        .limit(2)
        .all()
    )
    if len(snapshots) < 2:
        return [], []

    new_sid, old_sid = snapshots[0].id, snapshots[1].id

    def _player_pops(sid):
        return dict(
            db.session.query(
                Village.uid,
                func.sum(Village.population).label("pop"),
            )
            .filter(Village.snapshot_id == sid, Village.uid.isnot(None))
            .group_by(Village.uid)
            .all()
        )

    new_pops = _player_pops(new_sid)
    old_pops = _player_pops(old_sid)

    # Only compare players present in both snapshots
    common_uids = set(new_pops) & set(old_pops)
    diffs = [
        (uid, new_pops[uid] - old_pops[uid], old_pops[uid], new_pops[uid])
        for uid in common_uids
    ]

    # Gainers — biggest positive diff
    diffs.sort(key=lambda x: x[1], reverse=True)
    gainer_uids = [d[0] for d in diffs[:limit] if d[1] > 0]
    # Losers — biggest negative diff
    diffs.sort(key=lambda x: x[1])
    loser_uids = [d[0] for d in diffs[:limit] if d[1] < 0]

    all_uids = set(gainer_uids) | set(loser_uids)
    names = {}
    if all_uids:
        rows = (
            db.session.query(Player.uid, Player.name)
            .filter(Player.uid.in_(all_uids))
            .all()
        )
        names = {r.uid: r.name for r in rows}

    def _build(uid_list):
        result = []
        for uid in uid_list:
            result.append(
                {
                    "uid": uid,
                    "name": names.get(uid, f"Gracz #{uid}"),
                    "old_pop": old_pops.get(uid, 0),
                    "new_pop": new_pops.get(uid, 0),
                    "diff": new_pops.get(uid, 0) - old_pops.get(uid, 0),
                }
            )
        return result

    return _build(gainer_uids), _build(loser_uids)


@bp.route("/")
def index():
    top_alliances = (
        db.session.query(Alliance)
        .order_by(Alliance.total_pop.desc())
        .limit(15)
        .all()
    )

    top_players = (
        db.session.query(Player)
        .order_by(Player.total_pop.desc())
        .limit(15)
        .all()
    )

    total_alliances = db.session.query(func.count(Alliance.aid)).scalar() or 0
    total_players = db.session.query(func.count(Player.uid)).scalar() or 0

    active_attacks = (
        db.session.query(AttackReport)
        .filter(AttackReport.status != "resolved")
        .order_by(AttackReport.attack_unix.asc())
        .limit(10)
        .all()
    )

    recent_alerts = _recent_alerts()
    server_pop_trend = _server_pop_trend()
    top_gainers, top_losers = _top_movers()

    return render_template(
        "dashboard.html",
        top_alliances=top_alliances,
        top_players=top_players,
        total_alliances=total_alliances,
        total_players=total_players,
        active_attacks=active_attacks,
        recent_alerts=recent_alerts,
        server_pop_trend=server_pop_trend,
        top_gainers=top_gainers,
        top_losers=top_losers,
    )
