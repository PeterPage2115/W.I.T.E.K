"""API endpoints for WITEK Chrome extension data ingestion."""

import json
import logging
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, jsonify, request, current_app

from app.database import db

log = logging.getLogger(__name__)

bp = Blueprint("api_ext", __name__, url_prefix="/api/ext")


def require_ext_token(f):
    """Decorator: require valid X-Witek-Token header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Witek-Token", "")
        expected = current_app.config.get("EXT_API_TOKEN", "")
        if not expected:
            return jsonify({"error": "Extension API not configured"}), 503
        if token != expected:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


@bp.before_request
def check_json():
    if request.method == "POST" and not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415


@bp.after_request
def add_cors(response):
    """Allow requests from Chrome extension."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Witek-Token"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


@bp.route("/report", methods=["POST", "OPTIONS"])
@require_ext_token
def receive_report():
    """Receive battle report data from extension.

    Expected JSON:
    {
        "server_url": "https://ts31...",
        "report_id": 12345,
        "attacker": {"name": "...", "troops": {"1": 100}, "losses": {"1": 30}},
        "defender": {"name": "...", "troops": {"1": 200}, "losses": {"1": 80}},
        "bounty": {"wood": 1000, "clay": 500, "iron": 300, "crop": 2000}
    }
    """
    data = request.get_json()

    required = ["attacker", "defender"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    attacker = data["attacker"]
    defender = data["defender"]

    from app.models import BattleReport

    report = BattleReport(
        reported_by_discord="extension",
        reported_by_name="Chrome Extension",
        attacker_name=attacker.get("name", "?"),
        attacker_troops=json.dumps(attacker.get("troops", {})),
        attacker_losses=json.dumps(attacker.get("losses", {})),
        defender_name=defender.get("name", "?"),
        defender_troops=json.dumps(defender.get("troops", {})),
        defender_losses=json.dumps(defender.get("losses", {})),
        bounty=json.dumps(data.get("bounty", {})),
        raw_text=json.dumps({"source": "extension", "report_id": data.get("report_id")}),
    )

    db.session.add(report)
    db.session.commit()

    log.info("Extension report saved: id=%s, att=%s vs def=%s",
             report.id, attacker.get("name"), defender.get("name"))

    return jsonify({"ok": True, "report_id": report.id}), 201


@bp.route("/troops", methods=["POST", "OPTIONS"])
@require_ext_token
def receive_troops():
    """Receive troop data from extension.

    Expected JSON:
    {
        "server_url": "https://ts31...",
        "x": 76, "y": 43,
        "village_name": "Wioska",
        "troops": {"1": 500, "2": 100}
    }
    """
    data = request.get_json()

    for field in ["x", "y", "troops"]:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    from app.models import VillageTroops

    x, y = data["x"], data["y"]
    troops_json = json.dumps(data["troops"])

    existing = VillageTroops.query.filter_by(village_x=x, village_y=y).first()
    if existing:
        existing.troops = troops_json
        existing.updated_at = datetime.now(timezone.utc)
        if data.get("village_name"):
            existing.village_name = data["village_name"]
    else:
        vt = VillageTroops(
            village_x=x,
            village_y=y,
            village_name=data.get("village_name"),
            player_discord_id="extension",
            troops=troops_json,
        )
        db.session.add(vt)

    db.session.commit()

    log.info("Extension troops saved: (%s|%s) %s", x, y, data.get("village_name", "?"))

    return jsonify({"ok": True, "village": f"({x}|{y})"}), 200


@bp.route("/incoming", methods=["POST", "OPTIONS"])
@require_ext_token
def receive_incoming():
    """Receive incoming attack data from extension.

    Expected JSON:
    {
        "server_url": "https://ts31...",
        "x": 76, "y": 43,
        "incoming": [
            {"type": "attack", "from_x": 10, "from_y": -5,
             "arrival_unix": 1712764800, "player_name": "Enemy"}
        ]
    }
    """
    data = request.get_json()

    for field in ["x", "y", "incoming"]:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    from app.models import AttackReport

    x, y = data["x"], data["y"]
    created = []

    for inc in data["incoming"]:
        report = AttackReport(
            reported_by_discord="extension",
            reported_by_name="Chrome Extension",
            attacker_name=inc.get("player_name"),
            attacker_x=inc.get("from_x"),
            attacker_y=inc.get("from_y"),
            defender_x=x,
            defender_y=y,
            attack_unix=inc.get("arrival_unix"),
            status="reported",
        )
        db.session.add(report)
        db.session.flush()
        created.append(report.id)

    db.session.commit()

    log.info("Extension incoming: %d attacks on (%s|%s)", len(created), x, y)

    return jsonify({"ok": True, "created": created}), 201
