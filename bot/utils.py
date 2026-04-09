"""Shared constants and helpers for WITEK Discord bot."""

import re
from datetime import datetime, timedelta, timezone

# ------------------------------------------------------------------ #
# Travian Server Timezone (CEST = UTC+2 for European servers in summer)
# ------------------------------------------------------------------ #
SERVER_TZ = timezone(timedelta(hours=2))

# ------------------------------------------------------------------ #
# Colors — tactical palette for Discord embeds
# ------------------------------------------------------------------ #
COLOR_ATTACK = 0xE74C3C     # red — attacks, danger
COLOR_DEFENSE = 0x5A9A0A    # Travian green — defense, safety
COLOR_SUCCESS = 0x2ECC71    # green — resolved, confirmed
COLOR_WARNING = 0xF1C40F    # yellow — caution
COLOR_INFO = 0x3498DB       # blue — neutral info
COLOR_MAIN = 0x2C1810       # dark brown — general/help
COLOR_GOLD = 0xD4A017       # gold — identity, prestige
COLOR_PURPLE = 0x9B59B6     # purple — system

# ------------------------------------------------------------------ #
# Footer
# ------------------------------------------------------------------ #
FOOTER = "⚔️ WITEK — Na cześć H2P_Gucio"

# ------------------------------------------------------------------ #
# Tribe data — names, emoji, Travian CDN icons
# ------------------------------------------------------------------ #
CDN_BASE = "https://cdn.legends.travian.com/gpack/417.3/img_ltr"

TRIBE_NAMES = {1: "Rzymianie", 2: "Germanie", 3: "Galowie"}
TRIBE_EMOJI = {1: "🏛️", 2: "⚔️", 3: "🏹"}
TRIBE_ICONS = {
    1: f"{CDN_BASE}/global/tribes/roman_medium.png",
    2: f"{CDN_BASE}/global/tribes/teuton_medium.png",
    3: f"{CDN_BASE}/global/tribes/gaul_medium.png",
}

# Resource icons (verified working)
RESOURCE_ICONS = {
    "lumber": f"{CDN_BASE}/global/resources/lumber_small.png",
    "clay": f"{CDN_BASE}/global/resources/clay_small.png",
    "iron": f"{CDN_BASE}/global/resources/iron_small.png",
    "crop": f"{CDN_BASE}/global/resources/crop_small.png",
}

# Attack/defense icons (legacy GIF — verified working)
ICON_ATTACK = f"{CDN_BASE}/legacy/a/att2.gif"
ICON_RAID = f"{CDN_BASE}/legacy/a/att1.gif"
ICON_DEFENSE = f"{CDN_BASE}/legacy/a/def1.gif"
ICON_SPY = f"{CDN_BASE}/legacy/a/att3.gif"
ICON_HERO = f"{CDN_BASE}/hud/topBar/hero/states/heroHome.png"

STATUS_EMOJI = {
    "reported": "🔴",
    "defending": "🟡",
    "resolved": "🟢",
}

# ------------------------------------------------------------------ #
# Travian unit speeds (fields per hour) — Legends standard
# On x3 speed servers, troop movement speed is 2x base.
# ------------------------------------------------------------------ #
TROOP_SPEED_MULTIPLIER = 2  # ts31.x3 = 2x troop speed

