"""Tests for safe-troop distance calculator (inverse of travel time)."""
import pytest
from bot.utils import _calc_travel_seconds, calc_safe_distance


class TestCalcSafeDistance:
    def test_basic_short_distance(self):
        """Phalanx (14 f/h), 2 hours → ~14 fields one way."""
        dist = calc_safe_distance(speed=14, hours_away=2.0)
        round_trip = 2 * _calc_travel_seconds(dist, 14)
        assert round_trip >= 2.0 * 3600 - 1
        assert 13.5 <= dist <= 14.5

    def test_zero_hours(self):
        dist = calc_safe_distance(speed=14, hours_away=0.0)
        assert dist == 0.0

    def test_negative_hours(self):
        dist = calc_safe_distance(speed=14, hours_away=-1.0)
        assert dist == 0.0

    def test_with_tournament_square(self):
        """TS makes troops faster → can go farther in same time."""
        dist_no_ts = calc_safe_distance(speed=14, hours_away=4.0, ts_level=0)
        dist_with_ts = calc_safe_distance(speed=14, hours_away=4.0, ts_level=10)
        assert dist_with_ts > dist_no_ts

    def test_with_boots(self):
        dist_no = calc_safe_distance(speed=14, hours_away=4.0)
        dist_boots = calc_safe_distance(speed=14, hours_away=4.0, boots_bonus=0.75)
        assert dist_boots > dist_no

    def test_round_trip_consistency(self):
        """Verify round trip >= hours_away for many combinations."""
        for speed in [6, 10, 14, 19, 32]:
            for hours in [1.0, 2.0, 4.0, 8.0]:
                for ts in [0, 5, 10, 20]:
                    dist = calc_safe_distance(speed=speed, hours_away=hours, ts_level=ts)
                    if dist <= 0:
                        continue
                    rt = 2 * _calc_travel_seconds(dist, speed, ts_level=ts)
                    assert rt >= hours * 3600 - 2, (
                        f"speed={speed}, hours={hours}, ts={ts}: "
                        f"dist={dist:.2f}, rt={rt:.1f}s < {hours*3600}s"
                    )

    def test_long_distance_with_ts(self):
        """TS20 allows much farther travel than without."""
        dist = calc_safe_distance(speed=6, hours_away=10.0, ts_level=20)
        dist_no_ts = calc_safe_distance(speed=6, hours_away=10.0, ts_level=0)
        assert dist > dist_no_ts * 1.5

    def test_artifact_multiplier(self):
        dist_no = calc_safe_distance(speed=14, hours_away=4.0)
        dist_art = calc_safe_distance(speed=14, hours_away=4.0, artifact_mult=2.0)
        assert dist_art > dist_no
