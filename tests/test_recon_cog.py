"""Testy dla komend rozpoznania — /tnieaktywni."""

from datetime import datetime, timedelta, timezone

import pytest
from app import create_app
from app.database import db as _db
from app.models import Snapshot, Village

from bot.cogs.recon import _bbox_filter, _bbox_query, _find_inactive_players, _find_enemy_players
from bot.utils import torus_distance


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


def _make_village(map_id, snapshot_id, x, y, uid, player_name,
                  aid=0, alliance_name="", population=100,
                  tid=1, vid=None, name="Wioska"):
    return Village(
        map_id=map_id, snapshot_id=snapshot_id,
        x=x, y=y, tid=tid, vid=vid or map_id, name=name,
        uid=uid, player_name=player_name,
        aid=aid, alliance_name=alliance_name,
        population=population,
    )


# ------------------------------------------------------------------ #
# _bbox_filter
# ------------------------------------------------------------------ #


class TestBboxFilter:
    """Test bounding box filter for torus coordinates."""

    def test_normal_range(self, db_session):
        """Box fully within map boundaries should use BETWEEN."""
        s = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=3)
        db_session.add(s)
        db_session.commit()

        # Villages at x=0, x=5, x=50
        db_session.add_all([
            _make_village(1, s.id, 0, 0, 1, "P1"),
            _make_village(2, s.id, 5, 0, 2, "P2"),
            _make_village(3, s.id, 50, 0, 3, "P3"),
        ])
        db_session.commit()

        result = Village.query.filter(
            Village.snapshot_id == s.id,
            _bbox_filter(Village.x, 0, 10, 401),
        ).all()
        xs = {v.x for v in result}
        assert 0 in xs
        assert 5 in xs
        assert 50 not in xs

    def test_wrap_negative(self, db_session):
        """Box wrapping past negative boundary should include both sides."""
        s = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=3)
        db_session.add(s)
        db_session.commit()

        # half = 200. Center at -195, radius 10 → lo=-205 < -200 → wraps
        db_session.add_all([
            _make_village(1, s.id, -195, 0, 1, "P1"),  # within
            _make_village(2, s.id, 198, 0, 2, "P2"),    # wraps to ~-203 equivalent → within
            _make_village(3, s.id, 0, 0, 3, "P3"),      # outside
        ])
        db_session.commit()

        result = Village.query.filter(
            Village.snapshot_id == s.id,
            _bbox_filter(Village.x, -195, 10, 401),
        ).all()
        xs = {v.x for v in result}
        assert -195 in xs
        assert 198 in xs
        assert 0 not in xs

    def test_wrap_positive(self, db_session):
        """Box wrapping past positive boundary should include both sides."""
        s = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=2)
        db_session.add(s)
        db_session.commit()

        # half = 200. Center at 195, radius 10 → hi=205 > 200 → wraps
        db_session.add_all([
            _make_village(1, s.id, 195, 0, 1, "P1"),   # within
            _make_village(2, s.id, -198, 0, 2, "P2"),   # wraps → within
            _make_village(3, s.id, 0, 0, 3, "P3"),      # outside
        ])
        db_session.commit()

        result = Village.query.filter(
            Village.snapshot_id == s.id,
            _bbox_filter(Village.x, 195, 10, 401),
        ).all()
        xs = {v.x for v in result}
        assert 195 in xs
        assert -198 in xs
        assert 0 not in xs


# ------------------------------------------------------------------ #
# _bbox_query
# ------------------------------------------------------------------ #


