"""SQLAlchemy models for WITEK."""

from datetime import datetime, timezone
from .database import db


def _utcnow():
    return datetime.now(timezone.utc)


class Snapshot(db.Model):
    __tablename__ = "snapshots"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fetched_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    village_count = db.Column(db.Integer)

    villages = db.relationship("Village", back_populates="snapshot", lazy="dynamic")


class Village(db.Model):
    __tablename__ = "villages"

    map_id = db.Column(db.Integer, nullable=False, primary_key=True)
    snapshot_id = db.Column(
        db.Integer, db.ForeignKey("snapshots.id"), nullable=False, primary_key=True
    )
    x = db.Column(db.Integer, nullable=False)
    y = db.Column(db.Integer, nullable=False)
    tid = db.Column(db.Integer)  # tribe: 1=Romans, 2=Teutons, 3=Gauls
    vid = db.Column(db.Integer)  # village id
    name = db.Column(db.Text)
    uid = db.Column(db.Integer)  # player id
    player_name = db.Column(db.Text)
    aid = db.Column(db.Integer)  # alliance id
    alliance_name = db.Column(db.Text)
    population = db.Column(db.Integer)

    snapshot = db.relationship("Snapshot", back_populates="villages")

    __table_args__ = (
        db.Index("ix_villages_uid_snapshot", "uid", "snapshot_id"),
        db.Index("ix_villages_aid_snapshot", "aid", "snapshot_id"),
        db.Index("ix_villages_snapshot_xy", "snapshot_id", "x", "y"),
    )


class Player(db.Model):
    __tablename__ = "players"

    uid = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    tid = db.Column(db.Integer)
    aid = db.Column(db.Integer)
    alliance_name = db.Column(db.Text)
    total_pop = db.Column(db.Integer, default=0)
    village_count = db.Column(db.Integer, default=0)
    first_seen_at = db.Column(db.DateTime, default=_utcnow)
    last_updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)


class Alliance(db.Model):
    __tablename__ = "alliances"

    aid = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    member_count = db.Column(db.Integer, default=0)
    total_pop = db.Column(db.Integer, default=0)
    first_seen_at = db.Column(db.DateTime, default=_utcnow)
    last_updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)


