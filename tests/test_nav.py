"""Testy nawigacji: aktywne podświetlanie + tytuł strony."""

import re

import pytest
from app import create_app
from app.database import db as _db


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TRAVIAN_SERVER_URL = "https://test.travian.com"
    TRAVIAN_MAP_SIZE = 401
    TRAVIAN_OUR_ALLIANCES = [1]
    POP_DROP_THRESHOLD = 15
    NEW_VILLAGE_RADIUS = 30
    DISCORD_TOKEN = ""
    DISCORD_GUILD_ID = None
    DISCORD_ALERTS_CHANNEL_ID = None
    DISCORD_DEFENSE_FORUM_ID = None
    DISCORD_DEF_ROLE_ID = None
    ALLIANCE_PASSWORD = ""
    EXT_API_TOKEN = "test-token"
    SECRET_KEY = "test-secret"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


class TestTitle:
    """Tytuł strony nie powinien duplikować 'W.I.T.E.K'."""

    def test_dashboard_title(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert "<title>Panel Dowodzenia — W.I.T.E.K</title>" in html

    def test_no_double_witek(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert "W.I.T.E.K — W.I.T.E.K" not in html


class TestActiveNav:
    """Aktywna strona powinna mieć klasę text-trav-gold."""

    def test_dashboard_active(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'text-trav-gold font-semibold' in html
        assert 'href="/"' in html

    def test_attacks_active(self, client):
        resp = client.get("/attacks")
        html = resp.data.decode()
        # Ataki link should be active (gold + semibold)
        assert 'class="text-trav-gold font-semibold' in html
        # Check that the active class is on the attacks link specifically
        active_links = re.findall(
            r'href="([^"]+)"[^>]*class="text-trav-gold font-semibold', html
        )
        assert "/attacks" in active_links
        assert "/" not in active_links

    def test_defense_active(self, client):
        resp = client.get("/defense")
        html = resp.data.decode()
        active_links = re.findall(
            r'href="([^"]+)"[^>]*class="text-trav-gold font-semibold', html
        )
        assert "/defense" in active_links

    def test_reports_active(self, client):
        resp = client.get("/reports")
        html = resp.data.decode()
        active_links = re.findall(
            r'href="([^"]+)"[^>]*class="text-trav-gold font-semibold', html
        )
        assert "/reports" in active_links

    def test_attack_detail_highlights_attacks(self, app):
        """Sub-page /attacks/<id> should highlight Ataki."""
        with app.test_request_context("/attacks/999"):
            from flask import render_template_string
            html = render_template_string(
                '{% extends "base.html" %}{% block content %}test{% endblock %}',
            )
            active_links = re.findall(
                r'href="([^"]+)"[^>]*class="text-trav-gold font-semibold', html
            )
            assert "/attacks" in active_links
            assert "/" not in active_links


class TestNoDuplicateNavLinks:
    """Nie powinno być zduplikowanych linków w nawigacji."""

    def test_attacks_no_duplicate(self, client):
        resp = client.get("/attacks")
        html = resp.data.decode()
        count = html.count(">⚔️ Ataki</a>")
        # Exactly 2: one desktop, one mobile
        assert count == 2, f"Expected 2 Ataki links (desktop+mobile), got {count}"

    def test_defense_no_duplicate(self, client):
        resp = client.get("/defense")
        html = resp.data.decode()
        count = html.count(">🛡️ Obrona</a>")
        assert count == 2, f"Expected 2 Obrona links (desktop+mobile), got {count}"

    def test_reports_no_duplicate(self, client):
        resp = client.get("/reports")
        html = resp.data.decode()
        count = html.count(">📜 Raporty</a>")
        assert count == 2, f"Expected 2 Raporty links (desktop+mobile), got {count}"
