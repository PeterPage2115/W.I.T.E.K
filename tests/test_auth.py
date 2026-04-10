"""Tests for Discord OAuth2 authentication and RBAC (S5.1 + S5.2)."""

import pytest
from unittest.mock import patch, MagicMock
from app import create_app
from app.database import db as _db
from app.models import User
from app.auth_utils import login_required, role_required, get_current_user
from flask import Flask


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "test-secret"
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
    DISCORD_CLIENT_ID = "test-client-id"
    DISCORD_CLIENT_SECRET = "test-client-secret"
    DISCORD_REDIRECT_URI = "http://localhost:5000/auth/callback"


class TestConfigNoOAuth(TestConfig):
    DISCORD_CLIENT_ID = ""


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def app_no_oauth():
    app = create_app(TestConfigNoOAuth)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def client_no_oauth(app_no_oauth):
    return app_no_oauth.test_client()


# --- /auth/login ---

class TestLogin:
    def test_login_redirects_to_discord(self, client):
        resp = client.get("/auth/login")
        assert resp.status_code == 302
        assert "discord.com" in resp.headers["Location"]
        assert "test-client-id" in resp.headers["Location"]

    def test_login_no_oauth_flashes_error(self, client_no_oauth):
        resp = client_no_oauth.get("/auth/login", follow_redirects=True)
        assert resp.status_code == 200
        assert "OAuth nie skonfigurowany" in resp.data.decode()


# --- /auth/callback ---

