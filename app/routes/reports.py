"""Reports panel — view and analyze parsed battle reports."""

import json

from flask import Blueprint, render_template, request, current_app, abort
from ..database import db
from ..models import BattleReport, AttackReport, Snapshot

bp = Blueprint("reports", __name__)


def _safe_json(text):
    """Parse JSON string, return empty dict on failure."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def _sum_troops(troops_dict):
    """Sum all troop counts."""
    return sum(troops_dict.values()) if troops_dict else 0


def _determine_result(report):
    """Determine battle result from report data."""
    if report.result:
        return report.result

    atk_troops = _safe_json(report.attacker_troops)
    atk_losses = _safe_json(report.attacker_losses)
    def_troops = _safe_json(report.defender_troops)
    def_losses = _safe_json(report.defender_losses)

    atk_total = _sum_troops(atk_troops)
    atk_lost = _sum_troops(atk_losses)
    def_total = _sum_troops(def_troops)
    def_lost = _sum_troops(def_losses)

    if def_total > 0 and def_lost >= def_total:
        return "przegrana_obrony"
    if atk_total > 0 and atk_lost >= atk_total:
        return "wygrana_obrony"
    if atk_lost == 0 and def_lost == 0:
        return "szpieg"
    return "remis"


@bp.route("/reports")
def report_list():
    """List all battle reports with filters."""
    page = request.args.get("page", 1, type=int)
    per_page = 25

    query = db.session.query(BattleReport).order_by(
        BattleReport.created_at.desc()
    )

    # Filter by attack report ID
    attack_id = request.args.get("attack_id", type=int)
    if attack_id:
        query = query.filter(BattleReport.attack_report_id == attack_id)

    # Filter by player name
    player = request.args.get("player", "").strip()
    if player:
        query = query.filter(
            db.or_(
                BattleReport.attacker_name.ilike(f"%{player}%"),
                BattleReport.defender_name.ilike(f"%{player}%"),
            )
        )

    total = query.count()
    reports = query.offset((page - 1) * per_page).limit(per_page).all()

    enriched = []
    for r in reports:
        atk_troops = _safe_json(r.attacker_troops)
        def_troops = _safe_json(r.defender_troops)
        result_code = _determine_result(r)

        enriched.append({
            "obj": r,
            "atk_total": _sum_troops(atk_troops),
            "def_total": _sum_troops(def_troops),
            "result": result_code,
        })

    total_pages = max(1, (total + per_page - 1) // per_page)

    latest_snapshot = (
        db.session.query(Snapshot).order_by(Snapshot.fetched_at.desc()).first()
    )
    server_url = current_app.config.get("TRAVIAN_SERVER_URL", "")

    return render_template(
        "reports.html",
        reports=enriched,
        total=total,
        page=page,
        total_pages=total_pages,
        attack_id=attack_id,
        player_filter=player,
        snapshot=latest_snapshot,
        server_url=server_url,
    )


@bp.route("/reports/<int:report_id>")
def report_detail(report_id):
    """Detailed view of a single battle report."""
    report = db.session.get(BattleReport, report_id)
    if report is None:
        abort(404)

    atk_troops = _safe_json(report.attacker_troops)
    atk_losses = _safe_json(report.attacker_losses)
    atk_trapped = _safe_json(report.attacker_trapped) if report.attacker_trapped else {}
    def_troops = _safe_json(report.defender_troops)
    def_losses = _safe_json(report.defender_losses)
    bounty = _safe_json(report.bounty)
    result_code = _determine_result(report)

    # Build troop tables: list of (name, sent, lost, trapped)
    atk_table = []
    all_atk_units = set(atk_troops.keys()) | set(atk_losses.keys())
    for name in all_atk_units:
        atk_table.append({
            "name": name,
            "sent": atk_troops.get(name, 0),
            "lost": atk_losses.get(name, 0),
            "trapped": atk_trapped.get(name, 0),
        })

    def_table = []
    all_def_units = set(def_troops.keys()) | set(def_losses.keys())
    for name in all_def_units:
        def_table.append({
            "name": name,
            "sent": def_troops.get(name, 0),
            "lost": def_losses.get(name, 0),
        })

    # Total resources from bounty
    bounty_total = sum(
        int(v) for v in bounty.values() if isinstance(v, (int, float))
        or (isinstance(v, str) and v.isdigit())
    ) if bounty else 0

    # Linked attack report
    linked_attack = None
    if report.attack_report_id:
        linked_attack = db.session.query(AttackReport).get(report.attack_report_id)

    latest_snapshot = (
        db.session.query(Snapshot).order_by(Snapshot.fetched_at.desc()).first()
    )
    server_url = current_app.config.get("TRAVIAN_SERVER_URL", "")

    return render_template(
        "report_detail.html",
        report=report,
        atk_table=atk_table,
        def_table=def_table,
        atk_troops_total=_sum_troops(atk_troops),
        atk_losses_total=_sum_troops(atk_losses),
        def_troops_total=_sum_troops(def_troops),
        def_losses_total=_sum_troops(def_losses),
        bounty=bounty,
        bounty_total=bounty_total,
        result=result_code,
        linked_attack=linked_attack,
        snapshot=latest_snapshot,
        server_url=server_url,
    )
