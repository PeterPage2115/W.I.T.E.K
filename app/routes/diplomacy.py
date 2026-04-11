"""Diplomacy route — diplomatic relations page."""

from flask import Blueprint, render_template
from ..models import DiplomaticRelation, Snapshot
from ..database import db

bp = Blueprint("diplomacy", __name__)


@bp.route("/diplomacy")
def diplomacy():
    latest_snapshot = (
        db.session.query(Snapshot).order_by(Snapshot.fetched_at.desc()).first()
    )

    relations = (
        DiplomaticRelation.query
        .filter_by(active=True)
        .order_by(DiplomaticRelation.relation_type, DiplomaticRelation.target_alliance_name)
        .all()
    )
    grouped = {}
    for r in relations:
        grouped.setdefault(r.relation_type, []).append(r)

    return render_template(
        "diplomacy.html",
        snapshot=latest_snapshot,
        relations=grouped,
    )
