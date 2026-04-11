"""Testy modułu dyplomacji (model, trasy, logika)."""

import pytest
from datetime import datetime, timezone
from app import create_app
from app.database import db as _db
from app.models import DiplomaticRelation, Alliance


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


def _make_relation(db_session, **overrides):
    """Helper to create a DiplomaticRelation with defaults."""
    defaults = dict(
        relation_type="ally",
        target_alliance_id=10,
        target_alliance_name="TestAlliance",
        created_by="Gracz",
        notes=None,
        active=True,
    )
    defaults.update(overrides)
    rel = DiplomaticRelation(**defaults)
    db_session.add(rel)
    db_session.commit()
    return rel


# ── Model tests ──────────────────────────────────────────────────────────


class TestDiplomaticRelationModel:
    def test_create_relation(self, db_session):
        rel = _make_relation(db_session)
        assert rel.id is not None
        assert rel.relation_type == "ally"
        assert rel.target_alliance_name == "TestAlliance"
        assert rel.active is True

    def test_default_created_at(self, db_session):
        rel = _make_relation(db_session)
        assert rel.created_at is not None
        assert isinstance(rel.created_at, datetime)

    def test_relation_types(self, db_session):
        for rtype in ("ally", "pact", "nap", "war"):
            rel = _make_relation(
                db_session,
                relation_type=rtype,
                target_alliance_name=f"Alliance_{rtype}",
                target_alliance_id=100 + hash(rtype) % 100,
            )
            assert rel.relation_type == rtype

    def test_deactivation(self, db_session):
        rel = _make_relation(db_session)
        assert rel.active is True
        rel.active = False
        db_session.commit()
        refreshed = DiplomaticRelation.query.get(rel.id)
        assert refreshed.active is False

    def test_notes_nullable(self, db_session):
        rel_no_notes = _make_relation(db_session, notes=None)
        assert rel_no_notes.notes is None
        rel_with_notes = _make_relation(
            db_session,
            notes="Ważny pakt",
            target_alliance_name="Other",
            target_alliance_id=20,
        )
        assert rel_with_notes.notes == "Ważny pakt"


# ── Route tests ──────────────────────────────────────────────────────────


class TestDiplomacyRoute:
    def test_empty_page(self, client):
        resp = client.get("/diplomacy")
        assert resp.status_code == 200
        assert "Brak aktywnych relacji" in resp.data.decode("utf-8")

    def test_shows_relations(self, client, db_session):
        _make_relation(db_session, relation_type="ally", target_alliance_name="UFOLODZY2")
        _make_relation(db_session, relation_type="war", target_alliance_name="ENEMY", target_alliance_id=99)
        resp = client.get("/diplomacy")
        assert resp.status_code == 200
        assert b"UFOLODZY2" in resp.data
        assert b"ENEMY" in resp.data

    def test_inactive_not_shown(self, client, db_session):
        _make_relation(db_session, target_alliance_name="Hidden", active=False)
        resp = client.get("/diplomacy")
        assert resp.status_code == 200
        assert b"Hidden" not in resp.data

    def test_grouping(self, client, db_session):
        _make_relation(db_session, relation_type="ally", target_alliance_name="Friend1")
        _make_relation(db_session, relation_type="ally", target_alliance_name="Friend2", target_alliance_id=11)
        _make_relation(db_session, relation_type="war", target_alliance_name="Foe", target_alliance_id=20)
        resp = client.get("/diplomacy")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Sojusze" in html
        assert "Wojny" in html
        assert "Friend1" in html
        assert "Friend2" in html
        assert "Foe" in html

    def test_notes_displayed(self, client, db_session):
        _make_relation(db_session, notes="Ważna umowa")
        resp = client.get("/diplomacy")
        assert "Ważna umowa" in resp.data.decode("utf-8")

    def test_created_by_displayed(self, client, db_session):
        _make_relation(db_session, created_by="Dowódca")
        resp = client.get("/diplomacy")
        assert "Dowódca" in resp.data.decode("utf-8")
