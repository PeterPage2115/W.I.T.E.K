"""Testy dla komend tożsamości — /tlink, /tunlink, /twhoami."""

import pytest
from app import create_app
from app.database import db as _db
from app.models import Player, User


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


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield _db.session


def _make_player(uid, name, tid=1, aid=0, alliance_name="", total_pop=500, village_count=2):
    return Player(
        uid=uid, name=name, tid=tid, aid=aid,
        alliance_name=alliance_name,
        total_pop=total_pop, village_count=village_count,
    )


# ------------------------------------------------------------------ #
# _do_link logic — exact match, fuzzy, multiple, not_found, taken
# ------------------------------------------------------------------ #


class TestLinkExactMatch:
    """Test exact player match linking."""

    def test_link_exact_match_creates_user(self, db_session):
        """Exact match should create a User record linking discord_id → player uid."""
        db_session.add(_make_player(100, "TestPlayer", aid=1, alliance_name="ALLY"))
        db_session.commit()

        # Simulate _do_link exact match
        exact = Player.query.filter(Player.name == "TestPlayer").all()
        assert len(exact) == 1
        player = exact[0]

        discord_id = 999888777
        user = User(
            discord_id=discord_id,
            discord_name="testuser#1234",
            travian_uid=player.uid,
            travian_name=player.name,
        )
        db_session.add(user)
        db_session.commit()

        linked = User.query.filter_by(discord_id=discord_id).first()
        assert linked is not None
        assert linked.travian_uid == 100
        assert linked.travian_name == "TestPlayer"

    def test_link_updates_existing_user(self, db_session):
        """If user already linked, should update to new player."""
        db_session.add(_make_player(100, "OldPlayer"))
        db_session.add(_make_player(200, "NewPlayer"))
        db_session.add(User(
            discord_id=111, discord_name="user",
            travian_uid=100, travian_name="OldPlayer",
        ))
        db_session.commit()

        existing = User.query.filter_by(discord_id=111).first()
        new_player = Player.query.filter(Player.name == "NewPlayer").first()
        existing.travian_uid = new_player.uid
        existing.travian_name = new_player.name
        db_session.commit()

        refreshed = User.query.filter_by(discord_id=111).first()
        assert refreshed.travian_uid == 200
        assert refreshed.travian_name == "NewPlayer"

    def test_link_taken_by_another_discord(self, db_session):
        """If player already linked to another Discord user, should detect 'taken'."""
        db_session.add(_make_player(100, "ClaimedPlayer"))
        db_session.add(User(
            discord_id=111, discord_name="original",
            travian_uid=100, travian_name="ClaimedPlayer",
        ))
        db_session.commit()

        player = Player.query.filter(Player.name == "ClaimedPlayer").first()
        other = User.query.filter_by(travian_uid=player.uid).first()
        assert other is not None
        assert other.discord_id != 222  # different discord user


class TestLinkFuzzyMatch:
    """Test fuzzy/partial player name search."""

    def test_fuzzy_search_finds_partial(self, db_session):
        """LIKE search should find players with partial name match."""
        db_session.add_all([
            _make_player(1, "Gandalf"),
            _make_player(2, "Gandolf_II"),
            _make_player(3, "Legolas"),
        ])
        db_session.commit()

        search = "Gand"
        like = Player.query.filter(Player.name.ilike(f"%{search}%")).limit(5).all()
        assert len(like) == 2
        names = {p.name for p in like}
        assert "Gandalf" in names
        assert "Gandolf_II" in names

    def test_fuzzy_search_case_insensitive(self, db_session):
        """ILIKE search should be case-insensitive."""
        db_session.add(_make_player(1, "TestPlayer"))
        db_session.commit()

        like = Player.query.filter(Player.name.ilike("%testplayer%")).limit(5).all()
        assert len(like) == 1
        assert like[0].name == "TestPlayer"

    def test_fuzzy_no_match(self, db_session):
        """No match should return empty list."""
        db_session.add(_make_player(1, "Alice"))
        db_session.commit()

        like = Player.query.filter(Player.name.ilike("%zzzzz%")).limit(5).all()
        assert len(like) == 0


class TestLinkNotFound:
    """Test player not found scenario."""

    def test_no_exact_no_fuzzy(self, db_session):
        """When no player exists at all, should get not_found."""
        exact = Player.query.filter(Player.name == "Nobody").all()
        like = Player.query.filter(Player.name.ilike("%Nobody%")).limit(5).all()
        assert len(exact) == 0
        assert len(like) == 0

    def test_empty_player_table(self, app):
        """Empty players table returns not_found."""
        with app.app_context():
            assert Player.query.count() == 0
            exact = Player.query.filter(Player.name == "Anyone").all()
            assert len(exact) == 0


