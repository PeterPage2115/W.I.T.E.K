"""Testy dla tras raportów (app/routes/reports.py)."""

import json
import pytest
from datetime import datetime, timezone
from app import create_app
from app.database import db as _db
from app.models import Snapshot, BattleReport
from app.routes.reports import _get_unit_name, _build_unit_names, _UNIT_NAMES


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


def _make_report(db_session, **overrides):
    """Helper to create a BattleReport with sensible defaults."""
    defaults = dict(
        attacker_name="Atakujący",
        defender_name="Obrońca",
        attacker_troops=json.dumps({"1": 100}),
        attacker_losses=json.dumps({"1": 30}),
        defender_troops=json.dumps({"21": 200}),
        defender_losses=json.dumps({"21": 80}),
    )
    defaults.update(overrides)
    report = BattleReport(**defaults)
    db_session.add(report)
    db_session.commit()
    return report


class TestUnitNameMapping:
    def test_gaul_unit_21_is_falangita(self):
        names = _build_unit_names()
        assert names.get("21") == "Falangita"

    def test_teuton_unit_11_is_palkarz(self):
        names = _build_unit_names()
        assert names.get("11") == "Pałkarz"

    def test_unknown_unit_returns_fallback(self, app):
        with app.app_context():
            name = _get_unit_name("999")
            assert name == "Jednostka #999"

    def test_hero_mapping(self):
        names = _build_unit_names()
        assert names.get("hero") == "Bohater"

    def test_roman_unit_1(self):
        names = _build_unit_names()
        # Unit 1 is the first Roman unit
        assert "1" in names


class TestReportList:
    def test_empty_reports_returns_200(self, client):
        resp = client.get("/reports")
        assert resp.status_code == 200

    def test_reports_list_with_data(self, client, db_session):
        _make_report(db_session, attacker_name="Agresor", defender_name="Obrona")
        resp = client.get("/reports")
        assert resp.status_code == 200
        assert b"Agresor" in resp.data

    def test_reports_list_shows_multiple(self, client, db_session):
        _make_report(db_session, attacker_name="Atak1", defender_name="Def1")
        _make_report(db_session, attacker_name="Atak2", defender_name="Def2")
        resp = client.get("/reports")
        assert resp.status_code == 200
        assert b"Atak1" in resp.data
        assert b"Atak2" in resp.data

    def test_reports_filter_by_player(self, client, db_session):
        _make_report(db_session, attacker_name="UniquePlayer", defender_name="Def")
        _make_report(db_session, attacker_name="Other", defender_name="OtherDef")
        resp = client.get("/reports?player=UniquePlayer")
        assert resp.status_code == 200
        assert b"UniquePlayer" in resp.data

    def test_reports_pagination_returns_200(self, client, db_session):
        for i in range(30):
            _make_report(db_session, attacker_name=f"Atak{i}", defender_name=f"Def{i}")
        resp = client.get("/reports?page=2")
        assert resp.status_code == 200


class TestReportDetail:
    def test_nonexistent_report_returns_404(self, client):
        resp = client.get("/reports/9999")
        assert resp.status_code == 404

    def test_existing_report_returns_200(self, client, db_session):
        report = _make_report(db_session)
        resp = client.get(f"/reports/{report.id}")
        assert resp.status_code == 200

    def test_report_detail_shows_attacker(self, client, db_session):
        report = _make_report(db_session, attacker_name="WidocznyAtakujacy")
        resp = client.get(f"/reports/{report.id}")
        assert resp.status_code == 200
        assert "WidocznyAtakujacy".encode() in resp.data

    def test_report_detail_shows_defender(self, client, db_session):
        report = _make_report(db_session, defender_name="WidocznyObronca")
        resp = client.get(f"/reports/{report.id}")
        assert resp.status_code == 200
        assert "WidocznyObronca".encode() in resp.data

    def test_report_detail_with_bounty(self, client, db_session):
        report = _make_report(
            db_session,
            bounty=json.dumps({"lumber": 500, "clay": 300, "iron": 200, "crop": 100}),
        )
        resp = client.get(f"/reports/{report.id}")
        assert resp.status_code == 200

    def test_report_detail_with_result_field(self, client, db_session):
        report = _make_report(db_session, result="wygrana_obrony")
        resp = client.get(f"/reports/{report.id}")
        assert resp.status_code == 200
