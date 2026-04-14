"""Shared constants and helpers for W.I.T.E.K Discord bot."""

import re
from datetime import datetime, timedelta, timezone
from math import ceil

from bot.tribes import TRIBES, get_speed_multiplier, get_available_tribes

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
FOOTER = "⚔️ W.I.T.E.K — Na cześć H2P_Gucio"

# ------------------------------------------------------------------ #
# Tribe data — names, emoji, Travian CDN icons
# ------------------------------------------------------------------ #
CDN_BASE = "https://cdn.legends.travian.com/gpack/417.3/img_ltr"

TRIBE_NAMES = {t.tid: t.name_pl for t in TRIBES.values()}
TRIBE_EMOJI = {t.tid: t.emoji for t in TRIBES.values()}
TRIBE_ICONS = {
    t.tid: f"{CDN_BASE}/global/tribes/{t.icon_slug}_medium.png"
    for t in TRIBES.values()
    if t.icon_slug
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
TROOP_SPEED_MULTIPLIER = get_speed_multiplier()
AVAILABLE_TRIBES = get_available_tribes()

UNIT_SPEEDS: dict[int, list[dict]] = {}
for _tid, _tribe in TRIBES.items():
    UNIT_SPEEDS[_tid] = [
        {"name": u.speed_name or u.name, "speed": u.speed * TROOP_SPEED_MULTIPLIER, "type": u.unit_type}
        for u in _tribe.units
        if u.name != _tribe.settler_name
    ]

TYPE_EMOJI = {"inf": "🚶", "cav": "🐴", "siege": "🏗️", "special": "👑", "hero": "🦸", "nature": "🐾"}

# ------------------------------------------------------------------ #
# Crop consumption per unit (crop/hour) — official Travian data
# ------------------------------------------------------------------ #
UNIT_CROP: dict[int, list[dict]] = {}
for _tid, _tribe in TRIBES.items():
    UNIT_CROP[_tid] = [
        {"name": u.name, "crop": u.crop, "type": u.unit_type}
        for u in _tribe.units
    ]
UNIT_CROP[0] = [  # Nature / captured animals
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
]
HERO_CROP = 6  # hero always consumes 6 crop/h

# ------------------------------------------------------------------ #
# Unit name mapping — Polish forms (singular, plural, genitive, etc.)
# Maps any game-displayed form → canonical (singular) name
# ------------------------------------------------------------------ #
_UNIT_NAME_MAP: dict[str, str] = {}

# Build map from all known forms
_ALIASES: dict[str, list[str]] = {}
for _tribe in TRIBES.values():
    for _u in _tribe.units:
        if _u.name not in _ALIASES:
            _ALIASES[_u.name] = [_u.name]
        if _u.aliases:
            _ALIASES[_u.name].extend(
                a for a in _u.aliases if a not in _ALIASES[_u.name]
            )
        if _u.speed_name and _u.speed_name not in _ALIASES[_u.name]:
            _ALIASES[_u.name].append(_u.speed_name)
# Hero — not in any tribe
_ALIASES["Bohater"] = ["Bohater", "Bohatera"]
# Nature units (tid=0) — not in TRIBES registry
_ALIASES["Szczur"] = ["Szczury", "Szczurów", "Szczur"]
_ALIASES["Pająk"] = ["Pająki", "Pająków", "Pająk"]
_ALIASES["Wąż"] = ["Węże", "Węży", "Wąż"]
_ALIASES["Nietoperz"] = ["Nietoperze", "Nietoperzy", "Nietoperz"]
_ALIASES["Dzik"] = ["Dziki", "Dzików", "Dzik"]
_ALIASES["Wilk"] = ["Wilki", "Wilków", "Wilk"]
_ALIASES["Niedźwiedź"] = ["Niedźwiedzie", "Niedźwiedzi", "Niedźwiedź"]
_ALIASES["Krokodyl"] = ["Krokodyle", "Krokodyli", "Krokodyl"]
_ALIASES["Tygrys"] = ["Tygrysy", "Tygrysów", "Tygrys"]
_ALIASES["Słoń"] = ["Słonie", "Słoni", "Słoń"]

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


def torus_distance(x1: int, y1: int, x2: int, y2: int, map_size: int = 401, wrap: bool = True) -> float:
    """Calculate distance on a Travian map.

    wrap=True: torus distance (shortest path, may wrap around edges)
    wrap=False: flat Euclidean distance (no wrapping, for RoF servers)
    """
    dx = abs(x1 - x2)
    dy = abs(y1 - y2)
    if wrap:
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
        else AVAILABLE_TRIBES
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

UNIT_COMBAT: dict[int, list[dict]] = {}
for _tid, _tribe in TRIBES.items():
    UNIT_COMBAT[_tid] = [
        {"name": u.name, "att": u.att, "def_inf": u.def_inf, "def_cav": u.def_cav, "type": u.unit_type}
        for u in _tribe.units
        if u.name != _tribe.settler_name
    ]

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


def _get_crop_for_unit(name: str) -> int:
    """Get crop/h for a unit by canonical name. Returns 0 if unknown."""
    return CROP_BY_NAME.get(name, 0)


def calc_needed_defense(
    attackers: dict[str, int],
    defender_unit: str,
    wall_level: int = 0,
) -> dict | None:
    """Calculate how many of `defender_unit` are needed to survive `attackers`.

    Returns dict with count, att_type, total_att, effective_def_per_unit,
    wall_mult, crop_per_hour — or None if defender_unit is unknown.
    """
    # Validate defender unit
    def_stats = COMBAT_BY_NAME.get(defender_unit)
    if def_stats is None:
        return None

    wall_level = max(0, min(20, wall_level))
    wall_mult = 1 + WALL_BONUS[wall_level] / 100

    # Sum attack power by type (same logic as simulate_combat)
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

    if total_att == 0:
        return {
            "count": 0,
            "att_type": "inf",
            "total_att": 0,
            "effective_def_per_unit": 0,
            "wall_mult": wall_mult,
            "crop_per_hour": 0,
        }

    # Majority type determines which defense stat applies
    att_type = "cav" if cav_att > inf_att else "inf"
    def_per_unit = def_stats["def_cav"] if att_type == "cav" else def_stats["def_inf"]
    effective_def_per_unit = def_per_unit * wall_mult

    if effective_def_per_unit <= 0:
        # Defender unit has 0 relevant defense — can't win
        return {
            "count": 0,
            "att_type": att_type,
            "total_att": total_att,
            "effective_def_per_unit": 0,
            "wall_mult": wall_mult,
            "crop_per_hour": 0,
        }

    needed = ceil(total_att / effective_def_per_unit)
    crop = _get_crop_for_unit(defender_unit)

    return {
        "count": needed,
        "att_type": att_type,
        "total_att": total_att,
        "effective_def_per_unit": round(effective_def_per_unit, 2),
        "wall_mult": round(wall_mult, 2),
        "crop_per_hour": needed * crop,
    }


# ------------------------------------------------------------------ #
# Interception send-time calculator (Task 9)
# ------------------------------------------------------------------ #

def calc_interception_times(
    our_x: int, our_y: int,
    def_x: int, def_y: int,
    attack_eta_seconds: float,
    our_tribe: int,
    ts_level: int = 0,
    boots_bonus: float = 0.0,
    artifact_mult: float = 1.0,
    map_size: int = 401,
    wrap: bool = True,
) -> list[dict]:
    """Calculate when to send each unit type to intercept an attack.

    For each unit in our tribe, computes travel time to the defender village
    and derives the latest send time so troops arrive before the attack.

    Returns:
        List of dicts sorted by send time (most urgent first):
            name, type, speed, travel_seconds, send_in_seconds, can_make_it
    """
    distance = torus_distance(our_x, our_y, def_x, def_y, map_size, wrap=wrap)

    units = UNIT_SPEEDS.get(our_tribe, [])
    results = []

    for unit in units:
        travel = _calc_travel_seconds(
            distance, unit["speed"], artifact_mult, boots_bonus, ts_level,
        )
        send_in = attack_eta_seconds - travel
        can_make = send_in >= 0

        results.append({
            "name": unit["name"],
            "type": unit["type"],
            "speed": unit["speed"],
            "travel_seconds": round(travel, 1),
            "send_in_seconds": round(send_in, 1),
            "can_make_it": can_make,
        })

    # Sort: most urgent first (smallest send_in_seconds that's still positive)
    results.sort(key=lambda r: (not r["can_make_it"], r["send_in_seconds"]))
    return results
