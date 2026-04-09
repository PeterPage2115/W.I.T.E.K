"""Tests for map.sql parser."""

from app.map_sql.parser import parse_line, parse_map_sql, VillageRow


def test_parse_basic_line():
    line = "INSERT INTO x_world VALUES (12345,-23,45,1,98765,'Moja Wioska',100,'Gracz1',50,'Sojusz A',487,NULL,FALSE,NULL,NULL,NULL);"
    row = parse_line(line)
    assert row is not None
    assert row.map_id == 12345
    assert row.x == -23
    assert row.y == 45
    assert row.tid == 1
    assert row.vid == 98765
    assert row.name == "Moja Wioska"
    assert row.uid == 100
    assert row.player_name == "Gracz1"
    assert row.aid == 50
    assert row.alliance_name == "Sojusz A"
    assert row.population == 487


def test_parse_escaped_quotes():
    line = "INSERT INTO x_world VALUES (1,0,0,2,2,'Wioska O''Briena',3,'O''Brien',4,'L''alliance',100,NULL,FALSE,NULL,NULL,NULL);"
    row = parse_line(line)
    assert row is not None
    assert row.name == "Wioska O'Briena"
    assert row.player_name == "O'Brien"
    assert row.alliance_name == "L'alliance"


def test_parse_unicode_names():
    line = "INSERT INTO x_world VALUES (999,100,-200,3,555,'Wioska Ząb',200,'Gracz Ćma',60,'Ślązak',250,NULL,FALSE,NULL,NULL,NULL);"
    row = parse_line(line)
    assert row is not None
    assert row.name == "Wioska Ząb"
    assert row.player_name == "Gracz Ćma"
    assert row.alliance_name == "Ślązak"


def test_parse_empty_names():
    line = "INSERT INTO x_world VALUES (1,0,0,1,1,'',0,'',0,'',0,NULL,FALSE,NULL,NULL,NULL);"
    row = parse_line(line)
    assert row is not None
    assert row.name == ""
    assert row.player_name == ""
    assert row.alliance_name == ""


def test_parse_negative_coords():
    line = "INSERT INTO x_world VALUES (5000,-200,-200,2,777,'Far Away',10,'Player',1,'Ally',300,NULL,FALSE,NULL,NULL,NULL);"
    row = parse_line(line)
    assert row is not None
    assert row.x == -200
    assert row.y == -200


def test_parse_invalid_line():
    assert parse_line("") is None
    assert parse_line("-- comment") is None
    assert parse_line("not a valid line") is None


def test_parse_map_sql_multiple():
    text = """INSERT INTO x_world VALUES (1,10,20,1,100,'W1',10,'P1',1,'A1',100,NULL,FALSE,NULL,NULL,NULL);
INSERT INTO x_world VALUES (2,-10,-20,2,200,'W2',20,'P2',2,'A2',200,NULL,FALSE,NULL,NULL,NULL);
-- this is a comment
INSERT INTO x_world VALUES (3,0,0,3,300,'W3',30,'P3',0,'',50,NULL,FALSE,NULL,NULL,NULL);"""
    rows = parse_map_sql(text)
    assert len(rows) == 3
    assert rows[0].map_id == 1
    assert rows[1].x == -10
    assert rows[2].alliance_name == ""
