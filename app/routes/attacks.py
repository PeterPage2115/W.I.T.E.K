"""Attack panel — view and manage attack reports."""

import csv
import io
import json
from math import sqrt

from flask import Blueprint, render_template, request, current_app, abort, Response
from ..auth_utils import login_required, role_required
from ..database import db
from ..models import AttackReport, DefenseThread, TroopSupport, BattleReport
from . import paginate_query

bp = Blueprint("attacks", __name__)


def _torus_distance(x1, y1, x2, y2, map_size=401, wrap=True):
    """wrap=True: torus distance; wrap=False: flat Euclidean (RoF servers)."""
    dx = abs(x1 - x2)
    dy = abs(y1 - y2)
    if wrap:
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
        features = current_app.config.get("TRAVIAN_FEATURES", {})
        wrap = features.get("map_edge_wrapping", True)
        distance = _torus_distance(
            attack.attacker_x, attack.attacker_y,
            attack.defender_x, attack.defender_y,
            map_size, wrap=wrap,
        )

    server_url = current_app.config.get("TRAVIAN_SERVER_URL", "")

    return render_template(
        "attack_detail.html",
        attack=attack,
        support=parsed_support,
        reports=parsed_reports,
        thread=thread,
        distance=distance,
        server_url=server_url,
    )


@bp.route("/attacks/export")
@login_required
@role_required("leader", "officer")
def export_csv():
    """Export all attack reports as CSV."""
    attacks = (
        db.session.query(AttackReport)
        .order_by(AttackReport.created_at.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Zgłaszający", "Atakujący", "Sojusz atakującego",
        "Obrońca", "Wioska obrońcy", "X obrońcy", "Y obrońcy",
        "Czas ataku", "Notatki", "Status", "Data zgłoszenia",
    ])
    for a in attacks:
        writer.writerow([
            a.id,
            a.reported_by_name or "",
            a.attacker_name or "",
            a.attacker_alliance or "",
            a.defender_name or "",
            a.defender_village or "",
            a.defender_x if a.defender_x is not None else "",
            a.defender_y if a.defender_y is not None else "",
            a.attack_time or "",
            a.notes or "",
            a.status or "",
            a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=ataki_eksport.csv",
        },
    )
