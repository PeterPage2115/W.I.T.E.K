"""Apply SQL migrations from migrations/ in alphabetical order.

Tracks applied migrations in a `_migrations` table so each file
runs at most once.  Works with both PostgreSQL and SQLite.
"""

import os
import sys
from datetime import datetime, timezone

# Ensure project root is on sys.path so `app` package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.database import db


MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"
)


def _ensure_migrations_table():
    """Create the tracking table if it doesn't exist."""
    db.session.execute(
        db.text(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "  filename TEXT PRIMARY KEY,"
            "  applied_at TIMESTAMP NOT NULL"
            ")"
        )
    )
    db.session.commit()


def _applied_migrations() -> set[str]:
    rows = db.session.execute(db.text("SELECT filename FROM _migrations"))
    return {row[0] for row in rows}


def _pending_files(applied: set[str]) -> list[str]:
    if not os.path.isdir(MIGRATIONS_DIR):
        return []
    files = sorted(
        f for f in os.listdir(MIGRATIONS_DIR)
        if f.endswith(".sql") and f not in applied
    )
    return files


def apply_migrations():
    app = create_app()
    with app.app_context():
        _ensure_migrations_table()
        applied = _applied_migrations()
        pending = _pending_files(applied)

        if not pending:
            app.logger.info("Migrations: all up-to-date.")
            return

        for filename in pending:
            path = os.path.join(MIGRATIONS_DIR, filename)
            app.logger.info("Migrations: applying %s …", filename)
            with open(path, "r", encoding="utf-8") as fh:
                sql = fh.read().strip()
            if not sql:
                app.logger.info("Migrations: %s is empty, skipping.", filename)
            else:
                for statement in _split_statements(sql):
                    try:
                        db.session.execute(db.text(statement))
                    except Exception as exc:
                        msg = str(exc).lower()
                        # Tolerate columns/indexes that already exist
                        if "duplicate column" in msg or "already exists" in msg:
                            app.logger.info(
                                "Migrations: %s — skipped (already applied): %s",
                                filename, exc,
                            )
                            db.session.rollback()
                        else:
                            raise
            db.session.execute(
                db.text(
                    "INSERT INTO _migrations (filename, applied_at) "
                    "VALUES (:fn, :ts)"
                ),
                {"fn": filename, "ts": datetime.now(timezone.utc)},
            )
            db.session.commit()
            app.logger.info("Migrations: %s applied ✓", filename)

        app.logger.info("Migrations: %d new migration(s) applied.", len(pending))


def _split_statements(sql: str) -> list[str]:
    """Split SQL text on semicolons, ignoring empty fragments."""
    return [s.strip() for s in sql.split(";") if s.strip()]


if __name__ == "__main__":
    apply_migrations()
