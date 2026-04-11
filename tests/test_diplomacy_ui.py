"""Tests for diplomacy UI: add/edit/delete forms and routes."""

import pytest
from app import create_app
from app.database import db as _db
from app.models import DiplomaticRelation


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
        sess["discord_id"] = "123456"
        sess["discord_name"] = "TestUser"
        sess["role"] = "officer"


def _make_relation(db_session, **overrides):
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


# ── Add form visibility ─────────────────────────────────────────────────


class TestAddFormVisibility:
    def test_add_form_visible_when_logged_in(self, client, db_session):
        _login(client)
        resp = client.get("/diplomacy")
        html = resp.data.decode("utf-8")
        assert "Dodaj relację" in html

    def test_add_form_hidden_when_not_logged_in(self, client, db_session):
        resp = client.get("/diplomacy")
        html = resp.data.decode("utf-8")
        assert "Dodaj relację" not in html


# ── Add relation route ───────────────────────────────────────────────────


class TestAddRelation:
    def test_add_relation_success(self, client, db_session):
        _login(client)
        resp = client.post("/diplomacy/add", data={
            "relation_type": "war",
            "target_alliance_name": "ENEMY",
            "notes": "Aktywny konflikt",
        }, follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert "Dodano relację" in html
        rel = DiplomaticRelation.query.filter_by(target_alliance_name="ENEMY").first()
        assert rel is not None
        assert rel.relation_type == "war"
        assert rel.notes == "Aktywny konflikt"
        assert rel.created_by == "TestUser"

    def test_add_relation_empty_name(self, client, db_session):
        _login(client)
        resp = client.post("/diplomacy/add", data={
            "relation_type": "ally",
            "target_alliance_name": "",
        }, follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert "Nazwa sojuszu jest wymagana" in html

    def test_add_relation_invalid_type(self, client, db_session):
        _login(client)
        resp = client.post("/diplomacy/add", data={
            "relation_type": "invalid",
            "target_alliance_name": "X",
        }, follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert "Nieprawidłowy typ relacji" in html

    def test_add_relation_requires_login(self, client, db_session):
        resp = client.post("/diplomacy/add", data={
            "relation_type": "ally",
            "target_alliance_name": "Friend",
        })
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_add_relation_no_notes(self, client, db_session):
        _login(client)
        client.post("/diplomacy/add", data={
            "relation_type": "nap",
            "target_alliance_name": "Neutral",
            "notes": "",
        }, follow_redirects=True)
        rel = DiplomaticRelation.query.filter_by(target_alliance_name="Neutral").first()
        assert rel is not None
        assert rel.notes is None


# ── Edit relation route ──────────────────────────────────────────────────


class TestEditRelation:
    def test_edit_notes(self, client, db_session):
        _login(client)
        rel = _make_relation(db_session, notes="stare")
        resp = client.post(f"/diplomacy/{rel.id}/edit", data={
            "relation_type": "ally",
            "notes": "nowe notatki",
        }, follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert "Zaktualizowano relację" in html
        db_session.refresh(rel)
        assert rel.notes == "nowe notatki"

    def test_edit_type(self, client, db_session):
        _login(client)
        rel = _make_relation(db_session, relation_type="nap")
        client.post(f"/diplomacy/{rel.id}/edit", data={
            "relation_type": "war",
            "notes": "",
        }, follow_redirects=True)
        db_session.refresh(rel)
        assert rel.relation_type == "war"

    def test_edit_invalid_type(self, client, db_session):
        _login(client)
        rel = _make_relation(db_session)
        resp = client.post(f"/diplomacy/{rel.id}/edit", data={
            "relation_type": "bad",
            "notes": "",
        }, follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert "Nieprawidłowy typ relacji" in html

    def test_edit_nonexistent(self, client, db_session):
        _login(client)
        resp = client.post("/diplomacy/9999/edit", data={
            "relation_type": "ally",
            "notes": "",
        }, follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert "nie została znaleziona" in html

    def test_edit_requires_login(self, client, db_session):
        rel = _make_relation(db_session)
        resp = client.post(f"/diplomacy/{rel.id}/edit", data={
            "relation_type": "ally",
            "notes": "x",
        })
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ── Delete (deactivate) relation route ───────────────────────────────────


class TestDeleteRelation:
    def test_delete_deactivates(self, client, db_session):
        _login(client)
        rel = _make_relation(db_session)
        resp = client.post(f"/diplomacy/{rel.id}/delete", follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert "Dezaktywowano relację" in html
        db_session.refresh(rel)
        assert rel.active is False

    def test_delete_nonexistent(self, client, db_session):
        _login(client)
        resp = client.post("/diplomacy/9999/delete", follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert "nie została znaleziona" in html

    def test_delete_requires_login(self, client, db_session):
        rel = _make_relation(db_session)
        resp = client.post(f"/diplomacy/{rel.id}/delete")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_deleted_not_shown(self, client, db_session):
        _login(client)
        rel = _make_relation(db_session, target_alliance_name="GoneAlliance")
        client.post(f"/diplomacy/{rel.id}/delete", follow_redirects=True)
        resp = client.get("/diplomacy")
        html = resp.data.decode("utf-8")
        assert "GoneAlliance" not in html


# ── Inline edit/delete buttons ───────────────────────────────────────────


class TestInlineButtons:
    def test_edit_delete_buttons_visible_when_logged_in(self, client, db_session):
        _login(client)
        _make_relation(db_session, target_alliance_name="VisibleRelation")
        resp = client.get("/diplomacy")
        html = resp.data.decode("utf-8")
        assert "toggleEdit" in html
        assert "/delete" in html

    def test_edit_delete_buttons_hidden_when_not_logged_in(self, client, db_session):
        _make_relation(db_session, target_alliance_name="NoButtons")
        resp = client.get("/diplomacy")
        html = resp.data.decode("utf-8")
        # No delete forms or edit form containers for specific relations
        assert 'action="/diplomacy/' not in html or '/delete' not in html
        assert "Dodaj relację" not in html
