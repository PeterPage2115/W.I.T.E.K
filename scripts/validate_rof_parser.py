"""Validate 16-field parser against live RoF map.sql data."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.map_sql.parser import parse_line
from collections import Counter


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data_cache/rof_x10_test.sql"

    total = 0
    parsed = 0
    failed_lines = []
    regions = Counter()
    tribes = Counter()
    capitals = 0
    cities = 0
    harbors = 0
    vp_total = 0

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or not line.upper().startswith("INSERT"):
                continue
            total += 1
            row = parse_line(line)
            if row is None:
                failed_lines.append(line[:120])
                continue
            parsed += 1

            if row.region:
                regions[row.region] += 1
            tribes[row.tid] += 1
            if row.is_capital:
                capitals += 1
            if row.is_city:
                cities += 1
            if row.has_harbor:
                harbors += 1
            if row.victory_points:
                vp_total += row.victory_points

    print(f"\n{'='*60}")
    print(f"RoF Parser Validation Report")
    print(f"{'='*60}")
    print(f"Total INSERT lines: {total}")
    print(f"Successfully parsed: {parsed}")
    print(f"Failed to parse:    {total - parsed}")
    print(f"Success rate:       {parsed/total*100:.1f}%")
    print(f"\nTribes:")
    tribe_names = {1: "Romans", 2: "Teutons", 3: "Gauls", 4: "Nature", 5: "Natars",
                   6: "Egyptians", 7: "Huns", 8: "Spartans", 9: "Vikings"}
    for tid in sorted(tribes):
        print(f"  {tid} ({tribe_names.get(tid, '?')}): {tribes[tid]}")

    print(f"\nRoF Features:")
    print(f"  Regions: {len(regions)} unique ({sum(regions.values())} villages with region)")
    if regions:
        print(f"  Top regions: {regions.most_common(5)}")
    print(f"  Capitals: {capitals}")
    print(f"  Cities: {cities}")
    print(f"  Harbors: {harbors}")
    print(f"  Total VP: {vp_total}")

    if failed_lines:
        print(f"\nFailed lines (first 5):")
        for fl in failed_lines[:5]:
            print(f"  {fl}")

    print(f"\n{'='*60}")

    if total - parsed > 0:
        print(f"⚠️  {total - parsed} lines failed to parse!")
        return 1
    else:
        print("✅ All lines parsed successfully!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
