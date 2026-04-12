"""End-to-end test: RoF map.sql → collector → DB with 16 fields."""

import pytest
from app import create_app
from app.database import db as _db
from app.models import Snapshot, Village, Player
from app.map_sql.collector import store_snapshot


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TRAVIAN_SERVER_URL = "https://test.travian.com"
    TRAVIAN_MAP_SIZE = 401
    TRAVIAN_OUR_ALLIANCES = [1]
    POP_DROP_THRESHOLD = 15


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


ROF_MAP_SQL = """INSERT INTO `x_world` VALUES (1,50,-50,9,100,'Viking Town',200,'Ragnar',10,'NORD',1500,'Venedae',TRUE,FALSE,TRUE,100);
INSERT INTO `x_world` VALUES (2,51,-49,8,101,'Sparta City',201,'Leonidas',10,'NORD',2000,'Cimbri',FALSE,TRUE,FALSE,50);
INSERT INTO `x_world` VALUES (3,52,-48,9,102,'Second Viking',200,'Ragnar',10,'NORD',800,'Venedae',FALSE,FALSE,FALSE,30);
"""


def test_store_rof_snapshot(app):
    with app.app_context():
        snap = store_snapshot(ROF_MAP_SQL)
        assert snap.village_count == 3

        v1 = Village.query.filter_by(map_id=1, snapshot_id=snap.id).first()
        assert v1.region == "Venedae"
        assert v1.is_capital is True
        assert v1.has_harbor is True
        assert v1.victory_points == 100

        v2 = Village.query.filter_by(map_id=2, snapshot_id=snap.id).first()
        assert v2.region == "Cimbri"
        assert v2.is_city is True
        assert v2.has_harbor is False


def test_mixed_tribe_player(app):
    with app.app_context():
        store_snapshot(ROF_MAP_SQL)
        ragnar = Player.query.filter_by(uid=200).first()
        assert ragnar.tid == 9  # 2 Viking villages vs 0 others
        assert ragnar.village_count == 2


def test_classic_format_still_works(app):
    classic = "INSERT INTO x_world VALUES (1,0,0,1,1,'Rome',1,'Caesar',1,'SPQR',500,NULL,FALSE,NULL,NULL,NULL);\n"
    with app.app_context():
        snap = store_snapshot(classic)
        v = Village.query.filter_by(map_id=1, snapshot_id=snap.id).first()
        assert v.region is None
        assert v.is_capital is False
        assert v.has_harbor is None
        assert v.victory_points is None
