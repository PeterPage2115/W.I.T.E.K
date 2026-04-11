"""API endpoints for W.I.T.E.K Chrome extension data ingestion."""

import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, jsonify, request, current_app

from app.database import db

log = logging.getLogger(__name__)

bp = Blueprint("api_ext", __name__, url_prefix="/api/ext")

# --------------- Rate limiting (in-memory, per IP) --------------- #

_rate_limits: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()
_RATE_LIMIT = 30  # max requests per minute
_RATE_WINDOW = 60  # seconds
_CLEANUP_INTERVAL = 300  # purge stale entries every 5 min
_last_cleanup: float = 0.0


def _cleanup_stale_entries(now: float) -> None:
    """Remove IPs with no recent requests (called under lock)."""
    global _last_cleanup
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    cutoff = now - _RATE_WINDOW
    stale = [ip for ip, ts in _rate_limits.items() if not ts or ts[-1] < cutoff]
    for ip in stale:
        del _rate_limits[ip]


def check_rate_limit(ip: str) -> bool:
    """Return True if request is allowed, False if rate limit exceeded."""
    now = time.time()
    window = now - _RATE_WINDOW
    with _rate_lock:
        _cleanup_stale_entries(now)
        _rate_limits[ip] = [t for t in _rate_limits[ip] if t > window]
        if len(_rate_limits[ip]) >= _RATE_LIMIT:
            return False
        _rate_limits[ip].append(now)
        return True


def require_ext_token(f):
    """Decorator: require valid X-Witek-Token header + rate limit. Skips OPTIONS."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "OPTIONS":
            return jsonify({}), 204

        # Rate limit check (before token validation to protect against brute-force)
        ip = request.remote_addr or "unknown"
        if not check_rate_limit(ip):
            return jsonify({"error": "Rate limit exceeded"}), 429

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
    if request.method == "OPTIONS":
        return None
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

    # Extension sends "player" key; also support legacy "name" key
    atk_name = attacker.get("player") or attacker.get("name", "?")
    def_name = defender.get("player") or defender.get("name", "?")

    # Bounty lives inside attacker data (extension) or at top level (legacy)
    bounty_data = attacker.get("bounty") or data.get("bounty", {})

    report = BattleReport(
        reported_by_discord="extension",
        reported_by_name="Chrome Extension",
        attacker_name=atk_name,
        attacker_alliance=attacker.get("alliance", ""),
        attacker_village=attacker.get("village", ""),
        attacker_troops=json.dumps(attacker.get("troops", {})),
        attacker_losses=json.dumps(attacker.get("losses", {})),
        defender_name=def_name,
        defender_alliance=defender.get("alliance", ""),
        defender_village=defender.get("village", ""),
        defender_troops=json.dumps(defender.get("troops", {})),
        defender_losses=json.dumps(defender.get("losses", {})),
        bounty=json.dumps(bounty_data),
        battle_power_atk=data.get("battle_power_atk"),
        battle_power_def=data.get("battle_power_def"),
        kill_cost_atk=json.dumps(data.get("kill_cost_atk")) if data.get("kill_cost_atk") else None,
        kill_cost_def=json.dumps(data.get("kill_cost_def")) if data.get("kill_cost_def") else None,
        raw_text=json.dumps({"source": "extension", "report_id": data.get("report_id")}),
    )

    db.session.add(report)
    db.session.commit()

    log.info("Extension report saved: id=%s, att=%s vs def=%s",
             report.id, atk_name, def_name)

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
