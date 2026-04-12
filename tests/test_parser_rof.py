"""Tests for 16-field RoF map.sql parser."""

from app.map_sql.parser import parse_line, VillageRow


def test_parse_rof_line_with_all_fields():
    """Full RoF line with region, capital, city, harbor, VP."""
    line = (
        "INSERT INTO `x_world` VALUES "
        "(5001,-15,88,9,7777,'Viking Village',3001,'VikingPlayer',"
        "500,'NORD',1250,'Venedae',FALSE,FALSE,TRUE,42);"
    )
    row = parse_line(line)
    assert row is not None
    assert row.map_id == 5001
    assert row.x == -15
    assert row.y == 88
    assert row.tid == 9
    assert row.population == 1250
    assert row.region == "Venedae"
    assert row.is_capital is False
    assert row.is_city is False
    assert row.has_harbor is True
    assert row.victory_points == 42


def test_parse_classic_line_nulls():
    """Classic server line — extra fields are NULL."""
    line = (
        "INSERT INTO x_world VALUES "
        "(1,-200,-200,3,10187,'Wioska',480,'player',38,'alliance',"
        "156,NULL,FALSE,NULL,NULL,NULL);"
    )
    row = parse_line(line)
    assert row is not None
    assert row.population == 156
    assert row.region is None
    assert row.is_capital is False
    assert row.is_city is None
    assert row.has_harbor is None
    assert row.victory_points is None


def test_parse_rof_line_with_null_region():
    """Oasis or special tile with NULL region."""
    line = (
        "INSERT INTO `x_world` VALUES "
        "(9999,0,0,4,0,'Occupied Oasis',0,'Nature',0,'',"
        "0,NULL,FALSE,NULL,NULL,NULL);"
    )
    row = parse_line(line)
    assert row is not None
    assert row.region is None
    assert row.victory_points is None


def test_parse_rof_capital():
    """Capital village flagged TRUE."""
    line = (
        "INSERT INTO `x_world` VALUES "
        "(100,50,-50,1,200,'Roma',300,'Caesar',"
        "10,'SPQR',5000,'Cimbri',TRUE,FALSE,FALSE,0);"
    )
    row = parse_line(line)
    assert row.is_capital is True
    assert row.is_city is False
    assert row.has_harbor is False
    assert row.region == "Cimbri"
    assert row.victory_points == 0


def test_parse_region_with_quotes():
    """Region name with special characters."""
    line = (
        "INSERT INTO `x_world` VALUES "
        "(200,10,20,3,300,'Village',400,'Player',"
        "50,'Alliance',1000,'O''Brien Land',FALSE,TRUE,FALSE,10);"
    )
    row = parse_line(line)
    assert row.region == "O'Brien Land"
    assert row.is_city is True
