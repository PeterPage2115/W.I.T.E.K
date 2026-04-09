"""Testy dla komend ekonomicznych — /tcropper, /tszukaj, /tporownaj."""

import pytest
from app import create_app
from app.database import db as _db
from app.models import Alliance, Snapshot, Village

from bot.cogs.economy import (
    CROPPER_TYPES,
    _alliance_growth,
    _alliance_stats,
    _bbox_filter,
    _build_comparison_embed,
    _build_cropper_embed,
    _build_search_embed,
    _extract_landscape_type,
    _find_alliance,
    _fmt,
    _search_villages,
    _tiles_in_radius,
)
from bot.utils import torus_distance


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
# _tiles_in_radius
# ------------------------------------------------------------------ #

class TestTilesInRadius:
    def test_center_included(self):
        tiles = _tiles_in_radius(0, 0, 5, 401)
        assert (0, 0) in tiles

    def test_radius_zero_returns_center_only(self):
        # radius=0 → only center
        tiles = _tiles_in_radius(10, 20, 0, 401)
        assert tiles == [(10, 20)]

    def test_small_radius(self):
        tiles = _tiles_in_radius(0, 0, 1, 401)
        expected = {(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)}
        assert set(tiles) == expected

    def test_circle_filter(self):
        """Tiles outside the circle but inside the square should be excluded."""
        tiles = _tiles_in_radius(0, 0, 5, 401)
        for x, y in tiles:
            assert x * x + y * y <= 25

    def test_torus_wrap_positive(self):
        """Tiles near map edge wrap around."""
        tiles = _tiles_in_radius(199, 0, 5, 401)
        # Should include wrapped coords like -200, -199
        xs = {t[0] for t in tiles}
        assert -200 in xs or 200 in xs  # should wrap

    def test_torus_wrap_negative(self):
        tiles = _tiles_in_radius(-199, 0, 5, 401)
        xs = {t[0] for t in tiles}
        assert 200 in xs or -200 in xs

    def test_sorted_by_distance(self):
        """Tiles should be sorted by distance from center (closest first)."""
        tiles = _tiles_in_radius(0, 0, 10, 401)
        assert tiles[0] == (0, 0)
        dists = [x * x + y * y for x, y in tiles]
        assert dists == sorted(dists)

    def test_count_radius_5(self):
        """Radius 5 → should be roughly π*25 ≈ 78 tiles."""
        tiles = _tiles_in_radius(0, 0, 5, 401)
        assert 70 < len(tiles) < 90


# ------------------------------------------------------------------ #
# _extract_landscape_type
# ------------------------------------------------------------------ #

class TestExtractLandscapeType:
    def test_nested_tiles_format(self):
        data = {"response": {"tiles": [{"landscape": {"type": 3}}]}}
        assert _extract_landscape_type(data) == 3

    def test_tiles_without_response_wrapper(self):
        data = {"tiles": [{"landscape": {"type": 4}}]}
        assert _extract_landscape_type(data) == 4

    def test_fieldtype_in_tile(self):
        data = {"tiles": [{"fieldType": 5}]}
        assert _extract_landscape_type(data) == 5

    def test_restype_in_tile(self):
        data = {"tiles": [{"resType": 3}]}
        assert _extract_landscape_type(data) == 3

    def test_flat_fieldtype(self):
        data = {"fieldType": 4}
        assert _extract_landscape_type(data) == 4

    def test_flat_restype(self):
        data = {"resType": 5}
        assert _extract_landscape_type(data) == 5

    def test_flat_landscape_type(self):
        data = {"landscapeType": 3}
        assert _extract_landscape_type(data) == 3

    def test_none_for_empty(self):
        assert _extract_landscape_type({}) is None

    def test_none_for_non_dict(self):
        assert _extract_landscape_type("not a dict") is None
        assert _extract_landscape_type(None) is None

    def test_none_for_missing_type(self):
        data = {"tiles": [{"landscape": {}}]}
        assert _extract_landscape_type(data) is None

    def test_empty_tiles_list(self):
        data = {"tiles": []}
        assert _extract_landscape_type(data) is None


# ------------------------------------------------------------------ #
# CROPPER_TYPES
# ------------------------------------------------------------------ #

class TestCropperTypes:
    def test_15c_mapping(self):
        assert CROPPER_TYPES[3] == "15c"

    def test_9c_mappings(self):
        assert CROPPER_TYPES[4] == "9c"
        assert CROPPER_TYPES[5] == "9c"

    def test_non_cropper_excluded(self):
        assert 1 not in CROPPER_TYPES
        assert 2 not in CROPPER_TYPES
        assert 6 not in CROPPER_TYPES


