"""Verify all cogs load without errors."""

import pytest


@pytest.mark.integration
class TestCogLoading:
    def test_attacks_cog_imports(self):
        from bot.cogs.attacks import Attacks
        assert Attacks is not None

    def test_defense_cog_imports(self):
        from bot.cogs.defense import Defense
        assert Defense is not None

    def test_economy_cog_imports(self):
        from bot.cogs.economy import Economy
        assert Economy is not None

    def test_general_cog_imports(self):
        from bot.cogs.general import General
        assert General is not None

    def test_identity_cog_imports(self):
        from bot.cogs.identity import Identity
        assert Identity is not None

    def test_alerts_cog_imports(self):
        from bot.cogs.alerts import AlertsCog
        assert AlertsCog is not None

    def test_recon_cog_imports(self):
        from bot.cogs.recon import Recon
        assert Recon is not None

    def test_digest_cog_imports(self):
        from bot.cogs.digest import Digest
        assert Digest is not None

    def test_tribes_module(self):
        from bot.tribes import TRIBES
        assert len(TRIBES) >= 7  # tid 1,2,3,6,7,8,9

    def test_utils_generated_dicts(self):
        from bot.utils import UNIT_SPEEDS, UNIT_CROP, UNIT_COMBAT, TRIBE_NAMES
        assert len(UNIT_SPEEDS) >= 7
        assert len(UNIT_CROP) >= 7
        assert len(UNIT_COMBAT) >= 7
        assert 6 in TRIBE_NAMES  # Egyptians
        assert 9 in TRIBE_NAMES  # Spartans
