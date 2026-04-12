"""Diplomacy route — diplomatic relations page."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session as flask_session
from ..models import DiplomaticRelation
from ..database import db
from ..auth_utils import login_required

bp = Blueprint("diplomacy", __name__)

VALID_RELATION_TYPES = {"ally", "pact", "nap", "war"}


@bp.route("/diplomacy")
def diplomacy():
    relations = (
        DiplomaticRelation.query
        .filter_by(active=True)
        .order_by(DiplomaticRelation.relation_type, DiplomaticRelation.target_alliance_name)
        .all()
    )
    grouped = {}
    for r in relations:
        grouped.setdefault(r.relation_type, []).append(r)

    logged_in = "user_id" in flask_session

    return render_template(
        "diplomacy.html",
        relations=grouped,
        logged_in=logged_in,
    )


@bp.route("/diplomacy/add", methods=["POST"])
@login_required
def diplomacy_add():
    relation_type = request.form.get("relation_type", "").strip()
    target_name = request.form.get("target_alliance_name", "").strip()
    notes = request.form.get("notes", "").strip() or None

    if relation_type not in VALID_RELATION_TYPES:
        flash("❌ Nieprawidłowy typ relacji.", "error")
        return redirect(url_for("diplomacy.diplomacy"))

    if not target_name:
        flash("❌ Nazwa sojuszu jest wymagana.", "error")
        return redirect(url_for("diplomacy.diplomacy"))

    rel = DiplomaticRelation(
        relation_type=relation_type,
        target_alliance_id=0,
        target_alliance_name=target_name,
        created_by=flask_session.get("discord_name", "Nieznany"),
        notes=notes,
        active=True,
    )
    db.session.add(rel)
    db.session.commit()
    flash(f"✅ Dodano relację z {target_name}.", "success")
    return redirect(url_for("diplomacy.diplomacy"))


@bp.route("/diplomacy/<int:rel_id>/edit", methods=["POST"])
@login_required
def diplomacy_edit(rel_id):
    rel = db.session.get(DiplomaticRelation, rel_id)
    if not rel or not rel.active:
        flash("❌ Relacja nie została znaleziona.", "error")
        return redirect(url_for("diplomacy.diplomacy"))

    new_type = request.form.get("relation_type", "").strip()
    new_notes = request.form.get("notes", "").strip() or None

    if new_type and new_type in VALID_RELATION_TYPES:
        rel.relation_type = new_type
    elif new_type:
        flash("❌ Nieprawidłowy typ relacji.", "error")
        return redirect(url_for("diplomacy.diplomacy"))

    rel.notes = new_notes
    db.session.commit()
    flash(f"✅ Zaktualizowano relację z {rel.target_alliance_name}.", "success")
    return redirect(url_for("diplomacy.diplomacy"))


@bp.route("/diplomacy/<int:rel_id>/delete", methods=["POST"])
@login_required
def diplomacy_delete(rel_id):
    rel = db.session.get(DiplomaticRelation, rel_id)
    if not rel or not rel.active:
        flash("❌ Relacja nie została znaleziona.", "error")
        return redirect(url_for("diplomacy.diplomacy"))

    rel.active = False
    db.session.commit()
    flash(f"✅ Dezaktywowano relację z {rel.target_alliance_name}.", "success")
    return redirect(url_for("diplomacy.diplomacy"))