UNIT_SPEEDS: dict[int, list[dict]] = {
    1: [  # Romans
        {"name": "Legionista", "speed": 6 * TROOP_SPEED_MULTIPLIER, "type": "inf"},
        {"name": "Pretorianin", "speed": 5 * TROOP_SPEED_MULTIPLIER, "type": "inf"},
        {"name": "Imperians", "speed": 7 * TROOP_SPEED_MULTIPLIER, "type": "inf"},
        {"name": "Equites Legati", "speed": 16 * TROOP_SPEED_MULTIPLIER, "type": "cav"},
        {"name": "Equites Imperatoris", "speed": 14 * TROOP_SPEED_MULTIPLIER, "type": "cav"},
        {"name": "Equites Caesaris", "speed": 10 * TROOP_SPEED_MULTIPLIER, "type": "cav"},
        {"name": "Taran", "speed": 4 * TROOP_SPEED_MULTIPLIER, "type": "siege"},
        {"name": "Katapulta", "speed": 3 * TROOP_SPEED_MULTIPLIER, "type": "siege"},
        {"name": "Senator", "speed": 4 * TROOP_SPEED_MULTIPLIER, "type": "special"},
    ],
    2: [  # Teutons
        {"name": "Pałkarz", "speed": 7 * TROOP_SPEED_MULTIPLIER, "type": "inf"},
        {"name": "Włócznik", "speed": 7 * TROOP_SPEED_MULTIPLIER, "type": "inf"},
        {"name": "Topornik", "speed": 6 * TROOP_SPEED_MULTIPLIER, "type": "inf"},
        {"name": "Zwiadowca", "speed": 9 * TROOP_SPEED_MULTIPLIER, "type": "cav"},
        {"name": "Paladyn", "speed": 10 * TROOP_SPEED_MULTIPLIER, "type": "cav"},
        {"name": "Rycerz Teutoński", "speed": 9 * TROOP_SPEED_MULTIPLIER, "type": "cav"},
        {"name": "Taran", "speed": 4 * TROOP_SPEED_MULTIPLIER, "type": "siege"},
        {"name": "Katapulta", "speed": 3 * TROOP_SPEED_MULTIPLIER, "type": "siege"},
        {"name": "Wódz", "speed": 4 * TROOP_SPEED_MULTIPLIER, "type": "special"},
    ],
    3: [  # Gauls
        {"name": "Falanga", "speed": 7 * TROOP_SPEED_MULTIPLIER, "type": "inf"},
        {"name": "Miecznik", "speed": 6 * TROOP_SPEED_MULTIPLIER, "type": "inf"},
        {"name": "Tropiciel", "speed": 17 * TROOP_SPEED_MULTIPLIER, "type": "cav"},
        {"name": "Piorun Teutatesa", "speed": 19 * TROOP_SPEED_MULTIPLIER, "type": "cav"},
        {"name": "Druid", "speed": 16 * TROOP_SPEED_MULTIPLIER, "type": "cav"},
        {"name": "Haeduan", "speed": 13 * TROOP_SPEED_MULTIPLIER, "type": "cav"},
        {"name": "Taran", "speed": 4 * TROOP_SPEED_MULTIPLIER, "type": "siege"},
        {"name": "Trebusz", "speed": 3 * TROOP_SPEED_MULTIPLIER, "type": "siege"},
        {"name": "Wódz", "speed": 5 * TROOP_SPEED_MULTIPLIER, "type": "special"},
    ],
}

TYPE_EMOJI = {"inf": "🚶", "cav": "🐴", "siege": "🏗️", "special": "👑", "hero": "🦸", "nature": "🐾"}

# ------------------------------------------------------------------ #
# Crop consumption per unit (crop/hour) — official Travian data
# ------------------------------------------------------------------ #
UNIT_CROP: dict[int, list[dict]] = {
    1: [  # Romans
        {"name": "Legionista", "crop": 1, "type": "inf"},
        {"name": "Pretorianin", "crop": 1, "type": "inf"},
        {"name": "Imperians", "crop": 1, "type": "inf"},
        {"name": "Equites Legati", "crop": 3, "type": "cav"},
        {"name": "Equites Imperatoris", "crop": 3, "type": "cav"},
        {"name": "Equites Caesaris", "crop": 4, "type": "cav"},
        {"name": "Taran", "crop": 3, "type": "siege"},
        {"name": "Katapulta ognista", "crop": 6, "type": "siege"},
        {"name": "Senator", "crop": 5, "type": "special"},
        {"name": "Osadnik", "crop": 1, "type": "special"},
    ],
    2: [  # Teutons
        {"name": "Pałkarz", "crop": 1, "type": "inf"},
        {"name": "Włócznik", "crop": 1, "type": "inf"},
        {"name": "Topornik", "crop": 1, "type": "inf"},
        {"name": "Zwiadowca", "crop": 1, "type": "cav"},
        {"name": "Paladyn", "crop": 2, "type": "cav"},
        {"name": "Germański rycerz", "crop": 3, "type": "cav"},
        {"name": "Taran", "crop": 3, "type": "siege"},
        {"name": "Katapulta", "crop": 6, "type": "siege"},
        {"name": "Wódz", "crop": 5, "type": "special"},
        {"name": "Osadnik", "crop": 1, "type": "special"},
    ],
    3: [  # Gauls
        {"name": "Falangita", "crop": 1, "type": "inf"},
        {"name": "Miecznik", "crop": 1, "type": "inf"},
        {"name": "Tropiciel", "crop": 2, "type": "cav"},
        {"name": "Grom Teutatesa", "crop": 2, "type": "cav"},
        {"name": "Jeździec druidzki", "crop": 2, "type": "cav"},
        {"name": "Haeduan", "crop": 3, "type": "cav"},
        {"name": "Taran", "crop": 3, "type": "siege"},
        {"name": "Trebusz", "crop": 6, "type": "siege"},
        {"name": "Wódz", "crop": 5, "type": "special"},
        {"name": "Osadnik", "crop": 1, "type": "special"},
    ],
    0: [  # Nature / captured animals
        {"name": "Szczur", "crop": 1, "type": "nature"},
        {"name": "Pająk", "crop": 1, "type": "nature"},
        {"name": "Wąż", "crop": 1, "type": "nature"},
        {"name": "Nietoperz", "crop": 1, "type": "nature"},
        {"name": "Dzik", "crop": 2, "type": "nature"},
        {"name": "Wilk", "crop": 2, "type": "nature"},
        {"name": "Niedźwiedź", "crop": 3, "type": "nature"},
        {"name": "Krokodyl", "crop": 3, "type": "nature"},
        {"name": "Tygrys", "crop": 4, "type": "nature"},
        {"name": "Słoń", "crop": 5, "type": "nature"},
    ],
}
HERO_CROP = 6  # hero always consumes 6 crop/h

