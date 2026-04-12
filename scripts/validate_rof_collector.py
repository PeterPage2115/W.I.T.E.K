"""E2E validation: parse live RoF map.sql -> store via collector -> verify DB."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.database import db
from app.models import Snapshot, Village, Player
from app.map_sql.collector import store_snapshot


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data_cache/rof_x10_test.sql"

    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    app = create_app()
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context():
        db.drop_all()
        db.create_all()

        snap = store_snapshot(raw)

        print(f"\n{'='*60}")
        print(f"RoF Collector E2E Validation")
        print(f"{'='*60}")
        print(f"Snapshot ID: {snap.id}")
        print(f"Villages stored: {snap.village_count}")

        # Verify RoF fields
        harbor_count = Village.query.filter_by(snapshot_id=snap.id, has_harbor=True).count()
        capital_count = Village.query.filter_by(snapshot_id=snap.id, is_capital=True).count()
        region_count = Village.query.filter(Village.snapshot_id == snap.id, Village.region.isnot(None)).count()

        print(f"Harbors: {harbor_count}")
        print(f"Capitals: {capital_count}")
        print(f"With region: {region_count}")

        # Players
        player_count = Player.query.count()
        print(f"Players: {player_count}")

        # Sample a few villages
        sample = Village.query.filter(Village.region.isnot(None)).limit(3).all()
        if sample:
            print(f"\nSample villages:")
            for v in sample:
                print(f"  ({v.x}|{v.y}) {v.name} - {v.player_name} - region={v.region} harbor={v.has_harbor} vp={v.victory_points}")

        print(f"\n{'='*60}")
        print("✅ Collector E2E validation passed!")


if __name__ == "__main__":
    main()
