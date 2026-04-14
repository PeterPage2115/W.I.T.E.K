"""Testy eksportu CSV dla graczy i sojuszy."""

import csv
import io
import pytest
from app import create_app
from app.database import db as _db
from app.models import Player, Alliance


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TRAVIAN_SERVER_URL = "https://test.travian.com"
    TRAVIAN_MAP_SIZE = 401
    TRAVIAN_OUR_ALLIANCES = [1, 2]
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


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield _db.session


def _login(client):
    """Simulate login by setting session data."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["discord_id"] = "123456789"
        sess["discord_name"] = "TestUser"
        sess["role"] = "officer"


def _make_player(db_session, **overrides):
    defaults = dict(
        uid=1,
        name="TestGracz",
        tid=1,
        aid=1,
        alliance_name="TestSojusz",
        total_pop=500,
        village_count=3,
    )
    defaults.update(overrides)
    player = Player(**defaults)
    db_session.add(player)
    db_session.commit()
    return player


def _make_alliance(db_session, **overrides):
    defaults = dict(
        aid=1,
        name="TestSojusz",
        member_count=10,
        total_pop=5000,
    )
    defaults.update(overrides)
    alliance = Alliance(**defaults)
    db_session.add(alliance)
    db_session.commit()
    return alliance


# ── Player CSV Export ──


class TestPlayerExport:
    def test_requires_login(self, client):
        resp = client.get("/players/export")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_requires_role(self, client):
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["discord_id"] = "123456789"
            sess["discord_name"] = "TestUser"
            sess["role"] = "member"
        resp = client.get("/players/export")
        assert resp.status_code == 403

    def test_returns_csv_content_type(self, client, db_session):
        _login(client)
        resp = client.get("/players/export")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/csv")

    def test_csv_disposition_header(self, client, db_session):
        _login(client)
        resp = client.get("/players/export")
        disposition = resp.headers.get("Content-Disposition", "")
        assert "attachment" in disposition
        assert "gracze_eksport.csv" in disposition

    def test_csv_has_header_row(self, client, db_session):
        _login(client)
        resp = client.get("/players/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        header = next(reader)
        assert "Gracz" in header
        assert "Sojusz" in header
        assert "Populacja" in header
        assert "Wioski" in header
        assert "Plemię" in header

    def test_csv_contains_data(self, client, db_session):
        _make_player(db_session, name="SuperGracz")
        _login(client)
        resp = client.get("/players/export")
        text = resp.data.decode("utf-8")
        assert "SuperGracz" in text

    def test_csv_multiple_rows(self, client, db_session):
        _make_player(db_session, uid=1, name="Gracz1")
        _make_player(db_session, uid=2, name="Gracz2")
        _login(client)
        resp = client.get("/players/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 3  # header + 2 data rows

    def test_empty_export(self, client, db_session):
        _login(client)
        resp = client.get("/players/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 1  # header only

    def test_tribe_name_resolved(self, client, db_session):
        _make_player(db_session, uid=1, name="Rzymianin", tid=1)
        _login(client)
        resp = client.get("/players/export")
        text = resp.data.decode("utf-8")
        assert "Rzymianie" in text


# ── Alliance CSV Export ──


class TestAllianceExport:
    def test_requires_login(self, client):
        resp = client.get("/alliances/export")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_requires_role(self, client):
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["discord_id"] = "123456789"
            sess["discord_name"] = "TestUser"
            sess["role"] = "member"
        resp = client.get("/alliances/export")
        assert resp.status_code == 403

    def test_returns_csv_content_type(self, client, db_session):
        _login(client)
        resp = client.get("/alliances/export")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/csv")

    def test_csv_disposition_header(self, client, db_session):
        _login(client)
        resp = client.get("/alliances/export")
        disposition = resp.headers.get("Content-Disposition", "")
        assert "attachment" in disposition
        assert "sojusze_eksport.csv" in disposition

    def test_csv_has_header_row(self, client, db_session):
        _login(client)
        resp = client.get("/alliances/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        header = next(reader)
        assert "Sojusz" in header
        assert "Gracze" in header
        assert "Populacja" in header

    def test_csv_contains_data(self, client, db_session):
        _make_alliance(db_session, name="SuperSojusz")
        _login(client)
        resp = client.get("/alliances/export")
        text = resp.data.decode("utf-8")
        assert "SuperSojusz" in text

    def test_csv_multiple_rows(self, client, db_session):
        _make_alliance(db_session, aid=1, name="Sojusz1")
        _make_alliance(db_session, aid=2, name="Sojusz2")
        _login(client)
        resp = client.get("/alliances/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 3  # header + 2 data rows

    def test_empty_export(self, client, db_session):
        _login(client)
        resp = client.get("/alliances/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 1  # header only