# ------------------------------------------------------------------ #
# _search_villages (DB integration)
# ------------------------------------------------------------------ #

class TestSearchVillages:
    def test_no_snapshot(self, app, db_session):
        results, snap_date = _search_villages(0, 0, 20, 401, "", "", 0, 0)
        assert results is None
        assert snap_date is None

    def test_finds_nearby_villages(self, app, db_session):
        snap = Snapshot(village_count=3)
        db_session.add(snap)
        db_session.flush()

        db_session.add(_make_village(1, snap.id, 5, 5, 100, "Gracz1", population=200))
        db_session.add(_make_village(2, snap.id, 10, 10, 101, "Gracz2", population=300))
        db_session.add(_make_village(3, snap.id, 100, 100, 102, "Far", population=500))
        db_session.commit()

        results, snap_date = _search_villages(0, 0, 20, 401, "", "", 0, 0)
        assert len(results) == 2
        assert all(r["dist"] <= 20 for r in results)
        assert snap_date is not None

    def test_filter_by_player(self, app, db_session):
        snap = Snapshot(village_count=2)
        db_session.add(snap)
        db_session.flush()

        db_session.add(_make_village(1, snap.id, 5, 5, 100, "Alpha", population=200))
        db_session.add(_make_village(2, snap.id, 6, 6, 101, "Beta", population=300))
        db_session.commit()

        results, _ = _search_villages(0, 0, 20, 401, "Alpha", "", 0, 0)
        assert len(results) == 1
        assert results[0]["player"] == "Alpha"

    def test_filter_by_alliance(self, app, db_session):
        snap = Snapshot(village_count=2)
        db_session.add(snap)
        db_session.flush()

        db_session.add(_make_village(
            1, snap.id, 5, 5, 100, "Gracz1", aid=10,
            alliance_name="UFOLODZY", population=200,
        ))
        db_session.add(_make_village(
            2, snap.id, 6, 6, 101, "Gracz2", aid=20,
            alliance_name="Wrogowie", population=300,
        ))
        db_session.commit()

        results, _ = _search_villages(0, 0, 20, 401, "", "UFO", 0, 0)
        assert len(results) == 1
        assert results[0]["alliance"] == "UFOLODZY"

    def test_filter_by_min_pop(self, app, db_session):
        snap = Snapshot(village_count=2)
        db_session.add(snap)
        db_session.flush()

        db_session.add(_make_village(1, snap.id, 5, 5, 100, "G1", population=50))
        db_session.add(_make_village(2, snap.id, 6, 6, 101, "G2", population=500))
        db_session.commit()

        results, _ = _search_villages(0, 0, 20, 401, "", "", 100, 0)
        assert len(results) == 1
        assert results[0]["pop"] == 500

    def test_filter_by_max_pop(self, app, db_session):
        snap = Snapshot(village_count=2)
        db_session.add(snap)
        db_session.flush()

        db_session.add(_make_village(1, snap.id, 5, 5, 100, "G1", population=50))
        db_session.add(_make_village(2, snap.id, 6, 6, 101, "G2", population=500))
        db_session.commit()

        results, _ = _search_villages(0, 0, 20, 401, "", "", 0, 100)
        assert len(results) == 1
        assert results[0]["pop"] == 50

    def test_excludes_unoccupied(self, app, db_session):
        """Villages with uid=0 should not appear in search results."""
        snap = Snapshot(village_count=2)
        db_session.add(snap)
        db_session.flush()

        db_session.add(_make_village(1, snap.id, 5, 5, 0, "", population=0))
        db_session.add(_make_village(2, snap.id, 6, 6, 100, "Gracz", population=200))
        db_session.commit()

        results, _ = _search_villages(0, 0, 20, 401, "", "", 0, 0)
        assert len(results) == 1
        assert results[0]["player"] == "Gracz"

    def test_uses_latest_snapshot(self, app, db_session):
        """Should only return villages from the latest snapshot."""
        from datetime import datetime, timezone

        old_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        new_time = datetime(2024, 6, 1, tzinfo=timezone.utc)

        snap_old = Snapshot(fetched_at=old_time, village_count=1)
        db_session.add(snap_old)
        db_session.flush()
        db_session.add(_make_village(1, snap_old.id, 5, 5, 100, "OldPlayer", population=100))

        snap_new = Snapshot(fetched_at=new_time, village_count=1)
        db_session.add(snap_new)
        db_session.flush()
        db_session.add(_make_village(2, snap_new.id, 5, 5, 101, "NewPlayer", population=200))
        db_session.commit()

        results, _ = _search_villages(0, 0, 20, 401, "", "", 0, 0)
        assert len(results) == 1
        assert results[0]["player"] == "NewPlayer"