class TestLinkMultipleExact:
    """Test multiple exact name matches."""

    def test_multiple_exact_matches(self, db_session):
        """Multiple players with same name should return 'multiple' status."""
        db_session.add_all([
            _make_player(1, "SameName", aid=1, alliance_name="A1"),
            _make_player(2, "SameName", aid=2, alliance_name="A2"),
        ])
        db_session.commit()

        exact = Player.query.filter(Player.name == "SameName").all()
        assert len(exact) > 1
        suggestions = [(p.uid, p.name, p.alliance_name) for p in exact[:5]]
        assert len(suggestions) == 2


# ------------------------------------------------------------------ #
# _do_unlink logic
# ------------------------------------------------------------------ #


class TestUnlink:
    """Test unlinking Discord ↔ Travian."""

    def test_unlink_removes_user(self, db_session):
        """Unlinking should delete the User record."""
        db_session.add(User(
            discord_id=111, discord_name="user",
            travian_uid=100, travian_name="Player",
        ))
        db_session.commit()

        user = User.query.filter_by(discord_id=111).first()
        assert user is not None
        db_session.delete(user)
        db_session.commit()

        assert User.query.filter_by(discord_id=111).first() is None

    def test_unlink_when_not_linked(self, app):
        """Unlinking when not linked should return False."""
        with app.app_context():
            user = User.query.filter_by(discord_id=999).first()
            assert user is None  # no user → would return False


# ------------------------------------------------------------------ #
# _get_profile logic (from /twhoami)
# ------------------------------------------------------------------ #


class TestWhoami:
    """Test profile lookup for /twhoami."""

    def test_whoami_linked_returns_profile(self, db_session):
        """Linked user with existing player should return profile dict."""
        db_session.add(_make_player(100, "MyPlayer", tid=3, aid=5,
                                     alliance_name="COOL", total_pop=1500,
                                     village_count=4))
        db_session.add(User(
            discord_id=111, discord_name="user",
            travian_uid=100, travian_name="MyPlayer",
        ))
        db_session.commit()

        user = User.query.filter_by(discord_id=111).first()
        assert user is not None
        player = Player.query.get(user.travian_uid)
        assert player is not None

        profile = {
            "name": player.name,
            "tid": player.tid,
            "alliance": player.alliance_name,
            "pop": player.total_pop,
            "villages": player.village_count,
        }
        assert profile["name"] == "MyPlayer"
        assert profile["tid"] == 3
        assert profile["alliance"] == "COOL"
        assert profile["pop"] == 1500
        assert profile["villages"] == 4

    def test_whoami_not_linked(self, app):
        """Unlinked user should return None."""
        with app.app_context():
            user = User.query.filter_by(discord_id=999).first()
            assert user is None

    def test_whoami_linked_but_player_deleted(self, db_session):
        """User linked to deleted player should return None."""
        db_session.add(User(
            discord_id=111, discord_name="user",
            travian_uid=999, travian_name="GhostPlayer",
        ))
        db_session.commit()

        user = User.query.filter_by(discord_id=111).first()
        assert user is not None
        player = Player.query.get(user.travian_uid)
        assert player is None  # player no longer exists

    def test_whoami_user_without_travian_uid(self, db_session):
        """User with no travian_uid should return None (pre-link state)."""
        db_session.add(User(
            discord_id=111, discord_name="user",
            travian_uid=None, travian_name=None,
        ))
        db_session.commit()

        user = User.query.filter_by(discord_id=111).first()
        assert user is not None
        assert user.travian_uid is None


# ------------------------------------------------------------------ #
# _player_info helper
# ------------------------------------------------------------------ #


class TestPlayerInfo:
    """Test the _player_info dict conversion pattern."""

    def test_player_info_conversion(self, db_session):
        """Player model should convert to plain dict correctly."""
        db_session.add(_make_player(
            42, "Warrior", tid=2, aid=10, alliance_name="HORDE",
            total_pop=2500, village_count=7,
        ))
        db_session.commit()

        p = Player.query.get(42)
        info = {
            "name": p.name, "uid": p.uid, "tid": p.tid,
            "alliance": p.alliance_name or "—",
            "pop": p.total_pop or 0, "villages": p.village_count or 0,
        }
        assert info == {
            "name": "Warrior", "uid": 42, "tid": 2,
            "alliance": "HORDE", "pop": 2500, "villages": 7,
        }

    def test_player_info_null_alliance(self, db_session):
        """Player with no alliance should show '—'."""
        db_session.add(_make_player(1, "Loner", alliance_name=None, total_pop=100))
        db_session.commit()

        p = Player.query.get(1)
        alliance = p.alliance_name or "—"
        assert alliance == "—"
