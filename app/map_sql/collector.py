"""Fetch map.sql from Travian server and store snapshots in DB."""

import json
import logging
import time
import requests
from datetime import datetime, timezone

from ..database import db
from ..models import Snapshot, Village, Player, Alliance, Alert
from .parser import parse_map_sql
from .alerts import detect_alerts, is_stale_pair

logger = logging.getLogger(__name__)


def fetch_map_sql(server_url: str) -> str:
    """Download map.sql from the Travian server."""
    url = f"{server_url.rstrip('/')}/map.sql"
    logger.info("Fetching map.sql from %s", url)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def store_snapshot(raw_text: str) -> Snapshot:
    """Parse map.sql text and store a new snapshot in the database."""
    rows = parse_map_sql(raw_text)
    logger.info("Parsed %d villages from map.sql", len(rows))

    snapshot = Snapshot(
        fetched_at=datetime.now(timezone.utc),
        village_count=len(rows),
    )
    db.session.add(snapshot)
    db.session.flush()  # get snapshot.id

    # Bulk insert villages
    villages = [
        Village(
            map_id=r.map_id,
            snapshot_id=snapshot.id,
            x=r.x,
            y=r.y,
            tid=r.tid,
            vid=r.vid,
            name=r.name,
            uid=r.uid,
            player_name=r.player_name,
            aid=r.aid,
            alliance_name=r.alliance_name,
            population=r.population,
        )
        for r in rows
    ]
    db.session.bulk_save_objects(villages)

    # Update player aggregates
    _update_players(rows, snapshot.fetched_at)
    _update_alliances(rows, snapshot.fetched_at)

    db.session.commit()
    logger.info("Stored snapshot #%d with %d villages", snapshot.id, len(rows))
    return snapshot


def _update_players(rows, now):
    """Update player aggregates from parsed village rows."""
    player_data = {}
    for r in rows:
        if r.uid == 0:
            continue
        if r.uid not in player_data:
            player_data[r.uid] = {
                "name": r.player_name,
                "tid": r.tid,
                "aid": r.aid,
                "alliance_name": r.alliance_name,
                "total_pop": 0,
                "village_count": 0,
            }
        player_data[r.uid]["total_pop"] += r.population
        player_data[r.uid]["village_count"] += 1

    for uid, data in player_data.items():
        player = db.session.get(Player, uid)
        if player is None:
            player = Player(uid=uid, first_seen_at=now, **data)
            db.session.add(player)
        else:
            for key, val in data.items():
                setattr(player, key, val)
            player.last_updated_at = now


def _update_alliances(rows, now):
    """Update alliance aggregates from parsed village rows."""
    alliance_data = {}
    alliance_players = {}
    for r in rows:
        if r.aid == 0:
            continue
        if r.aid not in alliance_data:
            alliance_data[r.aid] = {"name": r.alliance_name, "total_pop": 0}
            alliance_players[r.aid] = set()
        alliance_data[r.aid]["total_pop"] += r.population
        alliance_players[r.aid].add(r.uid)

    for aid, data in alliance_data.items():
        alliance = db.session.get(Alliance, aid)
        if alliance is None:
            alliance = Alliance(
                aid=aid,
                name=data["name"],
                total_pop=data["total_pop"],
                member_count=len(alliance_players[aid]),
                first_seen_at=now,
            )
            db.session.add(alliance)
        else:
            alliance.name = data["name"]
            alliance.total_pop = data["total_pop"]
            alliance.member_count = len(alliance_players[aid])
            alliance.last_updated_at = now


def collect_and_store(app):
    """Full pipeline: fetch map.sql → parse → store → detect alerts."""
    with app.app_context():
        try:
            t_start = time.monotonic()
            raw = fetch_map_sql(app.config["TRAVIAN_SERVER_URL"])
            t_fetch = time.monotonic()

            snapshot = store_snapshot(raw)
            t_store = time.monotonic()

            logger.info(
                "Kolekcja zakończona: snapshot #%d, %d wiosek "
                "(fetch: %.1fs, store: %.1fs, razem: %.1fs)",
                snapshot.id, snapshot.village_count,
                t_fetch - t_start, t_store - t_fetch, t_store - t_start,
            )

            _run_alert_detection(app, snapshot)
            return snapshot
        except Exception:
            logger.exception("Failed to collect map.sql data")
            db.session.rollback()
            return None


def _run_alert_detection(app, new_snapshot):
    """Porównaj nowy snapshot z poprzednim i zapisz alerty."""
    try:
        prev_snapshot = (
            Snapshot.query
            .filter(Snapshot.id < new_snapshot.id)
            .order_by(Snapshot.id.desc())
            .first()
        )
        if prev_snapshot is None:
            logger.info("Brak poprzedniego snapshotu — pomijam detekcję alertów")
            return

        # Staleness guard: skip alerts if gap is too large (e.g. after downtime)
        max_gap = app.config.get("FETCH_INTERVAL_MINUTES", 60) * 2
        if is_stale_pair(new_snapshot.id, prev_snapshot.id, max_gap):
            logger.warning(
                "Pomijam detekcję alertów — snapshoty #%d → #%d zbyt oddalone",
                prev_snapshot.id, new_snapshot.id,
            )
            return

        config = {
            "TRAVIAN_OUR_ALLIANCES": app.config.get("TRAVIAN_OUR_ALLIANCES", []),
            "POP_DROP_THRESHOLD": app.config.get("POP_DROP_THRESHOLD", 15),
            "NEW_VILLAGE_RADIUS": app.config.get("NEW_VILLAGE_RADIUS", 30),
            "TRAVIAN_MAP_SIZE": app.config.get("TRAVIAN_MAP_SIZE", 401),
        }

        alerts = detect_alerts(new_snapshot.id, prev_snapshot.id, config)
        if not alerts:
            logger.info("Brak nowych alertów po porównaniu snapshotów #%d i #%d",
                        prev_snapshot.id, new_snapshot.id)
            return

        for alert_data in alerts:
            alert = Alert(
                snapshot_id=new_snapshot.id,
                alert_type=alert_data["type"],
                data=json.dumps(alert_data, ensure_ascii=False),
            )
            db.session.add(alert)

        db.session.commit()
        logger.info("Zapisano %d alertów dla snapshotu #%d", len(alerts), new_snapshot.id)

    except Exception:
        logger.exception("Błąd detekcji alertów")
        db.session.rollback()