# ------------------------------------------------------------------ #
# _bbox_filter
# ------------------------------------------------------------------ #

class TestBboxFilter:
    def test_normal_range(self, app, db_session):
        """Center (0, 0), radius 10 — simple range."""
        snap = Snapshot(village_count=3)
        db_session.add(snap)
        db_session.flush()

        db_session.add(_make_village(1, snap.id, 5, 5, 100, "In", population=100))
        db_session.add(_make_village(2, snap.id, -5, -5, 101, "In2", population=100))
        db_session.add(_make_village(3, snap.id, 50, 50, 102, "Out", population=100))
        db_session.commit()

        q = Village.query.filter(
            Village.snapshot_id == snap.id,
            _bbox_filter(Village.x, 0, 10, 401),
            _bbox_filter(Village.y, 0, 10, 401),
        )
        results = q.all()
        assert len(results) == 2

    def test_wrap_positive_edge(self, app, db_session):
        """Village near +200 with center near +200 should be found."""
        snap = Snapshot(village_count=2)
        db_session.add(snap)
        db_session.flush()

        db_session.add(_make_village(1, snap.id, 199, 0, 100, "Near", population=100))
        db_session.add(_make_village(2, snap.id, -198, 0, 101, "Wrap", population=100))
        db_session.commit()

        q = Village.query.filter(
            Village.snapshot_id == snap.id,
            _bbox_filter(Village.x, 200, 5, 401),
            _bbox_filter(Village.y, 0, 5, 401),
        )
        results = q.all()
        assert len(results) == 2


# ------------------------------------------------------------------ #
# _build_cropper_embed
# ------------------------------------------------------------------ #

class TestBuildCropperEmbed:
    def test_basic_embed(self):
        croppers = [
            {"x": 10, "y": 20, "type": "15c", "dist": 5.0,
             "occupied": False, "lt": 3},
            {"x": 15, "y": 25, "type": "9c", "dist": 8.0,
             "occupied": True, "player": "Gracz", "alliance": "ALI",
             "pop": 500, "tid": 1, "lt": 4},
        ]
        embed = _build_cropper_embed(
            croppers, 0, 0, 30, "oba", "https://test.travian.com",
            "2024-01-01 00:00 UTC", False,
        )
        assert "🌾" in embed.title
        assert "WOLNE" in embed.description
        assert "Gracz" in embed.description
        assert "2 cropperów" in embed.footer.text

    def test_truncated_flag(self):
        croppers = [
            {"x": 1, "y": 1, "type": "9c", "dist": 1.0,
             "occupied": False, "lt": 4},
        ]
        embed = _build_cropper_embed(
            croppers, 0, 0, 50, "9c", "https://test.travian.com",
            None, True,
        )
        assert "częściowy" in embed.footer.text


# ------------------------------------------------------------------ #
# _build_search_embed
# ------------------------------------------------------------------ #

class TestBuildSearchEmbed:
    def test_basic_embed(self):
        results = [
            {"x": 5, "y": 5, "name": "Wioska", "player": "Gracz",
             "alliance": "ALI", "pop": 200, "tid": 1, "dist": 7.07},
        ]
        embed = _build_search_embed(
            results, 0, 0, 20, "https://test.travian.com",
            "2024-01-01 00:00 UTC", "", "",
        )
        assert "Wioski" in embed.title
        assert "Gracz" in embed.description
        assert "1 wiosek" in embed.footer.text

    def test_with_filters_in_title(self):
        results = [
            {"x": 5, "y": 5, "name": "W", "player": "P", "alliance": "",
             "pop": 100, "tid": 2, "dist": 7.07},
        ]
        embed = _build_search_embed(
            results, 0, 0, 20, "https://test.travian.com",
            None, "P", "SOJ",
        )
        assert "gracz: P" in embed.title
        assert "sojusz: SOJ" in embed.title


# ------------------------------------------------------------------ #
# _fmt (number formatting)
# ------------------------------------------------------------------ #

