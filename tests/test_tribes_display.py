"""Testy dla wyświetlania ikon plemion w szablonach."""

import pytest
from app import create_app
from app.database import db as _db
from app.models import Snapshot, Alliance, Player, Village, TRIBE_NAMES
from bot.tribes import TRIBES


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


TRIBE_ICONS = {
    tid: {"css": f"trav-tribe-{t.icon_slug}" if t.icon_slug else "", "emoji": t.emoji}
    for tid, t in TRIBES.items()
}


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
def seed_data(app):
    """Seed snapshot with players of various tribes."""
    from datetime import datetime, timezone

    snap = Snapshot(fetched_at=datetime(2025, 1, 1, tzinfo=timezone.utc), village_count=9)
    _db.session.add(snap)
    _db.session.flush()

    alliance = Alliance(aid=1, name="TEST", member_count=9, total_pop=900)
    _db.session.add(alliance)

    tribe_ids = [1, 2, 3, 6, 7, 8, 9]
    for tid in tribe_ids:
        player = Player(
            uid=tid * 100,
            name=f"Player_T{tid}",
            tid=tid,
            aid=1,
            alliance_name="TEST",
            village_count=1,
            total_pop=100,
        )
        _db.session.add(player)
        village = Village(
            snapshot_id=snap.id,
            map_id=tid * 1000,
            vid=tid * 1000,
            name=f"Village_T{tid}",
            x=tid,
            y=tid,
            uid=tid * 100,
            player_name=f"Player_T{tid}",
            tid=tid,
            aid=1,
            alliance_name="TEST",
            population=100,
        )
        _db.session.add(village)

    _db.session.commit()


# --- Context processors ---

class TestContextProcessors:
    def test_tribe_names_available_in_context(self, app):
        """TRIBE_NAMES should be injected into all templates."""
        with app.test_request_context():
            processors = app.template_context_processors[None]
            context = {}
            for proc in processors:
                context.update(proc())
            assert "TRIBE_NAMES" in context
            assert context["TRIBE_NAMES"][1] == "Rzymianie"
            assert context["TRIBE_NAMES"][6] == "Egipcjanie"

    def test_tribe_names_has_all_playable_tribes(self, app):
        """TRIBE_NAMES should include tribes 1-3 and 6-9."""
        with app.test_request_context():
            processors = app.template_context_processors[None]
            context = {}
            for proc in processors:
                context.update(proc())
            names = context["TRIBE_NAMES"]
            for tid in [1, 2, 3, 6, 7, 8, 9]:
                assert tid in names, f"Tribe {tid} missing from TRIBE_NAMES"

    def test_tribe_icons_available_in_context(self, app):
        """TRIBE_ICONS should be injected with css/emoji for each tribe."""
        with app.test_request_context():
            processors = app.template_context_processors[None]
            context = {}
            for proc in processors:
                context.update(proc())
            assert "TRIBE_ICONS" in context
            icons = context["TRIBE_ICONS"]
            assert icons[1]["css"] == "trav-tribe-roman"
            assert icons[6]["css"] == "trav-tribe-egyptian"
            assert icons[9]["css"] == "trav-tribe-viking"

    def test_tribe_icons_derived_from_tribes_py(self, app):
        """TRIBE_ICONS should match bot/tribes.py data."""
        with app.test_request_context():
            processors = app.template_context_processors[None]
            context = {}
            for proc in processors:
                context.update(proc())
            icons = context["TRIBE_ICONS"]
            for tid, t in TRIBES.items():
                assert icons[tid]["css"] == f"trav-tribe-{t.icon_slug}"
                assert icons[tid]["emoji"] == t.emoji


# --- Macro rendering ---

