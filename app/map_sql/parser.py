"""Parser for Travian map.sql file.

The map.sql file contains INSERT statements like:
INSERT INTO x_world VALUES (id, x, y, tid, vid, 'village_name', uid, 'player_name',
                            aid, 'alliance_name', population, NULL, FALSE, NULL, NULL, NULL);
"""

import re
from dataclasses import dataclass


@dataclass
class VillageRow:
    map_id: int
    x: int
    y: int
    tid: int  # tribe: 1=Romans, 2=Teutons, 3=Gauls
    vid: int  # village id
    name: str
    uid: int  # player id
    player_name: str
    aid: int  # alliance id
    alliance_name: str
    population: int


# Matches one VALUES(...) group from INSERT INTO x_world VALUES (...);
_ROW_PATTERN = re.compile(
    r"INSERT\s+INTO\s+`?x_world`?\s+VALUES\s*\("
    r"(\d+),"       # map_id
    r"(-?\d+),"     # x
    r"(-?\d+),"     # y
    r"(\d+),"       # tid
    r"(\d+),"       # vid
    r"'((?:[^'\\]|'')*)',"  # village_name (escaped single quotes)
    r"(\d+),"       # uid
    r"'((?:[^'\\]|'')*)',"  # player_name
    r"(\d+),"       # aid
    r"'((?:[^'\\]|'')*)',"  # alliance_name
    r"(\d+)"        # population
    r"(?:,\s*(?:NULL|FALSE|TRUE|\d+))*"  # extra trailing fields (unknown)
    r"\s*\);",
    re.IGNORECASE,
)


def _unescape_sql(s: str) -> str:
    """Unescape SQL single-quoted string ('' → ')."""
    return s.replace("''", "'")


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
    )


def parse_map_sql(text: str) -> list[VillageRow]:
    """Parse full map.sql text, return list of VillageRow objects."""
    rows = []
    for line in text.splitlines():
        row = parse_line(line)
        if row is not None:
            rows.append(row)
    return rows
