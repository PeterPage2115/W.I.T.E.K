"""Testy eksportu CSV dla ataków i raportów bitewnych."""

import csv
import io
import pytest
from datetime import datetime, timezone
from app import create_app
from app.database import db as _db
from app.models import AttackReport, BattleReport


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


def _make_attack(db_session, **overrides):
    defaults = dict(
        reported_by_discord="123456789",
        reported_by_name="Gracz",
        attacker_name="Wróg",
        attacker_alliance="ZliSojusz",
        defender_name="Nasz",
        defender_village="Wioska",
        defender_x=10,
        defender_y=20,
        attack_time="14:30",
        notes="Uwaga!",
        status="reported",
    )
    defaults.update(overrides)
    attack = AttackReport(**defaults)
    db_session.add(attack)
    db_session.commit()
    return attack


def _make_report(db_session, **overrides):
    defaults = dict(
        attacker_name="Agresor",
        attacker_alliance="ZliSojusz",
        defender_name="Obrońca",
        defender_alliance="NaszSojusz",
        attacker_village="Wioska Agresora",
        defender_village="Wioska Obrońcy",
        attacker_losses='{"1": 50}',
        defender_losses='{"21": 30}',
        bounty='{"lumber": 100}',
        result="wygrana_obrony",
        reported_by_name="Gracz",
    )
    defaults.update(overrides)
    report = BattleReport(**defaults)
    db_session.add(report)
    db_session.commit()
    return report


# ── Attack CSV Export ──


class TestAttackExport:
    def test_requires_login(self, client):
        resp = client.get("/attacks/export")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_requires_role(self, client):
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["discord_id"] = "123456789"
            sess["discord_name"] = "TestUser"
            sess["role"] = "member"
        resp = client.get("/attacks/export")
        assert resp.status_code == 403

    def test_returns_csv_content_type(self, client, db_session):
        _login(client)
        resp = client.get("/attacks/export")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/csv")

    def test_csv_disposition_header(self, client, db_session):
        _login(client)
        resp = client.get("/attacks/export")
        disposition = resp.headers.get("Content-Disposition", "")
        assert "attachment" in disposition
        assert "ataki_eksport.csv" in disposition

    def test_csv_has_header_row(self, client, db_session):
        _login(client)
        resp = client.get("/attacks/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        header = next(reader)
        assert "ID" in header
        assert "Atakujący" in header
        assert "Status" in header

    def test_csv_contains_data(self, client, db_session):
        _make_attack(db_session, attacker_name="TestWrog")
        _login(client)
        resp = client.get("/attacks/export")
        text = resp.data.decode("utf-8")
        assert "TestWrog" in text

    def test_csv_multiple_rows(self, client, db_session):
        _make_attack(db_session, attacker_name="Wrog1")
        _make_attack(db_session, attacker_name="Wrog2")
        _login(client)
        resp = client.get("/attacks/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 3  # header + 2 data rows

    def test_empty_export(self, client, db_session):
        _login(client)
        resp = client.get("/attacks/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 1  # header only


# ── Battle Report CSV Export ──


class TestReportExport:
    def test_requires_login(self, client):
        resp = client.get("/reports/export")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_requires_role(self, client):
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["discord_id"] = "123456789"
            sess["discord_name"] = "TestUser"
            sess["role"] = "member"
        resp = client.get("/reports/export")
        assert resp.status_code == 403

    def test_returns_csv_content_type(self, client, db_session):
        _login(client)
        resp = client.get("/reports/export")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/csv")

    def test_csv_disposition_header(self, client, db_session):
        _login(client)
        resp = client.get("/reports/export")
        disposition = resp.headers.get("Content-Disposition", "")
        assert "attachment" in disposition
        assert "raporty_eksport.csv" in disposition

    def test_csv_has_header_row(self, client, db_session):
        _login(client)
        resp = client.get("/reports/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        header = next(reader)
        assert "ID" in header
        assert "Atakujący" in header
        assert "Wynik" in header

    def test_csv_contains_data(self, client, db_session):
        _make_report(db_session, attacker_name="TestAgresor")
        _login(client)
        resp = client.get("/reports/export")
        text = resp.data.decode("utf-8")
        assert "TestAgresor" in text

    def test_csv_multiple_rows(self, client, db_session):
        _make_report(db_session, attacker_name="Agresor1")
        _make_report(db_session, attacker_name="Agresor2")
        _login(client)
        resp = client.get("/reports/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 3  # header + 2 data rows

    def test_empty_export(self, client, db_session):
        _login(client)
        resp = client.get("/reports/export")
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 1  # header only
