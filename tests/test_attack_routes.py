"""Testy dla tras ataków (app/routes/attacks.py)."""

import json
import pytest
from datetime import datetime, timezone
from app import create_app
from app.database import db as _db
from app.models import AttackReport, BattleReport, TroopSupport, DefenseThread


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


def _make_attack(db_session, **overrides):
    """Helper to create an AttackReport with sensible defaults."""
    defaults = dict(
        reported_by_discord="123456789",
        reported_by_name="Gracz",
        attacker_name="Wróg",
        defender_name="Nasz",
        defender_village="Wioska",
        defender_x=10,
        defender_y=20,
        status="reported",
    )
    defaults.update(overrides)
    attack = AttackReport(**defaults)
    db_session.add(attack)
    db_session.commit()
    return attack


class TestAttackList:
    def test_empty_attacks_returns_200(self, client):
        resp = client.get("/attacks")
        assert resp.status_code == 200

    def test_attacks_with_data(self, client, db_session):
        _make_attack(db_session, attacker_name="ZlyGracz")
        resp = client.get("/attacks")
        assert resp.status_code == 200
        assert b"ZlyGracz" in resp.data

    def test_attacks_shows_multiple(self, client, db_session):
        _make_attack(db_session, attacker_name="Wrog1")
        _make_attack(db_session, attacker_name="Wrog2")
        resp = client.get("/attacks")
        assert resp.status_code == 200
        assert b"Wrog1" in resp.data
        assert b"Wrog2" in resp.data

    def test_attacks_filter_by_status(self, client, db_session):
        _make_attack(db_session, attacker_name="Aktywny", status="reported")
        _make_attack(db_session, attacker_name="Zamkniety", status="resolved")
        resp = client.get("/attacks?status=resolved")
        assert resp.status_code == 200
        assert b"Zamkniety" in resp.data

    def test_attacks_filter_all_status(self, client, db_session):
        _make_attack(db_session, status="reported")
        _make_attack(db_session, status="resolved")
        resp = client.get("/attacks?status=all")
        assert resp.status_code == 200

    def test_attacks_counts_shown(self, client, db_session):
        _make_attack(db_session, status="reported")
        _make_attack(db_session, status="resolved")
        resp = client.get("/attacks")
        assert resp.status_code == 200


class TestAttackDetail:
    def test_nonexistent_attack_returns_404(self, client):
        resp = client.get("/attacks/9999")
        assert resp.status_code == 404

    def test_existing_attack_returns_200(self, client, db_session):
        attack = _make_attack(db_session)
        resp = client.get(f"/attacks/{attack.id}")
        assert resp.status_code == 200

    def test_attack_detail_shows_attacker(self, client, db_session):
        attack = _make_attack(db_session, attacker_name="WidocznyWrog")
        resp = client.get(f"/attacks/{attack.id}")
        assert resp.status_code == 200
        assert b"WidocznyWrog" in resp.data

    def test_attack_detail_shows_defender(self, client, db_session):
        attack = _make_attack(db_session, defender_name="NaszGracz")
        resp = client.get(f"/attacks/{attack.id}")
        assert resp.status_code == 200
        assert b"NaszGracz" in resp.data

    def test_attack_detail_with_support(self, client, db_session):
        attack = _make_attack(db_session)
        support = TroopSupport(
            from_x=5, from_y=5, to_x=10, to_y=20,
            player_discord_id="999", player_name="Pomocnik",
            troops=json.dumps({"21": 50}),
            attack_report_id=attack.id,
        )
        db_session.add(support)
        db_session.commit()
        resp = client.get(f"/attacks/{attack.id}")
        assert resp.status_code == 200

    def test_attack_detail_with_battle_reports(self, client, db_session):
        attack = _make_attack(db_session)
        report = BattleReport(
            attack_report_id=attack.id,
            attacker_name="Wróg",
            defender_name="Nasz",
            attacker_troops=json.dumps({"1": 100}),
            attacker_losses=json.dumps({"1": 30}),
            defender_troops=json.dumps({"21": 200}),
            defender_losses=json.dumps({"21": 80}),
        )
        db_session.add(report)
        db_session.commit()
        resp = client.get(f"/attacks/{attack.id}")
        assert resp.status_code == 200

    def test_attack_detail_with_distance(self, client, db_session):
        attack = _make_attack(
            db_session,
            attacker_x=0, attacker_y=0,
            defender_x=3, defender_y=4,
        )
        resp = client.get(f"/attacks/{attack.id}")
        assert resp.status_code == 200

    def test_attack_detail_with_defense_thread(self, client, db_session):
        attack = _make_attack(db_session, forum_thread_id=111222333)
        thread = DefenseThread(
            forum_thread_id=111222333,
            defender_x=10, defender_y=20,
            defender_village="Wioska", defender_player="Nasz",
        )
        db_session.add(thread)
        db_session.commit()
        resp = client.get(f"/attacks/{attack.id}")
        assert resp.status_code == 200