# ------------------------------------------------------------------ #
# Unit name mapping — Polish forms (singular, plural, genitive, etc.)
# Maps any game-displayed form → canonical (singular) name
# ------------------------------------------------------------------ #
_UNIT_NAME_MAP: dict[str, str] = {}

# Build map from all known forms
_ALIASES: dict[str, list[str]] = {
    # Romans
    "Legionista": ["Legioniści", "Legionistów", "Legionista"],
    "Pretorianin": ["Pretorianie", "Pretorianów", "Pretorianin"],
    "Imperians": ["Imperiansy", "Imperiansów", "Imperians"],
    "Equites Legati": ["Equites Legati"],
    "Equites Imperatoris": ["Equites Imperatoris"],
    "Equites Caesaris": ["Equites Caesaris"],
    "Katapulta ognista": ["Katapulty ogniste", "Katapulta ognista"],
    "Senator": ["Senatorzy", "Senatorów", "Senator"],
    # Teutons
    "Pałkarz": ["Pałkarze", "Pałkarzy", "Pałkarz"],
    "Włócznik": ["Włócznicy", "Włóczników", "Włócznik"],
    "Topornik": ["Topornicy", "Toporników", "Topornik"],
    "Zwiadowca": ["Zwiadowcy", "Zwiadowców", "Zwiadowca"],
    "Paladyn": ["Paladyni", "Paladynów", "Paladyn"],
    "Germański rycerz": ["Germańscy rycerze", "Germańskich rycerzy", "Germański rycerz", "Rycerz Teutoński"],
    # Gauls
    "Falangita": ["Falangi", "Falangitów", "Falangita", "Falanga"],
    "Miecznik": ["Miecznicy", "Mieczników", "Miecznik"],
    "Tropiciel": ["Tropiciele", "Tropicieli", "Tropiciel"],
    "Grom Teutatesa": ["Gromy Teutatesa", "Gromów Teutatesa", "Grom Teutatesa", "Piorun Teutatesa"],
    "Jeździec druidzki": ["Jeźdźcy druidzcy", "Jeźdźców druidzkich", "Jeździec druidzki", "Druid"],
    "Haeduan": ["Haeduanowie", "Haeduanów", "Haeduan"],
    "Trebusz": ["Trebusze", "Trebuszów", "Trebusz"],
    # Shared
    "Taran": ["Tarany", "Taranów", "Taran"],
    "Katapulta": ["Katapulty", "Katapult", "Katapulta"],
    "Wódz": ["Wodzowie", "Wodzów", "Wódz"],
    "Osadnik": ["Osadnicy", "Osadników", "Osadnik"],
    "Bohater": ["Bohater", "Bohatera"],
    # Nature
    "Szczur": ["Szczury", "Szczurów", "Szczur"],
    "Pająk": ["Pająki", "Pająków", "Pająk"],
    "Wąż": ["Węże", "Węży", "Wąż"],
    "Nietoperz": ["Nietoperze", "Nietoperzy", "Nietoperz"],
    "Dzik": ["Dziki", "Dzików", "Dzik"],
    "Wilk": ["Wilki", "Wilków", "Wilk"],
    "Niedźwiedź": ["Niedźwiedzie", "Niedźwiedzi", "Niedźwiedź"],
    "Krokodyl": ["Krokodyle", "Krokodyli", "Krokodyl"],
    "Tygrys": ["Tygrysy", "Tygrysów", "Tygrys"],
    "Słoń": ["Słonie", "Słoni", "Słoń"],
}

for canonical, aliases in _ALIASES.items():
    for alias in aliases:
        _UNIT_NAME_MAP[alias.lower()] = canonical
    _UNIT_NAME_MAP[canonical.lower()] = canonical

# Build flat crop lookup: canonical_name → crop/h
CROP_BY_NAME: dict[str, int] = {"Bohater": HERO_CROP}
for tribe_units in UNIT_CROP.values():
    for u in tribe_units:
        CROP_BY_NAME[u["name"]] = u["crop"]


def normalize_unit_name(raw: str) -> str | None:
    """Map any Polish unit name form to canonical singular name."""
    return _UNIT_NAME_MAP.get(raw.strip().lower())


