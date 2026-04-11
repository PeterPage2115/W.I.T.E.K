"""Attack panel — view and manage attack reports."""

import json
from math import sqrt

from flask import Blueprint, render_template, request, current_app, abort
from ..database import db
from ..models import AttackReport, DefenseThread, TroopSupport, BattleReport, Snapshot
from . import paginate_query

bp = Blueprint("attacks", __name__)


def _torus_distance(x1, y1, x2, y2, map_size=401):
    dx = abs(x1 - x2)
    dy = abs(y1 - y2)
    dx = min(dx, map_size - dx)
    dy = min(dy, map_size - dy)
    return sqrt(dx**2 + dy**2)


def _safe_json(text):
    """Parse JSON string, return empty dict on failure."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


@bp.route("/attacks")
def index():
    """Show all attack reports, newest first. Filter by status."""
    status_filter = request.args.get("status", "all")

    query = db.session.query(AttackReport).order_by(AttackReport.created_at.desc())

    if status_filter != "all":
        query = query.filter(AttackReport.status == status_filter)

    page = request.args.get("page", 1, type=int)
    attacks, pagination = paginate_query(query, page=page, per_page=25)

    total = db.session.query(AttackReport).count()
    active = db.session.query(AttackReport).filter(
        AttackReport.status != "resolved"
    ).count()
    resolved = db.session.query(AttackReport).filter(
        AttackReport.status == "resolved"
    ).count()

    latest_snapshot = (
        db.session.query(Snapshot).order_by(Snapshot.fetched_at.desc()).first()
    )
    server_url = current_app.config.get("TRAVIAN_SERVER_URL", "")

    extra_args = {}
    if status_filter != "all":
        extra_args["status"] = status_filter

    return render_template(
        "attacks.html",
        attacks=attacks,
        pagination=pagination,
        status_filter=status_filter,
        total=total,
        active=active,
        resolved=resolved,
        snapshot=latest_snapshot,
        server_url=server_url,
        extra_args=extra_args,
    )


@bp.route("/attacks/<int:attack_id>")
def detail(attack_id):
    """Show single attack with full details, defense responses, battle reports."""
    attack = db.session.query(AttackReport).get(attack_id)
    if attack is None:
        abort(404)

    support = (
        db.session.query(TroopSupport)
        .filter(TroopSupport.attack_report_id == attack_id)
        .order_by(TroopSupport.created_at.desc())
        .all()
    )

    reports = (
        db.session.query(BattleReport)
        .filter(BattleReport.attack_report_id == attack_id)
        .order_by(BattleReport.created_at.desc())
        .all()
    )

    thread = None
    if attack.forum_thread_id:
        thread = (
            db.session.query(DefenseThread)
            .filter(DefenseThread.forum_thread_id == attack.forum_thread_id)
            .first()
        )

    # Pre-parse JSON fields for troops
    parsed_support = []
    for s in support:
        parsed_support.append({
            "obj": s,
            "troops": _safe_json(s.troops),
        })

    parsed_reports = []
    for r in reports:
        parsed_reports.append({
            "obj": r,
            "attacker_troops": _safe_json(r.attacker_troops),
            "attacker_losses": _safe_json(r.attacker_losses),
            "defender_troops": _safe_json(r.defender_troops),
            "defender_losses": _safe_json(r.defender_losses),
            "bounty": _safe_json(r.bounty),
        })

    # Calculate distance if both coords available
    distance = None
    if (
        attack.attacker_x is not None
        and attack.attacker_y is not None
        and attack.defender_x is not None
        and attack.defender_y is not None
    ):
        map_size = current_app.config.get("TRAVIAN_MAP_SIZE", 401)
        distance = _torus_distance(
            attack.attacker_x, attack.attacker_y,
            attack.defender_x, attack.defender_y,
            map_size,
        )

    latest_snapshot = (
        db.session.query(Snapshot).order_by(Snapshot.fetched_at.desc()).first()
    )
    server_url = current_app.config.get("TRAVIAN_SERVER_URL", "")

    return render_template(
        "attack_detail.html",
        attack=attack,
        support=parsed_support,
        reports=parsed_reports,
        thread=thread,
        distance=distance,
        snapshot=latest_snapshot,
        server_url=server_url,
    )
