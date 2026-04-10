from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _ensure_columns(app):
    """Add missing columns to existing tables (lightweight migration)."""
    expected = {
        "attack_reports": {
            "attacker_x": "INTEGER",
            "attacker_y": "INTEGER",
            "wall_level": "INTEGER",
            "crop_amount": "INTEGER",
            "crop_production": "INTEGER",
            "auto_resolved": "BOOLEAN DEFAULT 0",
        },
        "battle_reports": {
            "result": "TEXT",
            "is_manual": "BOOLEAN DEFAULT 0",
            "reported_by_name": "TEXT",
            "kill_cost_atk": "TEXT",
            "kill_cost_def": "TEXT",
        },
    }
    engine = db.engine
    with engine.connect() as conn:
        for table, cols in expected.items():
            result = conn.execute(db.text(f"PRAGMA table_info({table})"))
            existing = {row[1] for row in result}
            for col_name, col_type in cols.items():
                if col_name not in existing:
                    conn.execute(
                        db.text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                    )
                    app.logger.info("Migration: added %s.%s", table, col_name)
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
