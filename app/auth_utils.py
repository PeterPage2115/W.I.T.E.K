"""Role-based access control decorators (S5.2)."""

from functools import wraps
from flask import session, redirect, url_for, flash, abort


def login_required(f):
    """Require user to be logged in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Musisz się zalogować 🔒", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Require user to have one of the specified roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                flash("Musisz się zalogować 🔒", "warning")
                return redirect(url_for("auth.login"))
            user_role = session.get("role", "member")
            if user_role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def get_current_user():
    """Get current user info from session (or None)."""
    if "user_id" not in session:
        return None
    return {
        "id": session["user_id"],
        "discord_id": session["discord_id"],
        "discord_name": session["discord_name"],
        "role": session["role"],
    }