class TestCallback:
    def test_callback_no_code_redirects(self, client):
        resp = client.get("/auth/callback")
        assert resp.status_code == 302

    def test_callback_invalid_state_rejected(self, client):
        """CSRF protection: mismatched state is rejected."""
        with client.session_transaction() as sess:
            sess["oauth_state"] = "expected-state"
        resp = client.get("/auth/callback?code=test-code&state=wrong-state",
                          follow_redirects=True)
        assert resp.status_code == 200
        assert "token bezpieczeństwa" in resp.data.decode()

    @patch("app.routes.auth.requests.get")
    @patch("app.routes.auth.requests.post")
    def test_callback_creates_user(self, mock_post, mock_get, client, app):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"access_token": "fake-token"}),
        )
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "123456789", "username": "testuser"}),
        )

        with client.session_transaction() as sess:
            sess["oauth_state"] = "test-state"

        resp = client.get("/auth/callback?code=test-code&state=test-state")
        assert resp.status_code == 302

        with app.app_context():
            user = User.query.filter_by(discord_id=123456789).first()
            assert user is not None
            assert user.discord_name == "testuser"
            assert user.role == "member"

    @patch("app.routes.auth.requests.get")
    @patch("app.routes.auth.requests.post")
    def test_callback_sets_session(self, mock_post, mock_get, client):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"access_token": "fake-token"}),
        )
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "123456789", "username": "testuser"}),
        )

        with client.session_transaction() as sess:
            assert "user_id" not in sess
            sess["oauth_state"] = "test-state"

        client.get("/auth/callback?code=test-code&state=test-state")

        with client.session_transaction() as sess:
            assert sess["discord_id"] == 123456789
            assert sess["discord_name"] == "testuser"
            assert sess["role"] == "member"

    @patch("app.routes.auth.requests.get")
    @patch("app.routes.auth.requests.post")
    def test_callback_updates_existing_user(self, mock_post, mock_get, client, app):
        with app.app_context():
            user = User(discord_id=123456789, discord_name="oldname", role="officer")
            _db.session.add(user)
            _db.session.commit()

        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"access_token": "fake-token"}),
        )
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "123456789", "username": "newname"}),
        )

        with client.session_transaction() as sess:
            sess["oauth_state"] = "test-state"

        client.get("/auth/callback?code=test-code&state=test-state")

        with app.app_context():
            user = User.query.filter_by(discord_id=123456789).first()
            assert user.discord_name == "newname"
            assert user.role == "officer"

    @patch("app.routes.auth.requests.post")
    def test_callback_token_exchange_failure(self, mock_post, client):
        mock_post.return_value = MagicMock(status_code=400, text="Bad Request")

        with client.session_transaction() as sess:
            sess["oauth_state"] = "test-state"

        resp = client.get("/auth/callback?code=bad-code&state=test-state",
                          follow_redirects=True)
        assert resp.status_code == 200
        assert "autoryzacji Discord" in resp.data.decode()

    @patch("app.routes.auth.requests.get")
    @patch("app.routes.auth.requests.post")
    def test_callback_user_info_failure(self, mock_post, mock_get, client):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"access_token": "fake-token"}),
        )
        mock_get.return_value = MagicMock(status_code=401)

        with client.session_transaction() as sess:
            sess["oauth_state"] = "test-state"

        resp = client.get("/auth/callback?code=test-code&state=test-state",
                          follow_redirects=True)
        assert resp.status_code == 200
        assert "pobrać danych" in resp.data.decode()

    def test_callback_discord_error_handled(self, client):
        """Discord returns error parameter (e.g. access_denied)."""
        resp = client.get(
            "/auth/callback?error=access_denied&error_description=User+denied+access",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "User denied access" in resp.data.decode()


# --- /auth/logout ---

class TestLogout:
    def test_logout_clears_session(self, client):
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["discord_id"] = 123
            sess["discord_name"] = "test"
            sess["role"] = "member"

        resp = client.get("/auth/logout")
        assert resp.status_code == 302

        with client.session_transaction() as sess:
            assert "user_id" not in sess


# --- login_required decorator ---

class TestLoginRequired:
    def test_blocks_unauthenticated(self, app):
        @app.route("/protected-test")
        @login_required
        def protected():
            return "ok"

        with app.test_client() as c:
            resp = c.get("/protected-test")
            assert resp.status_code == 302
            assert "/auth/login" in resp.headers["Location"]

    def test_allows_authenticated(self, app):
        @app.route("/protected-test2")
        @login_required
        def protected():
            return "ok"

        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = 1
            resp = c.get("/protected-test2")
            assert resp.status_code == 200
            assert resp.data == b"ok"


# --- role_required decorator ---

class TestRoleRequired:
    def test_blocks_unauthenticated(self, app):
        @app.route("/admin-test")
        @role_required("leader")
        def admin():
            return "admin"

        with app.test_client() as c:
            resp = c.get("/admin-test")
            assert resp.status_code == 302
            assert "/auth/login" in resp.headers["Location"]

    def test_blocks_wrong_role(self, app):
        @app.route("/admin-test2")
        @role_required("leader")
        def admin():
            return "admin"

        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = 1
                sess["role"] = "member"
            resp = c.get("/admin-test2")
            assert resp.status_code == 403

    def test_allows_correct_role(self, app):
        @app.route("/admin-test3")
        @role_required("leader", "officer")
        def admin():
            return "admin"

        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = 1
                sess["role"] = "officer"
            resp = c.get("/admin-test3")
            assert resp.status_code == 200
            assert resp.data == b"admin"


# --- get_current_user ---

class TestGetCurrentUser:
    def test_returns_none_when_not_logged_in(self, app):
        with app.test_request_context():
            assert get_current_user() is None

    def test_returns_user_dict_when_logged_in(self, app):
        with app.test_request_context():
            from flask import session
            session["user_id"] = 1
            session["discord_id"] = 123
            session["discord_name"] = "testuser"
            session["role"] = "leader"

            user = get_current_user()
            assert user is not None
            assert user["id"] == 1
            assert user["discord_id"] == 123
            assert user["discord_name"] == "testuser"
            assert user["role"] == "leader"


# --- Context processor ---

class TestContextProcessor:
    def test_injects_current_user_none(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Zaloguj" in resp.data.decode()

    def test_injects_current_user_logged_in(self, client):
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["discord_id"] = 123
            sess["discord_name"] = "witek_user"
            sess["role"] = "member"

        resp = client.get("/")
        assert resp.status_code == 200
        assert "witek_user" in resp.data.decode()
        assert "Wyloguj" in resp.data.decode()
