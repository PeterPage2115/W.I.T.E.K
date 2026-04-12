"""Tests for quick-search API endpoint."""

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
    application = create_app(TestConfig)
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seed_data(app):
    """Seed players and alliances for search tests."""
    alliances = [
        Alliance(aid=1, name="UFOLODZY", member_count=20, total_pop=50000),
        Alliance(aid=2, name="UFO-Wing", member_count=10, total_pop=25000),
        Alliance(aid=3, name="Raiders", member_count=15, total_pop=30000),
    ]
    for a in alliances:
        _db.session.add(a)

    players = [
        Player(uid=1, name="Asterix", tid=3, aid=1, alliance_name="UFOLODZY", total_pop=1000, village_count=3),
        Player(uid=2, name="Obelix", tid=3, aid=1, alliance_name="UFOLODZY", total_pop=2000, village_count=5),
        Player(uid=3, name="Asterion", tid=1, aid=2, alliance_name="UFO-Wing", total_pop=500, village_count=1),
        Player(uid=4, name="Caesar", tid=1, aid=3, alliance_name="Raiders", total_pop=3000, village_count=7),
        Player(uid=5, name="Brutus", tid=1, aid=3, alliance_name="Raiders", total_pop=1500, village_count=4),
        Player(uid=6, name="Asteroth", tid=2, aid=3, alliance_name="Raiders", total_pop=800, village_count=2),
        Player(uid=7, name="AsterMax", tid=2, aid=2, alliance_name="UFO-Wing", total_pop=600, village_count=2),
        Player(uid=8, name="AsterPro", tid=1, aid=1, alliance_name="UFOLODZY", total_pop=400, village_count=1),
        Player(uid=9, name="AsterGod", tid=3, aid=1, alliance_name="UFOLODZY", total_pop=300, village_count=1),
    ]
    for p in players:
        _db.session.add(p)

    _db.session.commit()


def test_search_finds_player_by_partial_name(client, seed_data):
    resp = client.get("/api/search?q=Aste")
    assert resp.status_code == 200
    data = resp.get_json()
    names = [p["name"] for p in data["players"]]
    assert "Asterix" in names
    assert "Asterion" in names


def test_search_empty_for_short_query(client, seed_data):
    resp = client.get("/api/search?q=A")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["players"] == []
    assert data["alliances"] == []


def test_search_empty_for_missing_query(client, seed_data):
    resp = client.get("/api/search")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["players"] == []
    assert data["alliances"] == []


def test_search_finds_alliance_by_partial_name(client, seed_data):
    resp = client.get("/api/search?q=UFO")
    assert resp.status_code == 200
    data = resp.get_json()
    alliance_names = [a["name"] for a in data["alliances"]]
    assert "UFOLODZY" in alliance_names
    assert "UFO-Wing" in alliance_names


def test_search_returns_both_players_and_alliances(client, seed_data):
    resp = client.get("/api/search?q=UFO")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["alliances"]) >= 1
    # "UFO" doesn't match player names, so players may be empty — that's fine
    # Test with a broader term
    resp2 = client.get("/api/search?q=Aster")
    data2 = resp2.get_json()
    assert len(data2["players"]) >= 1


def test_search_is_case_insensitive(client, seed_data):
    resp_lower = client.get("/api/search?q=aste")
    resp_upper = client.get("/api/search?q=ASTE")
    data_lower = resp_lower.get_json()
    data_upper = resp_upper.get_json()
    assert len(data_lower["players"]) == len(data_upper["players"])
    lower_names = {p["name"] for p in data_lower["players"]}
    upper_names = {p["name"] for p in data_upper["players"]}
    assert lower_names == upper_names


def test_search_limits_results_to_5(client, seed_data):
    # We have 7 players matching "Aster*" — should return max 5
    resp = client.get("/api/search?q=Aster")
    data = resp.get_json()
    assert len(data["players"]) <= 5


def test_search_players_ordered_by_pop_desc(client, seed_data):
    resp = client.get("/api/search?q=Aster")
    data = resp.get_json()
    pops = [p["pop"] for p in data["players"]]
    assert pops == sorted(pops, reverse=True)


def test_search_player_has_expected_fields(client, seed_data):
    resp = client.get("/api/search?q=Caesar")
    data = resp.get_json()
    assert len(data["players"]) == 1
    player = data["players"][0]
    assert player["uid"] == 4
    assert player["name"] == "Caesar"
    assert player["alliance"] == "Raiders"
    assert player["pop"] == 3000


def test_search_percent_does_not_match_all(client, seed_data):
    """Percent sign should be treated literally, not as SQL wildcard."""
    resp = client.get("/api/search?q=%25")  # URL-encoded %
    data = resp.get_json()
    assert len(data["players"]) == 0
    assert len(data["alliances"]) == 0


def test_search_underscore_literal(client, seed_data):
    """Underscore should be treated literally, not as single-char wildcard."""
    resp = client.get("/api/search?q=__")
    data = resp.get_json()
    assert len(data["players"]) == 0


def test_search_alliance_has_expected_fields(client, seed_data):
    resp = client.get("/api/search?q=Raiders")
    data = resp.get_json()
    assert len(data["alliances"]) == 1
    alliance = data["alliances"][0]
    assert alliance["aid"] == 3
    assert alliance["name"] == "Raiders"
    assert alliance["members"] == 15
    assert alliance["pop"] == 30000
