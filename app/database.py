from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _expected_column_types(*, is_sqlite):
    false_default = "BOOLEAN DEFAULT 0" if is_sqlite else "BOOLEAN DEFAULT FALSE"
    true_default = "BOOLEAN DEFAULT 1" if is_sqlite else "BOOLEAN DEFAULT TRUE"
    return {
        "attack_reports": {
            "attacker_x": "INTEGER",
            "attacker_y": "INTEGER",
            "wall_level": "INTEGER",
            "crop_amount": "INTEGER",
            "crop_production": "INTEGER",
            "auto_resolved": false_default,
        },
        "battle_reports": {
            "result": "TEXT",
            "is_manual": false_default,
            "reported_by_name": "TEXT",
            "kill_cost_atk": "TEXT",
            "kill_cost_def": "TEXT",
        },
        "alerts": {
            "discord_eligible": true_default,
        },
        "villages": {
            "region": "TEXT",
            "is_capital": "BOOLEAN",
            "is_city": "BOOLEAN",
            "has_harbor": "BOOLEAN",
            "victory_points": "INTEGER",
        },
    }


def _ensure_columns(app):
    """Add missing columns to existing tables (lightweight migration)."""
    engine = db.engine
    is_sqlite = "sqlite" in str(engine.url)
    expected = _expected_column_types(is_sqlite=is_sqlite)
    with engine.connect() as conn:
        for table, cols in expected.items():
            if is_sqlite:
                result = conn.execute(db.text(f"PRAGMA table_info({table})"))
                existing = {row[1] for row in result}
            else:
                result = conn.execute(
                    db.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = :tbl"
                    ),
                    {"tbl": table},
                )
                existing = {row[0] for row in result}
            for col_name, col_type in cols.items():
                if col_name not in existing:
                    conn.execute(
                        db.text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                    )
                    app.logger.info("Migration: added %s.%s", table, col_name)

        # One-time data fix: old alerts created before discord_eligible column
        # had DEFAULT 1, making dashboard-only alerts appear on Discord
        conn.execute(
            db.text(
                "UPDATE alerts SET discord_eligible = false "
                "WHERE alert_type IN ('new_village', 'alliance_change') "
                "AND notified = false"
            )
        )

        conn.commit()


def _enable_wal(app):
    """Enable WAL journal mode for better concurrent access."""
    engine = db.engine
    if "sqlite" in str(engine.url):
        with engine.connect() as conn:
            conn.execute(db.text("PRAGMA journal_mode=WAL"))
            conn.execute(db.text("PRAGMA busy_timeout=5000"))
            conn.commit()
            app.logger.info("SQLite: WAL mode enabled, busy_timeout=5000ms")


def init_db(app):
    """Create all tables if they don't exist yet, then ensure new columns."""
    with app.app_context():
        from . import models  # noqa: F401 — register models
        db.create_all()
        _ensure_columns(app)
        _enable_wal(app)
