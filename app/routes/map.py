"""Interactive 2D map of Travian world (S4.5)."""

from flask import Blueprint, render_template, jsonify, request, current_app
from ..models import Village
from ..snapshot_helpers import get_latest_snapshot

bp = Blueprint("map", __name__)


@bp.route("/map")
def map_view():
    """Render the map page."""
    our_alliances = current_app.config.get("TRAVIAN_OUR_ALLIANCES", [])
    return render_template("map.html", our_alliances=our_alliances)


@bp.route("/api/map/villages")
def api_villages():
    """JSON endpoint returning village data for the map.

    Query params:
    - x_min, x_max, y_min, y_max: bounding box filter (optional)
    - alliance: filter by alliance name (optional)
    - player: filter by player name (optional)
    """
    snapshot = get_latest_snapshot()
    if not snapshot:
        return jsonify([])

    query = Village.query.filter_by(snapshot_id=snapshot.id)

    x_min = request.args.get("x_min", type=int)
    x_max = request.args.get("x_max", type=int)
    y_min = request.args.get("y_min", type=int)
    y_max = request.args.get("y_max", type=int)

    if all(v is not None for v in [x_min, x_max, y_min, y_max]):
        query = query.filter(
            Village.x >= x_min,
            Village.x <= x_max,
            Village.y >= y_min,
            Village.y <= y_max,
        )

    alliance = request.args.get("alliance")
    if alliance:
        query = query.filter(Village.alliance_name.ilike(f"%{alliance}%"))

    player = request.args.get("player")
    if player:
        query = query.filter(Village.player_name.ilike(f"%{player}%"))

    villages = query.all()

    our_alliances = current_app.config.get("TRAVIAN_OUR_ALLIANCES", [])

    result = []
    for v in villages:
        entry = {
            "x": v.x,
            "y": v.y,
            "name": v.name,
            "player": v.player_name,
            "alliance": v.alliance_name,
            "aid": v.aid,
            "pop": v.population,
            "tid": v.tid,
            "is_ours": v.aid in our_alliances if v.aid else False,
        }
        if v.is_capital:
            entry["is_capital"] = True
        if v.is_city:
            entry["is_city"] = True
        if v.has_harbor:
            entry["has_harbor"] = True
        if v.region:
            entry["region"] = v.region
        if v.victory_points:
            entry["vp"] = v.victory_points
        result.append(entry)

    return jsonify(result)
