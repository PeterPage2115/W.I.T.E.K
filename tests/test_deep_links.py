"""Tests for in-game deep link URL generation."""

from bot.deep_links import map_link, send_troops_link, marketplace_link, format_coord_with_link


SERVER = "https://rof.x3.international.travian.com"


def test_map_link():
    url = map_link(SERVER, 50, -30)
    assert url == f"{SERVER}/position_details.php?x=50&y=-30"


def test_map_link_strips_trailing_slash():
    url = map_link(SERVER + "/", 10, 20)
    assert url == f"{SERVER}/position_details.php?x=10&y=20"


def test_send_troops_link_reinforce():
    url = send_troops_link(SERVER, 10, 20, event_type=2)
    assert "tt=2" in url
    assert "x=10" in url
    assert "y=20" in url
    assert "eventType=2" in url


def test_send_troops_link_attack():
    url = send_troops_link(SERVER, -5, 15, event_type=3)
    assert "eventType=3" in url


def test_send_troops_with_troops():
    url = send_troops_link(SERVER, 0, 0, troops={"t1": 100, "t3": 50})
    assert "troop[t1]=100" in url
    assert "troop[t3]=50" in url


def test_marketplace_link():
    url = marketplace_link(SERVER, -5, 15)
    assert "gid=17" in url
    assert "x=-5" in url
    assert "y=15" in url
    assert "t=5" in url


def test_format_coord_with_link():
    result = format_coord_with_link(SERVER, 50, -30)
    assert "(50|-30)" in result
    assert "📍" in result
    assert SERVER in result
    assert "position_details.php" in result
