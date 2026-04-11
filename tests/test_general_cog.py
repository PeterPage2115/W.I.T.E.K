"""Testy dla komend ogólnych — /thelp, /tinfo, /tstats."""

from datetime import datetime, timezone

import pytest
from app import create_app
from app.database import db as _db
from app.models import Alliance, Player, Snapshot


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


# ------------------------------------------------------------------ #
# _get_last_sync logic (from /tinfo)
# ------------------------------------------------------------------ #


class TestGetLastSync:
    """Test the _get_last_sync logic from /tinfo."""

    def test_no_snapshot_returns_brak_danych(self, app):
        """When no snapshots exist, should return 'brak danych'."""
        with app.app_context():
            snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
            result = snap.fetched_at.strftime("%Y-%m-%d %H:%M UTC") if snap else "brak danych"
            assert result == "brak danych"

    def test_single_snapshot_returns_date(self, db_session):
        """With one snapshot, should return its formatted date."""
        dt = datetime(2024, 3, 15, 10, 30, tzinfo=timezone.utc)
        snap = Snapshot(fetched_at=dt, village_count=100)
        db_session.add(snap)
        db_session.commit()

        latest = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
        result = latest.fetched_at.strftime("%Y-%m-%d %H:%M UTC")
        assert result == "2024-03-15 10:30 UTC"

    def test_multiple_snapshots_returns_latest(self, db_session):
        """With multiple snapshots, should return the most recent one."""
        s1 = Snapshot(fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc), village_count=50)
        s2 = Snapshot(fetched_at=datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc), village_count=200)
        db_session.add_all([s1, s2])
        db_session.commit()

        latest = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
        result = latest.fetched_at.strftime("%Y-%m-%d %H:%M UTC")
        assert result == "2024-06-15 14:00 UTC"


# ------------------------------------------------------------------ #
# _get_stats logic (from /tstats)
# ------------------------------------------------------------------ #


class TestGetStats:
    """Test the _get_stats logic from /tstats."""

    def test_empty_db(self, app):
        """Empty database returns zero counts."""
        with app.app_context():
            snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
            total_players = Player.query.count()
            total_alliances = Alliance.query.count()
            total_villages = snap.village_count if snap else 0

            assert total_players == 0
            assert total_alliances == 0
            assert total_villages == 0

    def test_player_count(self, db_session):
        """Should count players correctly."""
        db_session.add_all([
            Player(uid=1, name="Alice", tid=1, total_pop=500, village_count=3),
            Player(uid=2, name="Bob", tid=2, total_pop=300, village_count=1),
        ])
        db_session.commit()

        assert Player.query.count() == 2

    def test_alliance_count(self, db_session):
        """Should count alliances correctly."""
        db_session.add_all([
            Alliance(aid=1, name="ALLY1", total_pop=1000, member_count=5),
            Alliance(aid=2, name="ALLY2", total_pop=800, member_count=3),
            Alliance(aid=3, name="ALLY3", total_pop=200, member_count=1),
        ])
        db_session.commit()

        assert Alliance.query.count() == 3

    def test_village_count_from_snapshot(self, db_session):
        """Should get village count from latest snapshot."""
        s = Snapshot(fetched_at=datetime(2024, 3, 1, tzinfo=timezone.utc), village_count=14000)
        db_session.add(s)
        db_session.commit()

        snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
        assert snap.village_count == 14000

    def test_top_alliances_ordered_by_pop(self, db_session):
        """Top 5 alliances should be ordered by total_pop descending."""
        alliances = [
            Alliance(aid=i, name=f"A{i}", total_pop=pop, member_count=m)
            for i, (pop, m) in enumerate([
                (5000, 10), (3000, 8), (1000, 3), (8000, 15),
                (2000, 5), (500, 2), (9000, 20),
            ], start=1)
        ]
        db_session.add_all(alliances)
        db_session.commit()

        top = Alliance.query.order_by(Alliance.total_pop.desc()).limit(5).all()
        top_list = [(a.name, a.total_pop, a.member_count) for a in top]

        assert len(top_list) == 5
        assert top_list[0] == ("A7", 9000, 20)
        assert top_list[1] == ("A4", 8000, 15)
        pops = [t[1] for t in top_list]
        assert pops == sorted(pops, reverse=True)

    def test_top_alliances_fewer_than_five(self, db_session):
        """With fewer than 5 alliances, should return all of them."""
        db_session.add_all([
            Alliance(aid=1, name="OnlyOne", total_pop=100, member_count=1),
        ])
        db_session.commit()

        top = Alliance.query.order_by(Alliance.total_pop.desc()).limit(5).all()
        assert len(top) == 1
        assert top[0].name == "OnlyOne"

    def test_snap_date_returned(self, db_session):
        """Snapshot date should be formatted correctly."""
        dt = datetime(2024, 5, 20, 8, 45, tzinfo=timezone.utc)
        db_session.add(Snapshot(fetched_at=dt, village_count=100))
        db_session.commit()

        snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
        snap_date = snap.fetched_at.strftime("%Y-%m-%d %H:%M UTC")
        assert snap_date == "2024-05-20 08:45 UTC"

    def test_snap_date_none_when_no_snapshot(self, app):
        """Without snapshots, snap_date should be None."""
        with app.app_context():
            snap = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
            snap_date = snap.fetched_at.strftime("%Y-%m-%d %H:%M UTC") if snap else None
            assert snap_date is None