class TestFmt:
    def test_small_number(self):
        assert _fmt(42) == "42"

    def test_thousands(self):
        assert _fmt(1234) == "1 234"

    def test_millions(self):
        assert _fmt(1234567) == "1 234 567"

    def test_zero(self):
        assert _fmt(0) == "0"

    def test_negative(self):
        assert _fmt(-5000) == "-5 000"


# ------------------------------------------------------------------ #
# _find_alliance
# ------------------------------------------------------------------ #

class TestFindAlliance:
    def test_find_by_exact_name(self, app, db_session):
        db_session.add(Alliance(aid=10, name="UFOLODZY"))
        db_session.commit()

        result = _find_alliance("UFOLODZY")
        assert result is not None
        assert result["aid"] == 10
        assert result["name"] == "UFOLODZY"

    def test_find_by_name_case_insensitive(self, app, db_session):
        db_session.add(Alliance(aid=10, name="UFOLODZY"))
        db_session.commit()

        result = _find_alliance("ufolodzy")
        assert result is not None
        assert result["aid"] == 10

    def test_find_by_partial_name(self, app, db_session):
        db_session.add(Alliance(aid=10, name="UFOLODZY"))
        db_session.commit()

        result = _find_alliance("UFO")
        assert result is not None
        assert result["aid"] == 10

    def test_find_by_aid(self, app, db_session):
        db_session.add(Alliance(aid=42, name="TestAlliance"))
        db_session.commit()

        result = _find_alliance("42")
        assert result is not None
        assert result["aid"] == 42

    def test_not_found(self, app, db_session):
        db_session.add(Alliance(aid=10, name="UFOLODZY"))
        db_session.commit()

        result = _find_alliance("NIEISTNIEJACY")
        assert result is None


# ------------------------------------------------------------------ #
# _alliance_stats
# ------------------------------------------------------------------ #

class TestAllianceStats:
    def test_basic_stats(self, app, db_session):
        snap = Snapshot(village_count=4)
        db_session.add(snap)
        db_session.flush()

        # Alliance 10: 2 players, 3 villages
        db_session.add(_make_village(1, snap.id, 0, 0, 100, "Gracz1",
                                     aid=10, alliance_name="ALI", population=500, tid=1))
        db_session.add(_make_village(2, snap.id, 1, 1, 100, "Gracz1",
                                     aid=10, alliance_name="ALI", population=300, tid=1))
        db_session.add(_make_village(3, snap.id, 2, 2, 101, "Gracz2",
                                     aid=10, alliance_name="ALI", population=200, tid=2))
        # Different alliance
        db_session.add(_make_village(4, snap.id, 3, 3, 102, "Enemy",
                                     aid=20, alliance_name="WRG", population=1000, tid=3))
        db_session.commit()

        stats = _alliance_stats(10)
        assert stats is not None
        assert stats["total_pop"] == 1000  # 500+300+200
        assert stats["village_count"] == 3
        assert stats["member_count"] == 2
        assert stats["avg_pop"] == 500  # 1000 // 2

    def test_top5_sorted_by_pop(self, app, db_session):
        snap = Snapshot(village_count=3)
        db_session.add(snap)
        db_session.flush()

        db_session.add(_make_village(1, snap.id, 0, 0, 100, "Low",
                                     aid=10, population=100, tid=1))
        db_session.add(_make_village(2, snap.id, 1, 1, 101, "High",
                                     aid=10, population=900, tid=2))
        db_session.add(_make_village(3, snap.id, 2, 2, 102, "Mid",
                                     aid=10, population=500, tid=3))
        db_session.commit()

        stats = _alliance_stats(10)
        names = [p["name"] for p in stats["top5"]]
        assert names == ["High", "Mid", "Low"]

    def test_tribe_distribution(self, app, db_session):
        snap = Snapshot(village_count=3)
        db_session.add(snap)
        db_session.flush()

        db_session.add(_make_village(1, snap.id, 0, 0, 100, "P1",
                                     aid=10, population=100, tid=1))
        db_session.add(_make_village(2, snap.id, 1, 1, 101, "P2",
                                     aid=10, population=200, tid=1))
        db_session.add(_make_village(3, snap.id, 2, 2, 102, "P3",
                                     aid=10, population=300, tid=3))
        db_session.commit()

        stats = _alliance_stats(10)
        assert stats["tribes"] == {1: 2, 3: 1}

    def test_no_snapshot_returns_none(self, app, db_session):
        assert _alliance_stats(10) is None

    def test_no_villages_returns_none(self, app, db_session):
        snap = Snapshot(village_count=0)
        db_session.add(snap)
        db_session.commit()

        assert _alliance_stats(999) is None


