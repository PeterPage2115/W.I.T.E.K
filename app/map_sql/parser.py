"""Parser for Travian map.sql file.

The map.sql file contains INSERT statements with 16 fields:
INSERT INTO x_world VALUES (id, x, y, tid, vid, 'village_name', uid, 'player_name',
                            aid, 'alliance_name', population, region, is_capital,
                            is_city, has_harbor, victory_points);
"""

import re
from dataclasses import dataclass


@dataclass
class VillageRow:
    map_id: int
    x: int
    y: int
    tid: int  # tribe: 1=Romans, 2=Teutons, 3=Gauls, 6=Egyptians, 7=Huns, 8=Spartans, 9=Vikings
    vid: int  # village id
    name: str
    uid: int  # player id
    player_name: str
    aid: int  # alliance id
    alliance_name: str
    population: int
    # RoF extended fields (None on classic servers)
    region: str | None = None
    is_capital: bool | None = None
    is_city: bool | None = None
    has_harbor: bool | None = None
    victory_points: int | None = None


_ROW_PATTERN = re.compile(
    r"INSERT\s+INTO\s+`?x_world`?\s+VALUES\s*\("
    r"(\d+),"               # 1: map_id
    r"(-?\d+),"             # 2: x
    r"(-?\d+),"             # 3: y
    r"(\d+),"               # 4: tid
    r"(\d+),"               # 5: vid
    r"'((?:[^'\\]|'')*)',"  # 6: village_name
    r"(\d+),"               # 7: uid
    r"'((?:[^'\\]|'')*)',"  # 8: player_name
    r"(\d+),"               # 9: aid
    r"'((?:[^'\\]|'')*)',"  # 10: alliance_name
    r"(\d+),"               # 11: population
    r"(NULL|'(?:[^'\\]|'')*'),"  # 12: region (NULL or 'RegionName')
    r"(TRUE|FALSE|NULL),"   # 13: is_capital
    r"(TRUE|FALSE|NULL),"   # 14: is_city
    r"(TRUE|FALSE|NULL),"   # 15: has_harbor
    r"(\d+|NULL)"           # 16: victory_points
    r"\s*\);",
    re.IGNORECASE,
)


def _unescape_sql(s: str) -> str:
    """Unescape SQL single-quoted string ('' → ')."""
    return s.replace("''", "'")


def _parse_bool(val: str) -> bool | None:
    """Parse SQL boolean: TRUE→True, FALSE→False, NULL→None."""
    v = val.upper()
    if v == "TRUE":
        return True
    if v == "FALSE":
        return False
    return None


def _parse_int_or_none(val: str) -> int | None:
    """Parse SQL int or NULL."""
    if val.upper() == "NULL":
        return None
    return int(val)


def _parse_region(val: str) -> str | None:
    """Parse region: NULL→None, 'Name'→Name."""
    if val.upper() == "NULL":
        return None
    return val.strip("'").replace("''", "'")


def parse_line(line: str) -> VillageRow | None:
    """Parse a single INSERT INTO x_world line. Returns None if not a valid row."""
    m = _ROW_PATTERN.match(line.strip())
    if not m:
        return None
    return VillageRow(
        map_id=int(m.group(1)),
        x=int(m.group(2)),
        y=int(m.group(3)),
        tid=int(m.group(4)),
        vid=int(m.group(5)),
        name=_unescape_sql(m.group(6)),
        uid=int(m.group(7)),
        player_name=_unescape_sql(m.group(8)),
        aid=int(m.group(9)),
        alliance_name=_unescape_sql(m.group(10)),
        population=int(m.group(11)),
        region=_parse_region(m.group(12)),
        is_capital=_parse_bool(m.group(13)),
        is_city=_parse_bool(m.group(14)),
        has_harbor=_parse_bool(m.group(15)),
        victory_points=_parse_int_or_none(m.group(16)),
    )


def parse_map_sql(text: str) -> list[VillageRow]:
    """Parse full map.sql text, return list of VillageRow objects."""
    rows = []
    for line in text.splitlines():
        row = parse_line(line)
        if row is not None:
            rows.append(row)
    return rows