class TestBboxQuery:
    """Test bounding box village query."""

    def test_returns_villages_in_box(self, db_session):
        """Should return only villages within bounding box."""
        s = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=3)
        db_session.add(s)
        db_session.commit()

        db_session.add_all([
            _make_village(1, s.id, 10, 10, 1, "P1"),
            _make_village(2, s.id, 15, 15, 2, "P2"),
            _make_village(3, s.id, 100, 100, 3, "P3"),
        ])
        db_session.commit()

        result = _bbox_query(s.id, 10, 10, 20, 401)
        uids = {v.uid for v in result}
        assert 1 in uids
        assert 2 in uids
        assert 3 not in uids

    def test_excludes_uid_zero(self, db_session):
        """Villages with uid=0 (Nature/empty) should be excluded."""
        s = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=2)
        db_session.add(s)
        db_session.commit()

        db_session.add_all([
            _make_village(1, s.id, 0, 0, 0, "Nature"),   # uid=0
            _make_village(2, s.id, 1, 1, 10, "Player"),  # uid>0
        ])
        db_session.commit()

        result = _bbox_query(s.id, 0, 0, 10, 401)
        uids = {v.uid for v in result}
        assert 0 not in uids
        assert 10 in uids

    def test_empty_result(self, db_session):
        """No villages in range should return empty list."""
        s = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=1)
        db_session.add(s)
        db_session.commit()

        db_session.add(_make_village(1, s.id, 100, 100, 1, "FarAway"))
        db_session.commit()

        result = _bbox_query(s.id, 0, 0, 5, 401)
        assert result == []


# ------------------------------------------------------------------ #
# _find_inactive_players
# ------------------------------------------------------------------ #


