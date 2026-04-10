"""Discord OAuth2 authentication (S5.1)."""

import logging
import secrets
from urllib.parse import urlencode

import requests
from flask import Blueprint, redirect, url_for, session, request, current_app, flash

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__, url_prefix="/auth")

DISCORD_API = "https://discord.com/api/v10"
DISCORD_OAUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"


@bp.route("/login")
def login():
    """Redirect to Discord OAuth2 authorization."""
    client_id = current_app.config.get("DISCORD_CLIENT_ID")
    redirect_uri = current_app.config.get("DISCORD_REDIRECT_URI")

    if not client_id:
        flash("OAuth nie skonfigurowany — ustaw DISCORD_CLIENT_ID", "error")
        logger.warning("OAuth login: DISCORD_CLIENT_ID nie ustawiony")
        return redirect(url_for("dashboard.index"))

    if not redirect_uri:
        flash("OAuth nie skonfigurowany — ustaw DISCORD_REDIRECT_URI", "error")
        logger.warning("OAuth login: DISCORD_REDIRECT_URI nie ustawiony")
        return redirect(url_for("dashboard.index"))

    # CSRF protection — random state token
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
    }
    auth_url = f"{DISCORD_OAUTH_URL}?{urlencode(params)}"
    logger.info("OAuth login: redirect do Discord (redirect_uri=%s)", redirect_uri)
    return redirect(auth_url)


@bp.route("/callback")
def callback():
    """Handle Discord OAuth2 callback."""
    # Check for errors from Discord
    error = request.args.get("error")
    if error:
        error_desc = request.args.get("error_description", error)
        logger.warning("OAuth callback: Discord zwrócił błąd: %s — %s", error, error_desc)
        flash(f"Błąd autoryzacji Discord: {error_desc}", "error")
        return redirect(url_for("dashboard.index"))

    code = request.args.get("code")
    if not code:
        logger.warning("OAuth callback: brak kodu autoryzacji w parametrach")
        flash("Nie otrzymano kodu autoryzacji", "error")
        return redirect(url_for("dashboard.index"))

    # Verify CSRF state
    state = request.args.get("state")
    expected_state = session.pop("oauth_state", None)
    if not state or state != expected_state:
        logger.warning("OAuth callback: nieprawidłowy state (CSRF protection)")
        flash("Nieprawidłowy token bezpieczeństwa — spróbuj ponownie", "error")
        return redirect(url_for("dashboard.index"))

    # Exchange code for token
    data = {
        "client_id": current_app.config["DISCORD_CLIENT_ID"],
        "client_secret": current_app.config["DISCORD_CLIENT_SECRET"],
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": current_app.config["DISCORD_REDIRECT_URI"],
    }
    resp = requests.post(DISCORD_TOKEN_URL, data=data)
    if resp.status_code != 200:
        logger.error(
            "OAuth callback: wymiana kodu nie powiodła się (status=%d, body=%s)",
            resp.status_code, resp.text[:200],
        )
        flash("Błąd autoryzacji Discord", "error")
        return redirect(url_for("dashboard.index"))

    token_data = resp.json()
    access_token = token_data.get("access_token")

    # Get user info
    headers = {"Authorization": f"Bearer {access_token}"}
    user_resp = requests.get(f"{DISCORD_API}/users/@me", headers=headers)
    if user_resp.status_code != 200:
        logger.error(
            "OAuth callback: pobranie danych użytkownika nie powiodło się (status=%d)",
            user_resp.status_code,
        )
        flash("Nie udało się pobrać danych użytkownika", "error")
        return redirect(url_for("dashboard.index"))

    discord_user = user_resp.json()
    discord_id = int(discord_user["id"])
    discord_name = discord_user.get("username", "")

    # Check if user exists in our DB (linked via /tlink)
    from app.models import User
    from app.database import db

    user = User.query.filter_by(discord_id=discord_id).first()
    if not user:
        # Auto-create user with member role
        user = User(discord_id=discord_id, discord_name=discord_name, role="member")
        db.session.add(user)
        db.session.commit()
        logger.info("OAuth: utworzono nowego użytkownika %s (ID: %d)", discord_name, discord_id)
    else:
        # Update discord name if changed
        if user.discord_name != discord_name:
            user.discord_name = discord_name
            db.session.commit()

    # Store in session
    session["user_id"] = user.id
    session["discord_id"] = discord_id
    session["discord_name"] = discord_name
    session["role"] = user.role

    logger.info("OAuth: zalogowano %s (ID: %d, rola: %s)", discord_name, discord_id, user.role)
    flash(f"Zalogowano jako {discord_name}! 🎮", "success")
    return redirect(url_for("dashboard.index"))


@bp.route("/logout")
def logout():
    """Clear session."""
    user = session.get("discord_name", "nieznany")
    session.clear()
    logger.info("OAuth: wylogowano %s", user)
    flash("Wylogowano ✅", "info")
    return redirect(url_for("dashboard.index"))
