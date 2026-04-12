"""Alert detection — porównanie snapshotów map.sql."""

import logging
from datetime import datetime, timedelta, timezone
from ..database import db
from ..models import Alert, Snapshot, Village

logger = logging.getLogger(__name__)

# Tolerancja rozmiaru snapshotu — jeśli nowy ma mniej niż 50% wiosek
# poprzedniego, uznajemy go za uszkodzony/obcięty i pomijamy alerty.
SNAPSHOT_SIZE_TOLERANCE = 0.5


def torus_distance(x1: int, y1: int, x2: int, y2: int, map_size: int = 401) -> float:
    """Dystans na torusowej mapie Travian."""
    dx = abs(x1 - x2)
    dy = abs(y1 - y2)
    dx = min(dx, map_size - dx)
    dy = min(dy, map_size - dy)
    return (dx ** 2 + dy ** 2) ** 0.5


def _ensure_utc(dt):
    """SQLite stores naive datetimes — treat as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def is_stale_pair(new_snapshot_id: int, prev_snapshot_id: int,
                  max_gap_minutes: float) -> bool:
    """Czy luka czasowa między snapshotami jest zbyt duża?

    Zwraca True gdy różnica fetched_at > max_gap_minutes.
    Używane aby pominąć generowanie alertów po dłuższym przestoju
    (np. 2-dniowa przerwa generowałaby tysiące fałszywych alertów).
    """
    prev = db.session.get(Snapshot, prev_snapshot_id)
    new = db.session.get(Snapshot, new_snapshot_id)

    if prev is None or new is None:
        return True

    prev_time = _ensure_utc(prev.fetched_at)
    new_time = _ensure_utc(new.fetched_at)

    gap_minutes = (new_time - prev_time).total_seconds() / 60
    if gap_minutes > max_gap_minutes:
        logger.warning(
            "Snapshoty #%d → #%d: luka %.0f min (limit: %.0f min) — "
            "za duża różnica, pomijam alerty aby uniknąć fałszywego spamu",
            prev_snapshot_id, new_snapshot_id,
            gap_minutes, max_gap_minutes,
        )
        return True

    logger.debug(
        "Snapshoty #%d → #%d: luka %.0f min (limit: %.0f min) — OK",
        prev_snapshot_id, new_snapshot_id, gap_minutes, max_gap_minutes,
    )
    return False


def validate_snapshot_pair(new_snapshot_id: int, prev_snapshot_id: int) -> bool:
    """Sprawdza czy nowy snapshot jest wiarygodny (nie obcięty/uszkodzony).

    Zwraca False gdy village_count nowego snapshotu jest < 50% poprzedniego.
    """
    prev = db.session.get(Snapshot, prev_snapshot_id)
    new = db.session.get(Snapshot, new_snapshot_id)

    if prev is None or new is None:
        return False

    prev_count = prev.village_count or 0
    new_count = new.village_count or 0

    if prev_count == 0:
        return True  # brak bazy porównawczej

    ratio = new_count / prev_count
    if ratio < SNAPSHOT_SIZE_TOLERANCE:
        logger.warning(
            "Snapshot #%d ma tylko %d wiosek (%.0f%% z #%d = %d) — "
            "prawdopodobnie obcięty, pomijam alerty",
            new_snapshot_id, new_count, ratio * 100,
            prev_snapshot_id, prev_count,
        )
        return False

    return True


def detect_alerts(new_snapshot_id: int, prev_snapshot_id: int, config: dict) -> list[dict]:
    """Porównuje dwa snapshoty i zwraca listę alertów.

    config keys:
    - TRAVIAN_OUR_ALLIANCES: list[int]
    - POP_DROP_THRESHOLD: int (percentage, e.g. 25 = 25%)
    - NEW_VILLAGE_RADIUS: int (fields)
    - TRAVIAN_MAP_SIZE: int (default 401)
    - MIN_POP_FOR_ALERTS: int (default 500)
    - ALERT_COOLDOWN_HOURS: int (default 6)
    """
    if not validate_snapshot_pair(new_snapshot_id, prev_snapshot_id):
        return []

    our_alliances = set(config.get("TRAVIAN_OUR_ALLIANCES", []))
    threshold = config.get("POP_DROP_THRESHOLD", 25)
    radius = config.get("NEW_VILLAGE_RADIUS", 30)
    map_size = config.get("TRAVIAN_MAP_SIZE", 401)
    min_pop = config.get("MIN_POP_FOR_ALERTS", 500)
    cooldown_hours = config.get("ALERT_COOLDOWN_HOURS", 6)

    alerts = []
    alerts.extend(_detect_pop_drops(
        new_snapshot_id, prev_snapshot_id, our_alliances, threshold, map_size,
        min_pop, cooldown_hours))
    alerts.extend(_detect_new_villages(
        new_snapshot_id, prev_snapshot_id, our_alliances, radius, map_size))
    alerts.extend(_detect_alliance_changes(
        new_snapshot_id, prev_snapshot_id, our_alliances, map_size))
    return alerts


def _get_player_populations(snapshot_id: int) -> dict[int, dict]:
    """Agreguje SUM(population) GROUP BY uid z Village table.

    Returns {uid: {"name": str, "aid": int, "alliance_name": str, "total_pop": int}}
    """
    rows = (
        db.session.query(
            Village.uid,
            Village.player_name,
            Village.aid,
            Village.alliance_name,
            db.func.sum(Village.population),
        )
        .filter(Village.snapshot_id == snapshot_id, Village.uid != 0)
        .group_by(Village.uid)
        .all()
    )
    result = {}
    for uid, player_name, aid, alliance_name, total_pop in rows:
        result[uid] = {
            "name": player_name,
            "aid": aid,
            "alliance_name": alliance_name or "",
            "total_pop": total_pop,
        }
    return result


def _get_occupied_villages(snapshot_id: int) -> dict[int, dict]:
    """Pobiera wioski z uid > 0, indeksowane po map_id."""
    rows = (
        db.session.query(
            Village.map_id,
            Village.x,
            Village.y,
            Village.name,
            Village.uid,
            Village.player_name,
            Village.aid,
            Village.alliance_name,
            Village.population,
        )
        .filter(Village.snapshot_id == snapshot_id, Village.uid != 0)
        .all()
    )
    return {
        r[0]: {
            "map_id": r[0], "x": r[1], "y": r[2], "name": r[3],
            "uid": r[4], "player_name": r[5],
            "aid": r[6], "alliance_name": r[7] or "", "population": r[8],
        }
        for r in rows
    }


def _get_player_alliance_map(snapshot_id: int) -> dict[int, dict]:
    """Zwraca DISTINCT (uid, aid) mapping z Village table.

    GROUP BY uid daje jedną parę (uid, aid) na gracza.
    Returns {uid: {"aid": int, "alliance_name": str, "name": str, "total_pop": int}}
    """
    rows = (
        db.session.query(
            Village.uid,
            Village.player_name,
            Village.aid,
            Village.alliance_name,
            db.func.sum(Village.population),
        )
        .filter(Village.snapshot_id == snapshot_id, Village.uid != 0)
        .group_by(Village.uid)
        .all()
    )
    return {
        uid: {
            "name": player_name,
            "aid": aid,
            "alliance_name": alliance_name or "",
            "total_pop": total_pop,
        }
        for uid, player_name, aid, alliance_name, total_pop in rows
    }


def _detect_pop_drops(new_id, prev_id, our_alliances, threshold, map_size,
                      min_pop=500, cooldown_hours=6):
    """Wykrywa spadki populacji graczy z NASZYCH sojuszów.

    Tylko gracze gdzie aid in our_alliances (w prev LUB new snapshot).
    Porównuje SUM(population) GROUP BY uid z Village table.
    """
    prev_players = _get_player_populations(prev_id)
    new_players = _get_player_populations(new_id)

    # Unia graczy z obu snapshotów — obsługuje znikniętych graczy (pop → 0)
    all_uids = set(prev_players.keys()) | set(new_players.keys())

    alerts = []
    for uid in all_uids:
        prev_data = prev_players.get(uid)
        new_data = new_players.get(uid)

        if prev_data is None:
            continue  # nowy gracz — nie raportujemy spadku

        old_pop = prev_data["total_pop"]
        if old_pop == 0:
            continue

        # Filtr: tylko gracze z naszych sojuszów (prev LUB new)
        is_our = prev_data["aid"] in our_alliances
        if new_data:
            is_our = is_our or new_data["aid"] in our_alliances
        if not is_our:
            continue

        # Min pop — pomijamy małe konta z niestabilnym %
        if old_pop < min_pop:
            continue

        new_pop = new_data["total_pop"] if new_data else 0
        drop_pct = ((old_pop - new_pop) / old_pop) * 100

        if drop_pct < threshold:
            continue

        # Cooldown dedup — nie alertuj jeśli już był alert w ostatnich N godzinach
        if cooldown_hours > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)
            recent = Alert.query.filter(
                Alert.alert_type == "pop_drop",
                Alert.data.contains(f'"uid": {uid},'),
                Alert.created_at >= cutoff,
            ).first()
            if recent:
                continue

        alerts.append({
            "type": "pop_drop",
            "uid": uid,
            "player_name": prev_data["name"],
            "alliance_name": prev_data["alliance_name"],
            "old_pop": old_pop,
            "new_pop": new_pop,
            "drop_pct": round(drop_pct, 1),
        })

    return alerts


def _detect_new_villages(new_id, prev_id, our_alliances, radius, map_size):
    """Wykrywa nowe wrogie wioski w pobliżu sojuszu.

    Diff po map_id: wioska jest "nowa" gdy map_id z uid>0 pojawia się
    w nowym snapshocie ale nie istniał (z uid>0) w poprzednim.
    """
    prev_occupied = _get_occupied_villages(prev_id)
    new_occupied = _get_occupied_villages(new_id)

    prev_map_ids = set(prev_occupied.keys())
    ally_positions = _get_ally_positions(new_id, our_alliances, map_size)

    if not ally_positions:
        return []

    alerts = []
    for map_id, v in new_occupied.items():
        if map_id in prev_map_ids:
            continue
        # Pomijamy wioski naszych sojuszów
        if v["aid"] in our_alliances:
            continue

        min_dist = _min_distance_to_allies(v["x"], v["y"], ally_positions, map_size)
        if min_dist > radius:
            continue

        alerts.append({
            "type": "new_village",
            "map_id": map_id,
            "village_name": v["name"],
            "x": v["x"],
            "y": v["y"],
            "uid": v["uid"],
            "player_name": v["player_name"],
            "aid": v["aid"],
            "alliance_name": v["alliance_name"],
            "distance": round(min_dist, 1),
        })

    return alerts


def _detect_alliance_changes(new_id, prev_id, our_alliances, map_size):
    """Wykrywa zmiany przynależności do sojuszów.

    Diff DISTINCT (uid, aid) między snapshotami. Klasyfikacja:
    - leave: gracz opuścił nasz sojusz
    - join: gracz dołączył do naszego sojuszu
    - switch: zmiana między sojuszami z udziałem obserwowanych

    Zakres: tylko zmiany dotyczące naszych sojuszów LUB wrogów blisko nas.
    aid=0 traktowany jako neutralny (brak sojuszu), nie wróg.
    """
    prev_map = _get_player_alliance_map(prev_id)
    new_map = _get_player_alliance_map(new_id)

    # Tylko gracze obecni w obu snapshotach (zniknięci → pop_drop, nie alliance_change)
    common_uids = set(prev_map.keys()) & set(new_map.keys())

    ally_positions = _get_ally_positions(new_id, our_alliances, map_size)

    alerts = []
    for uid in common_uids:
        prev_aid = prev_map[uid]["aid"]
        new_aid = new_map[uid]["aid"]

        if prev_aid == new_aid:
            continue

        # Klasyfikacja zmiany
        involves_our = prev_aid in our_alliances or new_aid in our_alliances

        if involves_our:
            # Bezpośrednio dotyczy naszych sojuszów — zawsze alertuj
            if prev_aid in our_alliances and new_aid not in our_alliances:
                change_type = "leave"
            elif new_aid in our_alliances and prev_aid not in our_alliances:
                change_type = "join"
            else:
                change_type = "switch"
        else:
            # Nie dotyczy naszych sojuszów — alertuj tylko jeśli gracz
            # dołączył do wroga (aid != 0) i jest blisko naszego terytorium
            if new_aid == 0:
                continue  # przeszedł na neutralny — nie interesuje nas
            if not _is_player_near_allies(
                uid, new_id, prev_id, ally_positions, radius=50, map_size=map_size
            ):
                continue
            change_type = "switch"

        alerts.append({
            "type": "alliance_change",
            "change_type": change_type,
            "uid": uid,
            "player_name": new_map[uid]["name"],
            "old_aid": prev_aid,
            "old_alliance_name": prev_map[uid]["alliance_name"],
            "new_aid": new_aid,
            "new_alliance_name": new_map[uid]["alliance_name"],
            "total_pop": new_map[uid]["total_pop"],
        })

    return alerts


def _get_ally_positions(snapshot_id, our_alliances, map_size):
    """Zwraca listę (x, y) wiosek sojuszniczych."""
    if not our_alliances:
        return []
    rows = (
        db.session.query(Village.x, Village.y)
        .filter(
            Village.snapshot_id == snapshot_id,
            Village.aid.in_(our_alliances),
        )
        .all()
    )
    return [(r[0], r[1]) for r in rows]


def _min_distance_to_allies(x, y, ally_positions, map_size):
    """Minimalny dystans torusowy do wiosek sojuszniczych."""
    if not ally_positions:
        return float("inf")
    return min(torus_distance(x, y, ax, ay, map_size) for ax, ay in ally_positions)


def _is_player_near_allies(uid, new_snapshot_id, prev_snapshot_id,
                           ally_positions, radius, map_size):
    """Sprawdza czy gracz ma wioskę blisko sojuszu.

    Sprawdza nowy snapshot, a jeśli gracz zniknął — fallback na poprzedni.
    """
    if not ally_positions:
        return False

    rows = (
        db.session.query(Village.x, Village.y)
        .filter(Village.snapshot_id == new_snapshot_id, Village.uid == uid)
        .all()
    )

    # Gracz mógł zniknąć — sprawdź poprzedni snapshot
    if not rows:
        rows = (
            db.session.query(Village.x, Village.y)
            .filter(Village.snapshot_id == prev_snapshot_id, Village.uid == uid)
            .all()
        )

    for vx, vy in rows:
        if _min_distance_to_allies(vx, vy, ally_positions, map_size) <= radius:
            return True
    return False
