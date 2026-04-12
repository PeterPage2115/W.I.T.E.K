"""Quick-search API for players and alliances."""

from flask import Blueprint, request, jsonify

from ..database import db
from ..models import Player, Alliance

bp = Blueprint("search", __name__)


def _escape_like(s: str) -> str:
    """Escape SQL LIKE wildcard characters."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@bp.route("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"players": [], "alliances": []})

    safe_q = _escape_like(q)
    players = (
        db.session.query(Player.uid, Player.name, Player.alliance_name, Player.total_pop)
        .filter(Player.name.ilike(f"%{safe_q}%", escape="\\"))
        .order_by(Player.total_pop.desc())
        .limit(5)
        .all()
    )
    alliances = (
        db.session.query(Alliance.aid, Alliance.name, Alliance.member_count, Alliance.total_pop)
        .filter(Alliance.name.ilike(f"%{safe_q}%", escape="\\"))
        .order_by(Alliance.total_pop.desc())
        .limit(5)
        .all()
    )

    return jsonify({
        "players": [
            {"uid": p.uid, "name": p.name, "alliance": p.alliance_name, "pop": p.total_pop}
            for p in players
        ],
        "alliances": [
            {"aid": a.aid, "name": a.name, "members": a.member_count, "pop": a.total_pop}
            for a in alliances
        ],
    })
