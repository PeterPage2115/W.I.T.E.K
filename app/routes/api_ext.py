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


# --------------- Input validation helpers --------------- #

def _validate_coords(x, y):
    """Validate Travian map coordinates. Returns (x, y) as ints or raises ValueError."""
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise ValueError(f"Coordinates must be numbers, got x={type(x).__name__}, y={type(y).__name__}")
    x, y = int(x), int(y)
    if not (-200 <= x <= 200) or not (-200 <= y <= 200):
        raise ValueError(f"Coordinates out of bounds: ({x}|{y}), must be -200..200")
    return x, y


def _validate_troops(troops, field_name="troops"):
    """Validate troops dict. Returns cleaned dict or raises ValueError."""
    if not isinstance(troops, dict):
        raise ValueError(f"{field_name} must be a dict, got {type(troops).__name__}")
    cleaned = {}
    for k, v in troops.items():
        if not isinstance(k, str):
            raise ValueError(f"Troop key must be string, got {type(k).__name__}")
        if not isinstance(v, (int, float)):
            raise ValueError(f"Troop count for '{k}' must be a number, got {type(v).__name__}")
        cleaned[str(k)] = int(v)
    return cleaned


def _validate_side(data, side_name):
    """Validate attacker/defender dict. Returns cleaned dict or raises ValueError."""
    if not isinstance(data, dict):
        raise ValueError(f"{side_name} must be a dict, got {type(data).__name__}")
    for key in ("name", "player", "alliance", "village"):
        if key in data and not isinstance(data[key], (str, type(None))):
            raise ValueError(f"{side_name}.{key} must be string")
    for key in ("troops", "losses"):
        if key in data:
            data[key] = _validate_troops(data[key], f"{side_name}.{key}")
    return data

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
    """Allow requests from Chrome extension and Travian domains."""
    origin = request.headers.get("Origin", "")
    allowed_patterns = [
        "chrome-extension://",
        ".travian.com",
    ]
    if any(p in origin for p in allowed_patterns) or not origin:
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
    else:
        response.headers["Access-Control-Allow-Origin"] = "null"
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

    try:
        attacker = _validate_side(data["attacker"], "attacker")
        defender = _validate_side(data["defender"], "defender")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    from app.models import BattleReport

    # Extension sends "player" key; also support legacy "name" key
    atk_name = attacker.get("player") or attacker.get("name", "?")
    def_name = defender.get("player") or defender.get("name", "?")

    atk_village = attacker.get("village", "")
    def_village = defender.get("village", "")
    atk_troops_json = json.dumps(attacker.get("troops", {}))
    def_troops_json = json.dumps(defender.get("troops", {}))

    # Duplicate check: same players, villages, and troop compositions
    existing = BattleReport.query.filter_by(
        attacker_name=atk_name,
        defender_name=def_name,
        attacker_village=atk_village,
        defender_village=def_village,
        attacker_troops=atk_troops_json,
        defender_troops=def_troops_json,
    ).first()

    if existing:
        log.info("Duplicate battle report detected: id=%s, att=%s vs def=%s",
                 existing.id, atk_name, def_name)
        return jsonify({"ok": True, "report_id": existing.id, "status": "duplicate"}), 200

    # Bounty lives inside attacker data (extension) or at top level (legacy)
    bounty_data = attacker.get("bounty") or data.get("bounty", {})

    report = BattleReport(
        reported_by_discord="extension",
        reported_by_name="Chrome Extension",
        attacker_name=atk_name,
        attacker_alliance=attacker.get("alliance", ""),
        attacker_village=atk_village,
        attacker_troops=atk_troops_json,
        attacker_losses=json.dumps(attacker.get("losses", {})),
        defender_name=def_name,
        defender_alliance=defender.get("alliance", ""),
        defender_village=def_village,
        defender_troops=def_troops_json,
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

    return jsonify({"ok": True, "report_id": report.id, "status": "created"}), 201


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

    try:
        x, y = _validate_coords(data["x"], data["y"])
        troops = _validate_troops(data["troops"])
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

    from app.models import VillageTroops

    troops_json = json.dumps(troops)

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


@bp.route("/spy-report", methods=["POST", "OPTIONS"])
@require_ext_token
def receive_spy_report():
    """Receive spy report data from extension.

    Expected JSON:
    {
        "server_url": "https://ts31...",
        "target_player": "PlayerName",
        "target_village": "VillageName",
        "x": 76, "y": 43,
        "spy_type": "resources" | "troops" | "both",
        "resources": {"lumber": 1000, "clay": 500, "iron": 300, "crop": 2000},
        "troops": {"1": 100, "2": 50},
        "defense_buildings": {"wall": 10, "palace": 5}
    }
    """
    data = request.get_json()

    for field in ["x", "y", "spy_type"]:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    spy_type = data["spy_type"]
    if spy_type not in ("resources", "troops", "both"):
        return jsonify({"error": "spy_type must be one of: resources, troops, both"}), 400

    try:
        x, y = _validate_coords(data["x"], data["y"])
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

    troops = None
    if data.get("troops"):
        try:
            troops = _validate_troops(data["troops"])
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    defense_buildings = None
    if data.get("defense_buildings"):
        if not isinstance(data["defense_buildings"], dict):
            return jsonify({"error": "defense_buildings must be a dict"}), 400
        defense_buildings = data["defense_buildings"]

    resources = data.get("resources", {})
    if not isinstance(resources, dict):
        return jsonify({"error": "resources must be a dict"}), 400

    from app.models import SpyReport

    troops_json = json.dumps(troops) if troops else None

    # Duplicate check: same target, spy type, resources, and troops
    existing = SpyReport.query.filter_by(
        target_x=x,
        target_y=y,
        spy_type=spy_type,
        resources_lumber=resources.get("lumber"),
        resources_clay=resources.get("clay"),
        resources_iron=resources.get("iron"),
        resources_crop=resources.get("crop"),
        troops=troops_json,
    ).first()

    if existing:
        log.info("Duplicate spy report detected: id=%s, target=(%s|%s)",
                 existing.id, x, y)
        return jsonify({"ok": True, "report_id": existing.id, "status": "duplicate"}), 200

    report = SpyReport(
        spy_type=spy_type,
        target_player=data.get("target_player"),
        target_village=data.get("target_village"),
        target_x=x,
        target_y=y,
        resources_lumber=resources.get("lumber"),
        resources_clay=resources.get("clay"),
        resources_iron=resources.get("iron"),
        resources_crop=resources.get("crop"),
        troops=troops_json,
        defense_buildings=json.dumps(defense_buildings) if defense_buildings else None,
        submitted_by="extension",
    )

    db.session.add(report)
    db.session.commit()

    log.info("Extension spy report saved: id=%s, target=(%s|%s) %s",
             report.id, x, y, data.get("target_player", "?"))

    return jsonify({"ok": True, "report_id": report.id, "status": "created"}), 201


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

    try:
        x, y = _validate_coords(data["x"], data["y"])
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

    if not isinstance(data.get("incoming"), list):
        return jsonify({"error": "incoming must be a list"}), 400

    for i, inc in enumerate(data["incoming"]):
        if not isinstance(inc, dict):
            return jsonify({"error": f"incoming[{i}] must be a dict"}), 400
        if "from_x" in inc and "from_y" in inc:
            try:
                inc["from_x"], inc["from_y"] = _validate_coords(inc["from_x"], inc["from_y"])
            except ValueError as e:
                return jsonify({"error": f"incoming[{i}]: {e}"}), 400

    from app.models import AttackReport
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


_VALID_GAME_DATA_TYPES = {"hero", "marketplace", "training"}


@bp.route("/game-data", methods=["POST", "OPTIONS"])
@require_ext_token
def receive_game_data():
    """Receive generic game data from extension (hero, marketplace, training).

    Expected JSON:
    {
        "type": "hero" | "marketplace" | "training",
        "data": { ... },
        "server_url": "https://ts31..."
    }
    """
    data = request.get_json()

    data_type = data.get("type")
    if not data_type or data_type not in _VALID_GAME_DATA_TYPES:
        return jsonify({"error": f"type must be one of: {', '.join(sorted(_VALID_GAME_DATA_TYPES))}"}), 400

    payload = data.get("data")
    if not isinstance(payload, dict):
        return jsonify({"error": "data must be a dict"}), 400

    from app.models import GameData

    entry = GameData(
        data_type=data_type,
        data=json.dumps(payload),
        server_url=data.get("server_url"),
    )

    db.session.add(entry)
    db.session.commit()

    log.info("Extension game-data saved: id=%s, type=%s", entry.id, data_type)

    return jsonify({"ok": True, "id": entry.id}), 201
