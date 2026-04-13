"""Regression tests for lightweight runtime migrations."""

from app.database import _expected_column_types


def test_postgres_boolean_defaults_use_boolean_literals():
    """PostgreSQL ALTER TABLE must use TRUE/FALSE defaults, not 1/0."""
    expected = _expected_column_types(is_sqlite=False)

    assert expected["attack_reports"]["auto_resolved"] == "BOOLEAN DEFAULT FALSE"
    assert expected["battle_reports"]["is_manual"] == "BOOLEAN DEFAULT FALSE"
    assert expected["alerts"]["discord_eligible"] == "BOOLEAN DEFAULT TRUE"