class TestFindInactivePlayers:
    """Test inactive player detection logic."""

    def _setup_snapshots(self, db_session, days_ago=2):
        """Create two snapshots: one old, one recent."""
        now = datetime.now(timezone.utc)
        s_old = Snapshot(fetched_at=now - timedelta(days=days_ago), village_count=10)
        s_new = Snapshot(fetched_at=now, village_count=10)
        db_session.add_all([s_old, s_new])
        db_session.commit()
        return s_old, s_new

    def test_returns_none_with_fewer_than_two_snapshots(self, db_session):
        """Need at least 2 snapshots, otherwise returns None."""
        s = Snapshot(fetched_at=datetime.now(timezone.utc), village_count=5)
        db_session.add(s)
        db_session.commit()

        result = _find_inactive_players(0, 0, 50, 50, 3, [1], "", 401)
        assert result is None

    def test_inactive_player_detected(self, db_session):
        """Player with same pop & village count in both snapshots → inactive."""
        s_old, s_new = self._setup_snapshots(db_session)

        # Same pop (200) in both snapshots
        db_session.add_all([
            _make_village(1, s_old.id, 5, 5, 10, "Lazy", population=200),
            _make_village(2, s_new.id, 5, 5, 10, "Lazy", population=200),
        ])
        db_session.commit()

        result = _find_inactive_players(0, 0, 50, 50, 3, [], "", 401)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "Lazy"
        assert result[0]["pop"] == 200

    def test_growing_player_not_inactive(self, db_session):
        """Player with increased pop should NOT be inactive."""
        s_old, s_new = self._setup_snapshots(db_session)

        db_session.add_all([
            _make_village(1, s_old.id, 5, 5, 10, "Active", population=200),
            _make_village(2, s_new.id, 5, 5, 10, "Active", population=300),
        ])
        db_session.commit()

        result = _find_inactive_players(0, 0, 50, 50, 3, [], "", 401)
        assert result == []

    def test_new_village_means_not_inactive(self, db_session):
        """Player who gained a village should NOT be inactive."""
        s_old, s_new = self._setup_snapshots(db_session)

        # One village in old snapshot, two in new (same total pop)
        db_session.add_all([
            _make_village(1, s_old.id, 5, 5, 10, "Expander", population=200),
            _make_village(2, s_new.id, 5, 5, 10, "Expander", population=100),
            _make_village(3, s_new.id, 6, 6, 10, "Expander", population=100),
        ])
        db_session.commit()

        result = _find_inactive_players(0, 0, 50, 50, 3, [], "", 401)
        assert result == []

    def test_our_alliance_excluded(self, db_session):
        """Players from our alliance should be excluded."""
        s_old, s_new = self._setup_snapshots(db_session)

        db_session.add_all([
            _make_village(1, s_old.id, 5, 5, 10, "AllyGuy", aid=1, population=200),
            _make_village(2, s_new.id, 5, 5, 10, "AllyGuy", aid=1, population=200),
        ])
        db_session.commit()

        result = _find_inactive_players(0, 0, 50, 50, 3, [1], "", 401)
        assert result == []

    def test_min_pop_filter(self, db_session):
        """Players below min_pop should be excluded."""
        s_old, s_new = self._setup_snapshots(db_session)

        db_session.add_all([
            _make_village(1, s_old.id, 5, 5, 10, "SmallFry", population=30),
            _make_village(2, s_new.id, 5, 5, 10, "SmallFry", population=30),
        ])
        db_session.commit()

        result = _find_inactive_players(0, 0, 50, 50, 3, [], "", 401)
        assert result == []  # min_pop=50 by default

    def test_out_of_radius_excluded(self, db_session):
        """Players outside search radius should be excluded."""
        s_old, s_new = self._setup_snapshots(db_session)

        # Village at (100, 100), searching from (0, 0) with radius=10
        db_session.add_all([
            _make_village(1, s_old.id, 100, 100, 10, "FarAway", population=200),
            _make_village(2, s_new.id, 100, 100, 10, "FarAway", population=200),
        ])
        db_session.commit()

        result = _find_inactive_players(0, 0, 10, 50, 3, [], "", 401)
        assert result == []

    def test_sorted_by_distance(self, db_session):
        """Results should be sorted by distance (closest first)."""
        s_old, s_new = self._setup_snapshots(db_session)

        db_session.add_all([
            _make_village(1, s_old.id, 20, 0, 10, "Far", population=200),
            _make_village(2, s_new.id, 20, 0, 10, "Far", population=200),
            _make_village(3, s_old.id, 5, 0, 20, "Close", population=200),
            _make_village(4, s_new.id, 5, 0, 20, "Close", population=200),
        ])
        db_session.commit()

        result = _find_inactive_players(0, 0, 50, 50, 3, [], "", 401)
        assert len(result) == 2
        assert result[0]["name"] == "Close"
        assert result[1]["name"] == "Far"

    def test_player_not_in_earliest_snapshot_excluded(self, db_session):
        """Player only appearing in latest snapshot (new player) should not be inactive."""
        s_old, s_new = self._setup_snapshots(db_session)

        # Only in new snapshot
        db_session.add(_make_village(1, s_new.id, 5, 5, 10, "NewGuy", population=200))
        db_session.commit()

        result = _find_inactive_players(0, 0, 50, 50, 3, [], "", 401)
        assert result == []

    def test_empty_area_returns_empty_list(self, db_session):
        """No villages in area should return empty list (not None)."""
        s_old, s_new = self._setup_snapshots(db_session)
        # No villages added

        result = _find_inactive_players(0, 0, 50, 50, 3, [], "", 401)
        assert result == []

    def test_multiple_villages_per_player(self, db_session):
        """Player's total pop should be sum of all villages."""
        s_old, s_new = self._setup_snapshots(db_session)

        # Two villages, same pop in both snapshots → total 300
        db_session.add_all([
            _make_village(1, s_old.id, 3, 3, 10, "MultiVillage", population=200),
            _make_village(2, s_old.id, 4, 4, 10, "MultiVillage", population=100),
            _make_village(3, s_new.id, 3, 3, 10, "MultiVillage", population=200),
            _make_village(4, s_new.id, 4, 4, 10, "MultiVillage", population=100),
        ])
        db_session.commit()

        result = _find_inactive_players(0, 0, 50, 50, 3, [], "", 401)
        assert len(result) == 1
        assert result[0]["pop"] == 300
        assert result[0]["village_count"] == 2


# ------------------------------------------------------------------ #
# _find_enemy_players
# ------------------------------------------------------------------ #