class TestTribeIconMacro:
    def test_roman_uses_css_class(self, app):
        with app.test_request_context():
            rendered = _render_macro(app, 1)
            assert "trav-tribe-roman" in rendered
            assert "Rzymianie" in rendered

    def test_teuton_uses_css_class(self, app):
        with app.test_request_context():
            rendered = _render_macro(app, 2)
            assert "trav-tribe-teuton" in rendered

    def test_gaul_uses_css_class(self, app):
        with app.test_request_context():
            rendered = _render_macro(app, 3)
            assert "trav-tribe-gaul" in rendered

    def test_egyptian_uses_css_class(self, app):
        with app.test_request_context():
            rendered = _render_macro(app, 6)
            assert "trav-tribe-egyptian" in rendered
            assert "Egipcjanie" in rendered

    def test_hun_uses_css_class(self, app):
        with app.test_request_context():
            rendered = _render_macro(app, 7)
            assert "trav-tribe-hun" in rendered
            assert "Hunowie" in rendered

    def test_spartan_uses_css_class(self, app):
        with app.test_request_context():
            rendered = _render_macro(app, 8)
            assert "trav-tribe-spartan" in rendered
            assert "Spartanie" in rendered

    def test_viking_uses_css_class(self, app):
        with app.test_request_context():
            rendered = _render_macro(app, 9)
            assert "trav-tribe-viking" in rendered
            assert "Wikingowie" in rendered

    def test_unknown_tribe_uses_fallback(self, app):
        with app.test_request_context():
            rendered = _render_macro(app, 99)
            assert "👤" in rendered

    def test_custom_size(self, app):
        with app.test_request_context():
            rendered = _render_macro(app, 1, size="48px")
            assert "48px" in rendered

    def test_nature_uses_emoji_fallback(self, app):
        """Nature (tid=4) has no icon_slug, should use emoji from tribes.py."""
        with app.test_request_context():
            rendered = _render_macro(app, 4)
            # Nature is not in TRIBES, so falls back to 👤
            assert "👤" in rendered

    def test_no_hardcoded_dicts_in_macro(self):
        """_macros.html should not contain hardcoded tribe dicts."""
        import pathlib
        macro_path = pathlib.Path("app/templates/_macros.html")
        content = macro_path.read_text(encoding="utf-8")
        assert "tribe_emojis" not in content
        assert "tribe_css" not in content


def _render_macro(app, tid, size="24px"):
    """Helper: render the tribe_icon macro for a given tid."""
    env = app.jinja_env
    template_str = (
        '{%- from "_macros.html" import tribe_icon -%}'
        "{{ tribe_icon(tid, size=size, tribe_names=TRIBE_NAMES, tribe_icons=TRIBE_ICONS) }}"
    )
    template = env.from_string(template_str)
    return template.render(tid=tid, size=size, TRIBE_NAMES=TRIBE_NAMES, TRIBE_ICONS=TRIBE_ICONS)


# --- Template integration ---

class TestDashboardTribes:
    def test_dashboard_renders_all_tribes(self, client, seed_data):
        resp = client.get("/")
        html = resp.data.decode()
        assert "trav-tribe-roman" in html
        assert "trav-tribe-egyptian" in html


class TestPlayerTribes:
    def test_player_page_roman(self, client, seed_data):
        resp = client.get("/player/100")
        html = resp.data.decode()
        assert "trav-tribe-roman" in html
        assert resp.status_code == 200

    def test_player_page_egyptian(self, client, seed_data):
        resp = client.get("/player/600")
        html = resp.data.decode()
        assert "trav-tribe-egyptian" in html
        assert resp.status_code == 200

    def test_player_page_viking(self, client, seed_data):
        resp = client.get("/player/900")
        html = resp.data.decode()
        assert "trav-tribe-viking" in html
        assert resp.status_code == 200


class TestAllianceTribes:
    def test_alliance_page_shows_all_tribes(self, client, seed_data):
        resp = client.get("/alliance/1")
        html = resp.data.decode()
        assert "trav-tribe-roman" in html
        assert "trav-tribe-egyptian" in html
        assert resp.status_code == 200


class TestMapTribes:
    def test_map_has_full_tribe_names_json(self, client, seed_data):
        resp = client.get("/map")
        html = resp.data.decode()
        assert "Egipcjanie" in html
        assert "Hunowie" in html
        assert "Wikingowie" in html
        assert resp.status_code == 200
