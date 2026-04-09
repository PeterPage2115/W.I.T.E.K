"""Tests for coordinate-level lock preventing duplicate defense threads."""

import asyncio
import pytest

from bot.cogs.attacks import _get_coord_lock, _coord_locks


class TestCoordLock:
    def setup_method(self):
        _coord_locks.clear()

    def test_same_coords_return_same_lock(self):
        lock_a = _get_coord_lock(76, 43)
        lock_b = _get_coord_lock(76, 43)
        assert lock_a is lock_b

    def test_different_coords_return_different_locks(self):
        lock_a = _get_coord_lock(76, 43)
        lock_b = _get_coord_lock(55, 22)
        assert lock_a is not lock_b

    def test_lock_is_asyncio_lock(self):
        lock = _get_coord_lock(10, -20)
        assert isinstance(lock, asyncio.Lock)
