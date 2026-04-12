"""Reports panel — view and analyze parsed battle reports."""

import csv
import io
import json

from flask import Blueprint, render_template, request, current_app, abort, Response
from ..auth_utils import login_required
from ..database import db
from ..models import BattleReport, AttackReport, SpyReport

bp = Blueprint("reports", __name__)


# ── Unit ID → name mapping ──────────────────────────────────
# Travian unit IDs: Romans 1-10, Teutons 11-20, Gauls 21-30,
# Nature 31-40, Natars 41-50, Egyptians 51-60, Huns 61-70,
# Vikings 71-80, Spartans 81-90
_UNIT_NAMES: dict[str, str] = {}


def _build_unit_names() -> dict[str, str]:
    """Build unit ID → name mapping from tribes.py."""
    try:
        from bot.tribes import TRIBES
        names = {"hero": "Bohater"}
        for tid, tribe in TRIBES.items():
            base = (tid - 1) * 10 if tid <= 5 else (tid - 1) * 10  # tid 6-9 skip 4,5
            # Actual Travian numbering: tid=1→1-10, tid=2→11-20, tid=3→21-30,
            # tid=4(nature)→31-40, tid=5(natars)→41-50,
            # tid=6→51-60, tid=7→61-70, tid=8→71-80, tid=9→81-90
            if tid <= 3:
                base = (tid - 1) * 10
            elif tid == 6:
                base = 50
            elif tid == 7:
                base = 60
            elif tid == 8:
                base = 70
            elif tid == 9:
                base = 80
            else:
                continue
            for i, unit in enumerate(tribe.units):
                unit_id = str(base + i + 1)
                names[unit_id] = unit.name
        return names
    except Exception:
        return {"hero": "Bohater"}


def _get_unit_name(unit_id: str) -> str:
    """Get human-readable unit name for a Travian unit ID."""
    global _UNIT_NAMES
    if not _UNIT_NAMES:
        _UNIT_NAMES = _build_unit_names()
    return _UNIT_NAMES.get(unit_id, f"Jednostka #{unit_id}")


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

    server_url = current_app.config.get("TRAVIAN_SERVER_URL", "")

    return render_template(
        "reports.html",
        reports=enriched,
        total=total,
        page=page,
        total_pages=total_pages,
        attack_id=attack_id,
        player_filter=player,
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
    for uid in all_atk_units:
        atk_table.append({
            "name": _get_unit_name(uid),
            "sent": atk_troops.get(uid, 0),
            "lost": atk_losses.get(uid, 0),
            "trapped": atk_trapped.get(uid, 0),
        })

    def_table = []
    all_def_units = set(def_troops.keys()) | set(def_losses.keys())
    for uid in all_def_units:
        def_table.append({
            "name": _get_unit_name(uid),
            "sent": def_troops.get(uid, 0),
            "lost": def_losses.get(uid, 0),
        })

    # Total resources from bounty (only actual resources, not carry)
    _RESOURCE_KEYS = {"lumber", "wood", "clay", "iron", "crop"}
    bounty_total = sum(
        int(v) for k, v in bounty.items()
        if k in _RESOURCE_KEYS and isinstance(v, (int, float))
        or (isinstance(v, str) and v.isdigit())
    ) if bounty else 0

    # Linked attack report
    linked_attack = None
    if report.attack_report_id:
        linked_attack = db.session.query(AttackReport).get(report.attack_report_id)

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
        server_url=server_url,
    )


@bp.route("/reports/spy")
@login_required
def spy_report_list():
    """List spy reports."""
    page = request.args.get("page", 1, type=int)
    per_page = 25

    query = db.session.query(SpyReport).order_by(SpyReport.submitted_at.desc())

    player = request.args.get("player", "").strip()
    if player:
        query = query.filter(SpyReport.target_player.ilike(f"%{player}%"))

    spy_type = request.args.get("spy_type", "").strip()
    if spy_type in ("resources", "troops", "both"):
        query = query.filter(SpyReport.spy_type == spy_type)

    total = query.count()
    reports = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)

    enriched = []
    for r in reports:
        troops = _safe_json(r.troops)
        buildings = _safe_json(r.defense_buildings)
        total_res = sum(v or 0 for v in [
            r.resources_lumber, r.resources_clay, r.resources_iron, r.resources_crop
        ])
        enriched.append({
            "obj": r,
            "total_res": total_res,
            "troop_count": _sum_troops(troops),
            "wall_level": buildings.get("wall"),
        })

    server_url = current_app.config.get("TRAVIAN_SERVER_URL", "")

    return render_template(
        "spy_reports.html",
        reports=enriched,
        total=total,
        page=page,
        total_pages=total_pages,
        player_filter=player,
        spy_type_filter=spy_type,
        server_url=server_url,
    )

@bp.route("/reports/export")
@login_required
def export_csv():
    """Export all battle reports as CSV."""
    reports = (
        db.session.query(BattleReport)
        .order_by(BattleReport.created_at.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Typ", "Atakujący", "Sojusz atakującego",
        "Obrońca", "Sojusz obrońcy", "Wioska atakującego",
        "Wioska obrońcy", "Straty atakującego", "Straty obrońcy",
        "Łupy", "Wynik", "Zgłaszający", "Data",
    ])
    for r in reports:
        writer.writerow([
            r.id,
            r.result or "",
            r.attacker_name or "",
            r.attacker_alliance or "",
            r.defender_name or "",
            r.defender_alliance or "",
            r.attacker_village or "",
            r.defender_village or "",
            r.attacker_losses or "",
            r.defender_losses or "",
            r.bounty or "",
            r.result or "",
            r.reported_by_name or "",
            r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=raporty_eksport.csv",
        },
    )