class User(db.Model):
    """Discord ↔ Travian identity mapping.

    travian_uid is nullable — a user can /tlink before the first snapshot
    (rubber-duck finding #7). No FK to players — resolved lazily at query time.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    discord_id = db.Column(db.BigInteger, unique=True, nullable=False)
    discord_name = db.Column(db.Text)
    travian_uid = db.Column(db.Integer, nullable=True)
    travian_name = db.Column(db.Text)
    role = db.Column(db.Text, default="member")  # leader / officer / member
    linked_at = db.Column(db.DateTime, default=_utcnow)
    created_at = db.Column(db.DateTime, default=_utcnow)


class AttackReport(db.Model):
    """Player-reported attack on an alliance village."""

    __tablename__ = "attack_reports"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    reported_by_discord = db.Column(db.Text, nullable=False)
    reported_by_name = db.Column(db.Text)
    attacker_name = db.Column(db.Text)
    attacker_alliance = db.Column(db.Text)
    attacker_x = db.Column(db.Integer, nullable=True)
    attacker_y = db.Column(db.Integer, nullable=True)
    defender_name = db.Column(db.Text)
    defender_village = db.Column(db.Text)
    defender_x = db.Column(db.Integer)
    defender_y = db.Column(db.Integer)
    attack_time = db.Column(db.Text)           # raw user input e.g. "14:30"
    attack_unix = db.Column(db.Integer)         # Unix timestamp for Discord <t:>
    notes = db.Column(db.Text)
    raw_text = db.Column(db.Text)
    wall_level = db.Column(db.Integer, nullable=True)
    crop_amount = db.Column(db.Integer, nullable=True)
    crop_production = db.Column(db.Integer, nullable=True)
    status = db.Column(db.Text, default="reported")  # reported / defending / resolved
    forum_thread_id = db.Column(db.BigInteger)  # Discord forum thread ID
    resolved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)


TRIBE_NAMES = {1: "Rzymianie", 2: "Germanie", 3: "Galowie"}


class VillageTroops(db.Model):
    """Current troop snapshot for a village (latest wins)."""

    __tablename__ = "village_troops"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    village_x = db.Column(db.Integer, nullable=False)
    village_y = db.Column(db.Integer, nullable=False)
    village_name = db.Column(db.Text)
    player_discord_id = db.Column(db.Text, nullable=False)
    player_name = db.Column(db.Text)
    troops = db.Column(db.Text, nullable=False)  # JSON {"unit": count}
    crop_consumption = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)


class TroopSupport(db.Model):
    """Support troops sent between villages."""

    __tablename__ = "troop_support"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    from_x = db.Column(db.Integer, nullable=False)
    from_y = db.Column(db.Integer, nullable=False)
    to_x = db.Column(db.Integer, nullable=False)
    to_y = db.Column(db.Integer, nullable=False)
    player_discord_id = db.Column(db.Text, nullable=False)
    player_name = db.Column(db.Text)
    troops = db.Column(db.Text, nullable=False)  # JSON
    crop_consumption = db.Column(db.Integer)
    travel_time_seconds = db.Column(db.Integer)
    attack_report_id = db.Column(db.Integer, nullable=True)
    forum_thread_id = db.Column(db.BigInteger, nullable=True)
    status = db.Column(db.Text, default="in_transit")  # in_transit / arrived / recalled
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)


class BattleReport(db.Model):
    """Parsed battle report from game."""

    __tablename__ = "battle_reports"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    attack_report_id = db.Column(db.Integer, nullable=True)
    forum_thread_id = db.Column(db.BigInteger, nullable=True)
    attacker_name = db.Column(db.Text)
    attacker_alliance = db.Column(db.Text)
    attacker_village = db.Column(db.Text)
    attacker_troops = db.Column(db.Text)  # JSON
    attacker_losses = db.Column(db.Text)  # JSON
    attacker_trapped = db.Column(db.Text)  # JSON (optional)
    defender_name = db.Column(db.Text)
    defender_alliance = db.Column(db.Text)
    defender_village = db.Column(db.Text)
    defender_troops = db.Column(db.Text)  # JSON
    defender_losses = db.Column(db.Text)  # JSON
    bounty = db.Column(db.Text)  # JSON
    battle_power_atk = db.Column(db.Integer)
    battle_power_def = db.Column(db.Integer)
    raw_text = db.Column(db.Text)
    result = db.Column(db.Text)  # wygrana_obrony / przegrana_obrony / remis / szpieg
    is_manual = db.Column(db.Boolean, default=False)
    reported_by_discord = db.Column(db.Text)
    reported_by_name = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=_utcnow)


class Alert(db.Model):
    """Alerty generowane po porównaniu snapshotów map.sql."""

    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    snapshot_id = db.Column(db.Integer, db.ForeignKey("snapshots.id"))
    alert_type = db.Column(db.Text)  # pop_drop, new_village, alliance_change
    data = db.Column(db.Text)  # JSON with details
    notified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow)


class MonitorSettings(db.Model):
    """User preferences for personal monitoring."""

    __tablename__ = "monitor_settings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    discord_id = db.Column(db.BigInteger, unique=True, nullable=False)
    enabled = db.Column(db.Boolean, default=True)
    pop_drop_threshold = db.Column(db.Integer, default=50)
    neighbor_radius = db.Column(db.Integer, default=15)
    enemy_radius = db.Column(db.Integer, default=20)
    last_checked_snapshot_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)


class PersonalAlert(db.Model):
    """Personal notification preferences and history for linked users."""

    __tablename__ = "personal_alerts"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    discord_id = db.Column(db.BigInteger, nullable=False, index=True)
    snapshot_id = db.Column(db.Integer, nullable=True)
    alert_type = db.Column(db.Text, nullable=False)
    # Types: pop_drop, new_neighbor, enemy_nearby
    data = db.Column(db.Text)  # JSON with details
    notified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow)


class DefenseThread(db.Model):
    """Thread-level state for defense coordination on Discord forum."""

    __tablename__ = "defense_threads"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    forum_thread_id = db.Column(db.BigInteger, unique=True, nullable=False)
    defender_x = db.Column(db.Integer, nullable=False)
    defender_y = db.Column(db.Integer, nullable=False)
    defender_village = db.Column(db.Text)
    defender_player = db.Column(db.Text)
    wall_level = db.Column(db.Integer, nullable=True)
    crop_amount = db.Column(db.Integer, nullable=True)
    crop_production = db.Column(db.Integer, nullable=True)
    status = db.Column(db.Text, default="active")  # active / resolved
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