def calc_crop_consumption(troops: dict[str, int]) -> int:
    """Calculate total crop/h for a dict of {unit_name: count}."""
    total = 0
    for name, count in troops.items():
        canonical = normalize_unit_name(name) or name
        crop = CROP_BY_NAME.get(canonical, 1)  # default 1 if unknown
        total += crop * count
    return total


def torus_distance(x1: int, y1: int, x2: int, y2: int, map_size: int = 401) -> float:
    """Calculate shortest distance on a Travian torus map."""
    dx = abs(x1 - x2)
    dy = abs(y1 - y2)
    dx = min(dx, map_size - dx)
    dy = min(dy, map_size - dy)
    return (dx ** 2 + dy ** 2) ** 0.5


def travel_time_str(distance: float, speed: int) -> str:
    """Human-readable travel time for a unit with given speed."""
    hours = distance / speed
    h = int(hours)
    m = int((hours - h) * 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def units_can_reach(tribe_id: int, distance: float, seconds_left: float) -> list[dict]:
    """Return units that can cover `distance` fields in `seconds_left` seconds."""
    if tribe_id not in UNIT_SPEEDS or seconds_left <= 0:
        return []
    hours_left = seconds_left / 3600
    results = []
    for unit in UNIT_SPEEDS[tribe_id]:
        time_needed = distance / unit["speed"]
        can_reach = time_needed <= hours_left
        results.append({
            "name": unit["name"],
            "speed": unit["speed"],
            "type": unit["type"],
            "travel": travel_time_str(distance, unit["speed"]),
            "can_reach": can_reach,
        })
    return results


# ------------------------------------------------------------------ #
# Reverse unit speed detection (S4.2)
# ------------------------------------------------------------------ #

# Modifier options for brute-force search
_ARTIFACT_MULTS = (1.0, 1.5, 2.0)
_BOOTS_BONUSES = (0.0, 0.25, 0.5, 0.75)
_TS_RANGE = range(21)  # Tournament Square 0-20

# Sort priority for unit types (siege most dangerous → first)
_TYPE_ORDER = {"siege": 0, "inf": 1, "cav": 2, "special": 3}


def _calc_travel_seconds(
    distance: float,
    base_speed: float,
    artifact_mult: float = 1.0,
    boots_bonus: float = 0.0,
    ts_level: int = 0,
) -> float:
    """Calculate travel time in seconds using the two-phase Travian formula.

    First 20 fields: speed = base_speed * artifact_mult
    After 20 fields: speed = base_speed * artifact_mult * (1 + boots + 0.2*ts)
    """
    if distance <= 0 or base_speed <= 0:
        return 0.0

    eff_speed = base_speed * artifact_mult

    if distance <= 20:
        return (distance / eff_speed) * 3600

    time_first20 = 20 / eff_speed
    boosted_speed = eff_speed * (1 + boots_bonus + 0.2 * ts_level)
    time_rest = (distance - 20) / boosted_speed
    return (time_first20 + time_rest) * 3600


def calc_safe_distance(
    speed: float,
    hours_away: float,
    ts_level: int = 0,
    boots_bonus: float = 0.0,
    artifact_mult: float = 1.0,
) -> float:
    """Calculate minimum one-way distance for a safe round trip.

    Given how many hours troops should be away, returns the distance
    so that a round trip takes at least that long.
    Uses binary search on _calc_travel_seconds().
    """
    if hours_away <= 0 or speed <= 0:
        return 0.0

    budget_seconds = hours_away * 3600
    max_speed = speed * artifact_mult * (1 + boots_bonus + 0.2 * ts_level)
    upper = max_speed * hours_away / 2 * 1.1
    lower = 0.0

    for _ in range(100):
        mid = (lower + upper) / 2
        round_trip = 2 * _calc_travel_seconds(mid, speed, artifact_mult, boots_bonus, ts_level)
        if abs(round_trip - budget_seconds) < 1.0:
            return round(mid, 2)
        if round_trip < budget_seconds:
            lower = mid
        else:
            upper = mid

    return round((lower + upper) / 2, 2)


def detect_possible_units(
    distance: float,
    travel_seconds: float,
    attacker_tribe: int | None = None,
) -> list[dict]:
    """Reverse-calculate which units could be attacking.

    Given distance and travel time, determines what units match that speed.
    Considers Tournament Square (0-20), hero boots (0-75%), and artifacts.

    Args:
        distance: Distance in fields (float).
        travel_seconds: Travel time in seconds.
        attacker_tribe: If known, only check that tribe's units. If None, check all.

    Returns:
        List of dicts sorted by tactical priority (siege first):
            name: unit name (Polish)
            tribe: tribe id (or list of tribe ids if grouped)
            type: inf/cav/siege/special
            speed: base speed (already includes x2 multiplier)
            ts_range: (min_ts, max_ts) — Tournament Square range that fits
            needs_boots: bool — whether hero boots are needed
            needs_artifact: bool — whether speed artifact needed
            artifact_mult: float (1.0, 1.5, or 2.0)
            boots_bonus: float (0.0, 0.25, 0.5, or 0.75)
    """
    if distance <= 0 or travel_seconds <= 0:
        return []

    # Hybrid tolerance: at least 60s, otherwise 5% of travel time
    tolerance = max(60.0, travel_seconds * 0.05)

    tribes_to_check = (
        [attacker_tribe]
        if attacker_tribe and attacker_tribe in UNIT_SPEEDS
        else [1, 2, 3]
    )

    # Collect matches keyed by (name, speed, type) for cross-tribe dedup
    grouped: dict[tuple[str, int, str], dict] = {}

    for tid in tribes_to_check:
        for unit in UNIT_SPEEDS[tid]:
            key = (unit["name"], unit["speed"], unit["type"])
            best_match = None

            for art in _ARTIFACT_MULTS:
                for boots in _BOOTS_BONUSES:
                    # For dist <= 20, boots and TS have no effect — skip variations
                    if distance <= 20 and (boots > 0):
                        continue

                    matching_ts = []
                    ts_options = [0] if distance <= 20 else _TS_RANGE

                    for ts in ts_options:
                        calc = _calc_travel_seconds(
                            distance, unit["speed"], art, boots, ts
                        )
                        if abs(calc - travel_seconds) <= tolerance:
                            matching_ts.append(ts)

                    if not matching_ts:
                        continue

                    candidate = {
                        "artifact": art,
                        "boots": boots,
                        "ts_min": min(matching_ts),
                        "ts_max": max(matching_ts),
                    }

                    # Prefer simplest explanation (lowest modifiers)
                    if best_match is None or (
                        art, boots, candidate["ts_min"]
                    ) < (
                        best_match["artifact"],
                        best_match["boots"],
                        best_match["ts_min"],
                    ):
                        best_match = candidate

            if best_match is None:
                continue

            if key in grouped:
                # Add this tribe to existing group
                if tid not in grouped[key]["tribes"]:
                    grouped[key]["tribes"].append(tid)
            else:
                grouped[key] = {
                    "name": unit["name"],
                    "tribes": [tid],
                    "type": unit["type"],
                    "speed": unit["speed"],
                    "ts_range": (best_match["ts_min"], best_match["ts_max"]),
                    "needs_boots": best_match["boots"] > 0,
                    "needs_artifact": best_match["artifact"] > 1.0,
                    "artifact_mult": best_match["artifact"],
                    "boots_bonus": best_match["boots"],
                }

    results = list(grouped.values())

    # When tribe is known, collapse tribes list to single int
    for r in results:
        r["tribe"] = r["tribes"][0] if len(r["tribes"]) == 1 else r["tribes"]
        del r["tribes"]

    # Sort: siege first (most dangerous), then by speed ascending
    results.sort(key=lambda r: (_TYPE_ORDER.get(r["type"], 99), r["speed"]))

    return results


def format_unit_analysis(results: list[dict]) -> str:
    """Format detect_possible_units results for a Discord embed field.

    Groups output by type (siege → inf → cav → special).
    Keeps total length ≤ 1024 chars (Discord field limit).
    """
    if not results:
        return ""

    # Sort: siege first (most dangerous), then inf, cav, special; by speed
    sorted_results = sorted(
        results, key=lambda r: (_TYPE_ORDER.get(r["type"], 99), r["speed"])
    )

    lines: list[str] = []
    for r in sorted_results:
        emoji = TYPE_EMOJI.get(r["type"], "")

        # Tribe indicator (only when multiple tribes)
        tribe = r["tribe"]
        if isinstance(tribe, list):
            tribe_str = "".join(TRIBE_EMOJI.get(t, "") for t in tribe)
        else:
            tribe_str = TRIBE_EMOJI.get(tribe, "")

        # Build modifier description
        parts: list[str] = []
        if r["needs_artifact"]:
            parts.append(f"artefakt x{r['artifact_mult']:g}")

        ts_min, ts_max = r["ts_range"]
        if ts_min == 0 and ts_max == 0:
            parts.append("bez TS")
        elif ts_min == ts_max:
            parts.append(f"TS {ts_min}")
        else:
            parts.append(f"TS ~{ts_min}-{ts_max}")

        if r["needs_boots"]:
            parts.append(f"buty {int(r['boots_bonus'] * 100)}%")
        elif not r["needs_artifact"] and ts_min == 0 and ts_max == 0:
            parts.append("bez butów")

        mod_str = ", ".join(parts) if parts else "bez modyfikatorów"

        lines.append(
            f"{emoji} **{r['name']}** ({r['speed']} pól/h) {tribe_str} — {mod_str}"
        )

    text = "\n".join(lines)
    if len(text) > 1000:
        # Truncate and indicate remaining count
        truncated: list[str] = []
        length = 0
        for i, line in enumerate(lines):
            if length + len(line) + 1 > 950:
                remaining = len(lines) - i
                truncated.append(f"_...i {remaining} więcej pasujących_")
                break
            truncated.append(line)
            length += len(line) + 1
        text = "\n".join(truncated)

    return text


# ------------------------------------------------------------------ #
# Coordinate parsing
# ------------------------------------------------------------------ #

def parse_coords(text: str) -> tuple[int | None, int | None]:
    """Parse Travian-style coordinates from text.

    Accepts: "76|43", "76 43", "(76, 43)", "-12|-34", "76|43" etc.
    Returns (x, y) or (None, None) if unparseable or out of range.
    Travian map is 401x401, coords range: [-200, 200].
    """
    m = re.match(r"\(?(-?\d+)\s*[|,/\s]\s*(-?\d+)\)?", text.strip())
    if m:
        x, y = int(m.group(1)), int(m.group(2))
        if -200 <= x <= 200 and -200 <= y <= 200:
            return x, y
    return None, None


def map_link(server_url: str, x: int, y: int) -> str:
    """Build a clickable Travian map link."""
    return f"{server_url}/karte.php?x={x}&y={y}"


def coords_display(server_url: str, x: int, y: int) -> str:
    """Format coordinates as a clickable markdown link."""
    url = map_link(server_url, x, y)
    return f"[({x}|{y})]({url})"


# ------------------------------------------------------------------ #
# Time parsing → Discord timestamp
# ------------------------------------------------------------------ #

def parse_attack_time(time_str: str) -> int | None:
    """Parse HH:MM (or DD.MM HH:MM) into a Unix timestamp.

    Assumes server timezone (CEST, UTC+2). If only HH:MM and it's in
    the past today, assumes tomorrow.
    Returns Unix timestamp or None.
    """
    time_str = time_str.strip()

    # Try DD.MM HH:MM or DD.MM.YYYY HH:MM
    for fmt in ("%d.%m %H:%M", "%d.%m.%Y %H:%M"):
        try:
            parsed = datetime.strptime(time_str, fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=datetime.now().year)
            parsed = parsed.replace(tzinfo=SERVER_TZ)
            return int(parsed.timestamp())
        except ValueError:
            continue

    # Try HH:MM only
    m = re.match(r"(\d{1,2}):(\d{2})", time_str)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        now = datetime.now(SERVER_TZ)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return int(target.timestamp())

    return None


def discord_timestamp(unix: int, style: str = "R") -> str:
    """Format a unix timestamp as a Discord timestamp.

    Styles: R=relative, f=full, t=time, T=time+sec, d=date, D=long date, F=full+day
    """
    return f"<t:{unix}:{style}>"


# ------------------------------------------------------------------ #
# Combat stats — official Travian Legends attack/defense values
# ------------------------------------------------------------------ #

UNIT_COMBAT: dict[int, list[dict]] = {
    1: [  # Romans
        {"name": "Legionista", "att": 40, "def_inf": 35, "def_cav": 50, "type": "inf"},
        {"name": "Pretorianin", "att": 30, "def_inf": 65, "def_cav": 35, "type": "inf"},
        {"name": "Imperians", "att": 70, "def_inf": 40, "def_cav": 25, "type": "inf"},
        {"name": "Equites Legati", "att": 0, "def_inf": 20, "def_cav": 10, "type": "cav"},
        {"name": "Equites Imperatoris", "att": 120, "def_inf": 65, "def_cav": 50, "type": "cav"},
        {"name": "Equites Caesaris", "att": 180, "def_inf": 80, "def_cav": 105, "type": "cav"},
        {"name": "Taran", "att": 60, "def_inf": 30, "def_cav": 75, "type": "siege"},
        {"name": "Katapulta ognista", "att": 75, "def_inf": 60, "def_cav": 10, "type": "siege"},
        {"name": "Senator", "att": 50, "def_inf": 40, "def_cav": 30, "type": "special"},
    ],
    2: [  # Teutons
        {"name": "Pałkarz", "att": 40, "def_inf": 20, "def_cav": 5, "type": "inf"},
        {"name": "Włócznik", "att": 10, "def_inf": 35, "def_cav": 60, "type": "inf"},
        {"name": "Topornik", "att": 60, "def_inf": 30, "def_cav": 30, "type": "inf"},
        {"name": "Zwiadowca", "att": 0, "def_inf": 10, "def_cav": 5, "type": "cav"},
        {"name": "Paladyn", "att": 55, "def_inf": 100, "def_cav": 40, "type": "cav"},
        {"name": "Germański rycerz", "att": 150, "def_inf": 50, "def_cav": 75, "type": "cav"},
        {"name": "Taran", "att": 65, "def_inf": 30, "def_cav": 80, "type": "siege"},
        {"name": "Katapulta", "att": 50, "def_inf": 60, "def_cav": 10, "type": "siege"},
        {"name": "Wódz", "att": 40, "def_inf": 60, "def_cav": 40, "type": "special"},
    ],
    3: [  # Gauls
        {"name": "Falangita", "att": 15, "def_inf": 40, "def_cav": 50, "type": "inf"},
        {"name": "Miecznik", "att": 65, "def_inf": 35, "def_cav": 20, "type": "inf"},
        {"name": "Tropiciel", "att": 0, "def_inf": 20, "def_cav": 10, "type": "cav"},
        {"name": "Grom Teutatesa", "att": 90, "def_inf": 25, "def_cav": 40, "type": "cav"},
        {"name": "Jeździec druidzki", "att": 45, "def_inf": 115, "def_cav": 55, "type": "cav"},
        {"name": "Haeduan", "att": 140, "def_inf": 60, "def_cav": 165, "type": "cav"},
        {"name": "Taran", "att": 50, "def_inf": 30, "def_cav": 70, "type": "siege"},
        {"name": "Trebusz", "att": 70, "def_inf": 45, "def_cav": 10, "type": "siege"},
        {"name": "Wódz", "att": 40, "def_inf": 50, "def_cav": 50, "type": "special"},
    ],
}

# Flat lookup: canonical_name → combat stats
COMBAT_BY_NAME: dict[str, dict] = {}
for _tribe_id, _units in UNIT_COMBAT.items():
    for _u in _units:
        COMBAT_BY_NAME[_u["name"]] = {
            "att": _u["att"],
            "def_inf": _u["def_inf"],
            "def_cav": _u["def_cav"],
            "type": _u["type"],
            "tribe": _tribe_id,
        }

# Wall defense bonus by level (0-20) — Travian Legends Earth Wall/City Wall/Palisade
WALL_BONUS: list[float] = [
    0, 2, 4, 7, 10, 14, 18, 23, 28, 34, 40,
    47, 55, 63, 72, 81, 91, 102, 113, 125, 138,
]

# Common abbreviations → canonical name for combat input parsing
_COMBAT_ABBREV: dict[str, str] = {
    "ec": "Equites Caesaris",
    "ei": "Equites Imperatoris",
    "el": "Equites Legati",
    "ko": "Katapulta ognista",
    "rt": "Germański rycerz",
    "gt": "Grom Teutatesa",
    "jd": "Jeździec druidzki",
    "tt": "Grom Teutatesa",
    "imp": "Imperians",
    "pret": "Pretorianin",
    "leg": "Legionista",
    "pal": "Paladyn",
    "top": "Topornik",
    "fal": "Falangita",
    "haed": "Haeduan",
}


def parse_army_input(text: str) -> tuple[dict[str, int], list[str]]:
    """Parse user army input like 'Imperians:500, EC:200'.

    Accepts comma or newline separated entries, each as 'name:count' or 'name count'.
    Returns (army_dict, errors) where army_dict maps canonical name → count.
    """
    army: dict[str, int] = {}
    errors: list[str] = []

    # Split by comma or newline
    entries = re.split(r"[,\n]+", text.strip())
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        # Split name:count or name count (last token is the number)
        m = re.match(r"^(.+?)\s*[:=]\s*(\d+)\s*$", entry)
        if not m:
            # Try: name<space>count
            m = re.match(r"^(.+?)\s+(\d+)\s*$", entry)
        if not m:
            errors.append(f"❌ Nie rozumiem: `{entry}` — użyj formatu `nazwa:ilość`")
            continue

        raw_name = m.group(1).strip()
        count = int(m.group(2))
        if count <= 0:
            continue

        # Try normalize_unit_name first
        canonical = normalize_unit_name(raw_name)
        # Try abbreviation lookup
        if canonical is None:
            canonical = _COMBAT_ABBREV.get(raw_name.lower())
        # Validate that it has combat stats
        if canonical is None or canonical not in COMBAT_BY_NAME:
            errors.append(f"❌ Nieznana jednostka: `{raw_name}`")
            continue

        army[canonical] = army.get(canonical, 0) + count

    return army, errors


def simulate_combat(
    attackers: dict[str, int],
    defenders: dict[str, int],
    wall_level: int = 0,
) -> dict:
    """Simulate Travian Legends combat (simplified).

    Returns dict with:
    - inf_att: infantry attack points
    - cav_att: cavalry attack points
    - total_att: total attack power
    - def_power_inf: total defense vs infantry (before wall)
    - def_power_cav: total defense vs cavalry (before wall)
    - def_power_inf_wall: defense vs inf with wall
    - def_power_cav_wall: defense vs cav with wall
    - wall_bonus_pct: wall bonus percentage
    - att_type: "inf" or "cav" (majority attack type)
    - effective_def: defense used in calculation
    - att_losses_pct: percentage of attackers lost (0-100)
    - def_losses_pct: percentage of defenders lost (0-100)
    - result: "att_wins" / "def_wins" / "draw"
    - att_remaining: dict of surviving attackers
    - def_remaining: dict of surviving defenders
    """
    wall_level = max(0, min(20, wall_level))
    wall_pct = WALL_BONUS[wall_level]

    # Calculate attack power split by type
    inf_att = 0
    cav_att = 0
    for name, count in attackers.items():
        stats = COMBAT_BY_NAME.get(name)
        if not stats or count <= 0:
            continue
        power = stats["att"] * count
        if stats["type"] in ("inf", "siege", "special"):
            inf_att += power
        else:  # cav
            cav_att += power

    total_att = inf_att + cav_att

    # Calculate defense power
    def_inf = 0
    def_cav = 0
    for name, count in defenders.items():
        stats = COMBAT_BY_NAME.get(name)
        if not stats or count <= 0:
            continue
        def_inf += stats["def_inf"] * count
        def_cav += stats["def_cav"] * count

    # Apply wall bonus
    wall_mult = 1 + wall_pct / 100
    def_inf_wall = def_inf * wall_mult
    def_cav_wall = def_cav * wall_mult

    # Determine attack type (majority of attack points)
    att_type = "cav" if cav_att > inf_att else "inf"
    effective_def = def_cav_wall if att_type == "cav" else def_inf_wall

    # Edge cases
    if total_att == 0 and effective_def == 0:
        return {
            "inf_att": 0, "cav_att": 0, "total_att": 0,
            "def_power_inf": def_inf, "def_power_cav": def_cav,
            "def_power_inf_wall": def_inf_wall, "def_power_cav_wall": def_cav_wall,
            "wall_bonus_pct": wall_pct, "att_type": att_type,
            "effective_def": effective_def,
            "att_losses_pct": 0, "def_losses_pct": 0,
            "result": "draw",
            "att_remaining": dict(attackers), "def_remaining": dict(defenders),
        }
    if total_att == 0:
        return {
            "inf_att": 0, "cav_att": 0, "total_att": 0,
            "def_power_inf": def_inf, "def_power_cav": def_cav,
            "def_power_inf_wall": def_inf_wall, "def_power_cav_wall": def_cav_wall,
            "wall_bonus_pct": wall_pct, "att_type": att_type,
            "effective_def": effective_def,
            "att_losses_pct": 100, "def_losses_pct": 0,
            "result": "def_wins",
            "att_remaining": {n: 0 for n in attackers}, "def_remaining": dict(defenders),
        }
    if effective_def == 0:
        return {
            "inf_att": inf_att, "cav_att": cav_att, "total_att": total_att,
            "def_power_inf": def_inf, "def_power_cav": def_cav,
            "def_power_inf_wall": def_inf_wall, "def_power_cav_wall": def_cav_wall,
            "wall_bonus_pct": wall_pct, "att_type": att_type,
            "effective_def": effective_def,
            "att_losses_pct": 0, "def_losses_pct": 100,
            "result": "att_wins",
            "att_remaining": dict(attackers),
            "def_remaining": {n: 0 for n in defenders},
        }

    # Combat calculation
    att = total_att
    defe = effective_def
    ratio = min(att, defe) / max(att, defe)
    winner_losses_pct = (ratio ** 1.5) * 100

    if att > defe:
        result = "att_wins"
        att_losses_pct = winner_losses_pct
        def_losses_pct = 100.0
    elif defe > att:
        result = "def_wins"
        att_losses_pct = 100.0
        def_losses_pct = winner_losses_pct
    else:
        result = "draw"
        att_losses_pct = 100.0
        def_losses_pct = 100.0

    # Calculate remaining troops
    att_remaining = {}
    for name, count in attackers.items():
        surviving = int(count * (1 - att_losses_pct / 100))
        att_remaining[name] = surviving

    def_remaining = {}
    for name, count in defenders.items():
        surviving = int(count * (1 - def_losses_pct / 100))
        def_remaining[name] = surviving

    return {
        "inf_att": inf_att, "cav_att": cav_att, "total_att": total_att,
        "def_power_inf": def_inf, "def_power_cav": def_cav,
        "def_power_inf_wall": def_inf_wall, "def_power_cav_wall": def_cav_wall,
        "wall_bonus_pct": wall_pct, "att_type": att_type,
        "effective_def": effective_def,
        "att_losses_pct": round(att_losses_pct, 1),
        "def_losses_pct": round(def_losses_pct, 1),
        "result": result,
        "att_remaining": att_remaining,
        "def_remaining": def_remaining,
    }
