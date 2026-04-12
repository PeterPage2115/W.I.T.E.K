"""Blueprint: /alerts dashboard — history and filtering of all alert types."""

import json
import math

from flask import Blueprint, render_template, request
from ..database import db
from ..models import Alert

bp = Blueprint("alerts_web", __name__)

ALERT_META = {
    "pop_drop": {"icon": "🔻", "label": "Spadek populacji"},
    "new_village": {"icon": "🏘️", "label": "Nowa wioska"},
    "alliance_change": {"icon": "🔄", "label": "Zmiana sojuszu"},
}

POLISH_MONTHS = {
    1: "sty", 2: "lut", 3: "mar", 4: "kwi", 5: "maj", 6: "cze",
    7: "lip", 8: "sie", 9: "wrz", 10: "paź", 11: "lis", 12: "gru",
}

PER_PAGE = 25


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _format_timestamp(dt):
    if dt is None:
        return "—"
    m = POLISH_MONTHS.get(dt.month, str(dt.month))
    return f"{dt.day} {m} {dt.year}, {dt.strftime('%H:%M')}"


def _format_details(alert_type, data):
    if alert_type == "pop_drop":
        old = data.get("old_pop", "?")
        new = data.get("new_pop", "?")
        pct = data.get("drop_pct", "?")
        if isinstance(pct, float):
            pct = f"{pct:.1f}"
        return f"{old} → {new} (-{pct}%)"
    elif alert_type == "new_village":
        x = data.get("x", "?")
        y = data.get("y", "?")
        dist = data.get("distance", "?")
        if isinstance(dist, float):
            dist = f"{dist:.1f}"
        return f"({x}|{y}) dist: {dist}"
    elif alert_type == "alliance_change":
        old_a = data.get("old_alliance_name", "—") or "—"
        new_a = data.get("new_alliance_name", "—") or "—"
        ct = data.get("change_type", "")
        return f"{old_a} → {new_a} ({ct})"
    return "—"


@bp.route("/alerts")
def alerts_list():
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    type_filter = request.args.get("type", "").strip()
    search = request.args.get("search", "").strip()

    query = Alert.query

    if type_filter in ALERT_META:
        query = query.filter(Alert.alert_type == type_filter)

    if search:
        escaped = _escape_like(search)
        query = query.filter(Alert.data.like(f"%{escaped}%", escape="\\"))

    total = query.count()
    total_pages = max(1, math.ceil(total / PER_PAGE))
    if page > total_pages:
        page = total_pages

    alerts_raw = (
        query.order_by(Alert.created_at.desc())
        .offset((page - 1) * PER_PAGE)
        .limit(PER_PAGE)
        .all()
    )

    alerts = []
    for a in alerts_raw:
        try:
            data = json.loads(a.data) if a.data else {}
        except (json.JSONDecodeError, TypeError):
            data = {}

        meta = ALERT_META.get(a.alert_type, {"icon": "❓", "label": a.alert_type or "?"})
        alerts.append({
            "id": a.id,
            "type": a.alert_type,
            "icon": meta["icon"],
            "label": meta["label"],
            "player_name": data.get("player_name", "—"),
            "details": _format_details(a.alert_type, data),
            "timestamp": _format_timestamp(a.created_at),
            "notified": a.notified,
        })

    return render_template(
        "alerts.html",
        alerts=alerts,
        page=page,
        total=total,
        total_pages=total_pages,
        type_filter=type_filter,
        search=search,
        alert_types=ALERT_META,
    )
