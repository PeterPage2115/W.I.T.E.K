"""Dashboard route — main page."""

from flask import Blueprint, render_template
from sqlalchemy import func
from ..database import db
from ..models import Snapshot, Alliance, Player, AttackReport

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    latest_snapshot = (
        db.session.query(Snapshot).order_by(Snapshot.fetched_at.desc()).first()
    )

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

    return render_template(
        "dashboard.html",
        snapshot=latest_snapshot,
        top_alliances=top_alliances,
        top_players=top_players,
        total_alliances=total_alliances,
        total_players=total_players,
        active_attacks=active_attacks,
    )
