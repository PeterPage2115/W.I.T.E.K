"""Tests for RoF tribe ID correctness — tid 8=Spartans, tid 9=Vikings."""

from bot.tribes import TRIBES, get_legionnaire_stats


def test_tid_8_is_spartans():
    """Official Travian docs: tid 8 = Spartans."""
    tribe = TRIBES[8]
    assert tribe.name_en == "Spartans"
    assert tribe.name_pl == "Spartanie"
    assert tribe.emoji == "🛡️"


def test_tid_9_is_vikings():
    """Official Travian docs: tid 9 = Vikings."""
    tribe = TRIBES[9]
    assert tribe.name_en == "Vikings"
    assert tribe.name_pl == "Wikingowie"
    assert tribe.emoji == "⛵"


def test_spartans_have_hoplite():
    assert TRIBES[8].units[0].name == "Hoplite"


def test_vikings_have_thrall():
    assert TRIBES[9].units[0].name == "Thrall"


def test_all_tribes_have_unique_tids():
    tids = [t.tid for t in TRIBES.values()]
    assert len(tids) == len(set(tids))


def test_legionnaire_default_stats():
    stats = get_legionnaire_stats(rebalanced=False)
    assert stats["def_cav"] == 50
    assert stats["speed"] == 6


def test_legionnaire_rebalanced_stats():
    stats = get_legionnaire_stats(rebalanced=True)
    assert stats["def_cav"] == 70
    assert stats["speed"] == 7