# ------------------------------------------------------------------ #
# _alliance_growth
# ------------------------------------------------------------------ #

class TestAllianceGrowth:
    def test_growth_calculated(self, app, db_session):
        from datetime import datetime, timezone

        snap_old = Snapshot(fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                            village_count=1)
        db_session.add(snap_old)
        db_session.flush()
        db_session.add(_make_village(1, snap_old.id, 0, 0, 100, "P1",
                                     aid=10, population=500))

        snap_new = Snapshot(fetched_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
                            village_count=1)
        db_session.add(snap_new)
        db_session.flush()
        db_session.add(_make_village(2, snap_new.id, 0, 0, 100, "P1",
                                     aid=10, population=700))
        db_session.commit()

        growth, has_prev = _alliance_growth(10, snap_new.id)
        assert has_prev is True
        assert growth == 200

    def test_decline_negative(self, app, db_session):
        from datetime import datetime, timezone

        snap_old = Snapshot(fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                            village_count=1)
        db_session.add(snap_old)
        db_session.flush()
        db_session.add(_make_village(1, snap_old.id, 0, 0, 100, "P1",
                                     aid=10, population=1000))

        snap_new = Snapshot(fetched_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
                            village_count=1)
        db_session.add(snap_new)
        db_session.flush()
        db_session.add(_make_village(2, snap_new.id, 0, 0, 100, "P1",
                                     aid=10, population=800))
        db_session.commit()

        growth, has_prev = _alliance_growth(10, snap_new.id)
        assert growth == -200

    def test_no_previous_snapshot(self, app, db_session):
        snap = Snapshot(village_count=1)
        db_session.add(snap)
        db_session.flush()
        db_session.add(_make_village(1, snap.id, 0, 0, 100, "P1",
                                     aid=10, population=500))
        db_session.commit()

        growth, has_prev = _alliance_growth(10, snap.id)
        assert has_prev is False
        assert growth is None


# ------------------------------------------------------------------ #
# _build_comparison_embed
# ------------------------------------------------------------------ #

class TestBuildComparisonEmbed:
    def test_basic_embed(self):
        stats1 = {
            "total_pop": 50000, "village_count": 100, "member_count": 20,
            "avg_pop": 2500,
            "top5": [{"name": "Top1", "pop": 10000}, {"name": "Top2", "pop": 8000}],
            "tribes": {1: 10, 2: 8, 3: 2},
            "snap_date": "2024-01-01 00:00 UTC", "snap_id": 1,
        }
        stats2 = {
            "total_pop": 40000, "village_count": 80, "member_count": 15,
            "avg_pop": 2666,
            "top5": [{"name": "Enemy1", "pop": 12000}],
            "tribes": {1: 5, 2: 10},
            "snap_date": "2024-01-01 00:00 UTC", "snap_id": 1,
        }
        embed = _build_comparison_embed("NASI", stats1, 500, "WROG", stats2, -200)
        assert "NASI" in embed.description
        assert "WROG" in embed.description
        assert "Porównanie" in embed.title
        # Check fields exist
        field_names = [f.name for f in embed.fields]
        assert "⚖️ Statystyki" in field_names
        assert "🗡️ Rozkład plemion" in field_names
        assert "🏆 Top 5 NASI" in field_names
        assert "🏆 Top 5 WROG" in field_names

    def test_embed_with_no_growth(self):
        stats = {
            "total_pop": 1000, "village_count": 5, "member_count": 3,
            "avg_pop": 333,
            "top5": [{"name": "P1", "pop": 500}],
            "tribes": {1: 3},
            "snap_date": None, "snap_id": 1,
        }
        embed = _build_comparison_embed("A", stats, None, "B", stats, None)
        # Should not crash; growth line should not appear
        stats_field = [f for f in embed.fields if f.name == "⚖️ Statystyki"][0]
        assert "Zmiana" not in stats_field.value

    def test_numbers_formatted_with_spaces(self):
        stats = {
            "total_pop": 456789, "village_count": 120, "member_count": 45,
            "avg_pop": 10151,
            "top5": [{"name": "P1", "pop": 25000}],
            "tribes": {1: 45},
            "snap_date": None, "snap_id": 1,
        }
        embed = _build_comparison_embed("A", stats, None, "B", stats, None)
        stats_field = [f for f in embed.fields if f.name == "⚖️ Statystyki"][0]
        assert "456 789" in stats_field.value
        assert "10 151" in stats_field.value
