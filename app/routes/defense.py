"""Defense panel — view defense coordination threads."""

import json
from math import sqrt

from flask import Blueprint, render_template, request, current_app, abort
from sqlalchemy import func

from ..database import db
from ..models import (
    DefenseThread, VillageTroops, TroopSupport,
    AttackReport, BattleReport, Snapshot,
)

bp = Blueprint("defense", __name__)


def _safe_json(text):
    """Parse JSON string, return empty dict on failure."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def _sum_troops(troops_dict):
    """Sum all troop counts in a parsed troops dict."""
    return sum(troops_dict.values()) if troops_dict else 0


@bp.route("/defense")
def index():
    """List all defense threads with summary stats."""
    status_filter = request.args.get("status", "all")

    query = db.session.query(DefenseThread).order_by(
        DefenseThread.updated_at.desc()
    )

    if status_filter != "all":
        query = query.filter(DefenseThread.status == status_filter)

    threads = query.limit(100).all()

    # Stats
    total = db.session.query(DefenseThread).count()
    active = db.session.query(DefenseThread).filter(
        DefenseThread.status == "active"
    ).count()
    resolved = db.session.query(DefenseThread).filter(
        DefenseThread.status == "resolved"
    ).count()

    total_garrison_troops = 0
    total_support_troops = 0

    # Enrich threads with counts
    enriched = []
    for t in threads:
        attack_count = db.session.query(AttackReport).filter(
            AttackReport.forum_thread_id == t.forum_thread_id
        ).count()

        support_count = db.session.query(TroopSupport).filter(
            TroopSupport.forum_thread_id == t.forum_thread_id
        ).count()

        # Garrison troops matching defender coords
        garrisons = db.session.query(VillageTroops).filter(
            VillageTroops.village_x == t.defender_x,
            VillageTroops.village_y == t.defender_y,
        ).all()

        supports = db.session.query(TroopSupport).filter(
            TroopSupport.forum_thread_id == t.forum_thread_id
        ).all()

        garrison_crop = sum(g.crop_consumption or 0 for g in garrisons)
        support_crop = sum(s.crop_consumption or 0 for s in supports)
        total_crop = garrison_crop + support_crop

        garrison_troop_count = sum(
            _sum_troops(_safe_json(g.troops)) for g in garrisons
        )
        support_troop_count = sum(
            _sum_troops(_safe_json(s.troops)) for s in supports
        )

        total_garrison_troops += garrison_troop_count
        total_support_troops += support_troop_count

        # Latest activity: max of thread updated_at, latest attack, latest support
        last_activity = t.updated_at or t.created_at

        enriched.append({
            "obj": t,
            "attack_count": attack_count,
            "support_count": support_count,
            "total_crop": total_crop,
            "last_activity": last_activity,
        })

    latest_snapshot = (
        db.session.query(Snapshot).order_by(Snapshot.fetched_at.desc()).first()
    )
    server_url = current_app.config.get("TRAVIAN_SERVER_URL", "")

    return render_template(
        "defense.html",
        threads=enriched,
        status_filter=status_filter,
        total=total,
        active=active,
        resolved=resolved,
        total_garrison_troops=total_garrison_troops,
        total_support_troops=total_support_troops,
        snapshot=latest_snapshot,
        server_url=server_url,
    )


@bp.route("/defense/<int:thread_id>")
def detail(thread_id):
    """Single defense thread with full coordination view."""
    thread = db.session.query(DefenseThread).get(thread_id)
    if thread is None:
        abort(404)

    # Attacks linked by forum_thread_id
    attacks = (
        db.session.query(AttackReport)
        .filter(AttackReport.forum_thread_id == thread.forum_thread_id)
        .order_by(AttackReport.created_at.desc())
        .all()
    )

    # Garrison troops matching defender coordinates
    garrisons = (
        db.session.query(VillageTroops)
        .filter(
            VillageTroops.village_x == thread.defender_x,
            VillageTroops.village_y == thread.defender_y,
        )
        .order_by(VillageTroops.updated_at.desc())
        .all()
    )

    parsed_garrisons = []
    total_garrison_troops = 0
    total_garrison_crop = 0
    for g in garrisons:
        troops = _safe_json(g.troops)
        troop_count = _sum_troops(troops)
        total_garrison_troops += troop_count
        total_garrison_crop += g.crop_consumption or 0
        parsed_garrisons.append({
            "obj": g,
            "troops": troops,
            "troop_count": troop_count,
        })

    # Support troops linked by forum_thread_id
    supports = (
        db.session.query(TroopSupport)
        .filter(TroopSupport.forum_thread_id == thread.forum_thread_id)
        .order_by(TroopSupport.created_at.desc())
        .all()
    )

    parsed_supports = []
    total_support_troops = 0
    total_support_crop = 0
    for s in supports:
        troops = _safe_json(s.troops)
        troop_count = _sum_troops(troops)
        total_support_troops += troop_count
        total_support_crop += s.crop_consumption or 0
        parsed_supports.append({
            "obj": s,
            "troops": troops,
            "troop_count": troop_count,
        })

    # Battle reports linked by forum_thread_id
    reports = (
        db.session.query(BattleReport)
        .filter(BattleReport.forum_thread_id == thread.forum_thread_id)
        .order_by(BattleReport.created_at.desc())
        .all()
    )

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

    # Totals
    total_troops = total_garrison_troops + total_support_troops
    total_crop = total_garrison_crop + total_support_crop

    latest_snapshot = (
        db.session.query(Snapshot).order_by(Snapshot.fetched_at.desc()).first()
    )
    server_url = current_app.config.get("TRAVIAN_SERVER_URL", "")

    return render_template(
        "defense_detail.html",
        thread=thread,
        attacks=attacks,
        garrisons=parsed_garrisons,
        supports=parsed_supports,
        reports=parsed_reports,
        total_garrison_troops=total_garrison_troops,
        total_garrison_crop=total_garrison_crop,
        total_support_troops=total_support_troops,
        total_support_crop=total_support_crop,
        total_troops=total_troops,
        total_crop=total_crop,
        snapshot=latest_snapshot,
        server_url=server_url,
    )