class TestFindEnemyPlayers:
    """Test enemy player search logic."""

    def _setup_snapshot(self, db_session):
        """Create a single snapshot."""
        now = datetime.now(timezone.utc)
        s = Snapshot(fetched_at=now, village_count=10)
        db_session.add(s)
        db_session.commit()
        return s

    def test_returns_none_without_snapshot(self, db_session):
        """No snapshots at all should return None."""
        result = _find_enemy_players(0, 0, 50, 100, [], "", 401)
        assert result is None

    def test_our_alliance_excluded(self, db_session):
        """Villages from our alliances should be excluded."""
        s = self._setup_snapshot(db_session)
        db_session.add_all([
            _make_village(1, s.id, 5, 5, 10, "AllyGuy", aid=1,
                          alliance_name="UFKI", population=500),
            _make_village(2, s.id, 6, 6, 20, "Enemy", aid=99,
                          alliance_name="BAD", population=500),
        ])
        db_session.commit()

        result = _find_enemy_players(0, 0, 50, 100, [1], "", 401)
        names = {p["name"] for p in result}
        assert "AllyGuy" not in names
        assert "Enemy" in names

    def test_non_allied_included(self, db_session):
        """Non-allied players should appear in results."""
        s = self._setup_snapshot(db_session)
        db_session.add(_make_village(
            1, s.id, 5, 5, 10, "Neutral", aid=50,
            alliance_name="OTHER", population=200,
        ))
        db_session.commit()

        result = _find_enemy_players(0, 0, 50, 100, [1, 2], "", 401)
        assert len(result) == 1
        assert result[0]["name"] == "Neutral"

    def test_min_pop_filter(self, db_session):
        """Players below min_pop should be excluded."""
        s = self._setup_snapshot(db_session)
        db_session.add_all([
            _make_village(1, s.id, 5, 5, 10, "Tiny", aid=99,
                          alliance_name="X", population=50),
            _make_village(2, s.id, 6, 6, 20, "Big", aid=99,
                          alliance_name="X", population=500),
        ])
        db_session.commit()

        result = _find_enemy_players(0, 0, 50, 100, [], "", 401)
        names = {p["name"] for p in result}
        assert "Tiny" not in names
        assert "Big" in names

    def test_grouping_by_player(self, db_session):
        """Multiple villages of same player should aggregate pop and count."""
        s = self._setup_snapshot(db_session)
        db_session.add_all([
            _make_village(1, s.id, 3, 3, 10, "Multi", aid=99,
                          alliance_name="X", population=200),
            _make_village(2, s.id, 4, 4, 10, "Multi", aid=99,
                          alliance_name="X", population=150),
        ])
        db_session.commit()

        result = _find_enemy_players(0, 0, 50, 100, [], "", 401)
        assert len(result) == 1
        assert result[0]["pop"] == 350
        assert result[0]["village_count"] == 2

    def test_sorted_by_pop_descending(self, db_session):
        """Results should be sorted by total population, highest first."""
        s = self._setup_snapshot(db_session)
        db_session.add_all([
            _make_village(1, s.id, 5, 5, 10, "Small", aid=99,
                          alliance_name="X", population=200),
            _make_village(2, s.id, 6, 6, 20, "Big", aid=99,
                          alliance_name="X", population=800),
        ])
        db_session.commit()

        result = _find_enemy_players(0, 0, 50, 100, [], "", 401)
        assert len(result) == 2
        assert result[0]["name"] == "Big"
        assert result[1]["name"] == "Small"

    def test_closest_village_tracked(self, db_session):
        """Player's closest village coords should be recorded."""
        s = self._setup_snapshot(db_session)
        db_session.add_all([
            _make_village(1, s.id, 10, 10, 10, "Player", aid=99,
                          alliance_name="X", population=200),
            _make_village(2, s.id, 3, 3, 10, "Player", aid=99,
                          alliance_name="X", population=100),
        ])
        db_session.commit()

        result = _find_enemy_players(0, 0, 50, 100, [], "", 401)
        assert result[0]["closest_x"] == 3
        assert result[0]["closest_y"] == 3

    def test_out_of_radius_excluded(self, db_session):
        """Players outside search radius should be excluded."""
        s = self._setup_snapshot(db_session)
        db_session.add(_make_village(
            1, s.id, 100, 100, 10, "FarAway", aid=99,
            alliance_name="X", population=500,
        ))
        db_session.commit()

        result = _find_enemy_players(0, 0, 10, 100, [], "", 401)
        assert result == []

    def test_empty_area(self, db_session):
        """No villages in area should return empty list."""
        s = self._setup_snapshot(db_session)
        result = _find_enemy_players(0, 0, 50, 100, [], "", 401)
        assert result == []
