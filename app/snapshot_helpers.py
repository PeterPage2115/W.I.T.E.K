"""Request-scoped snapshot helper — cached on flask.g."""

from flask import g

from .database import db
from .models import Snapshot


def get_latest_snapshot():
    """Return the latest snapshot, cached per-request on flask.g."""
    if not hasattr(g, "_latest_snapshot"):
        g._latest_snapshot = (
            db.session.query(Snapshot)
            .order_by(Snapshot.fetched_at.desc())
            .first()
        )
    return g._latest_snapshot
