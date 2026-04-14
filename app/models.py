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
    tid = db.Column(db.Integer)  # tribe: 1=Romans, 3=Gauls, 6=Egyptians, 7=Huns, 8=Spartans, 9=Vikings
    vid = db.Column(db.Integer)  # village id
    name = db.Column(db.Text)
    uid = db.Column(db.Integer)  # player id
    player_name = db.Column(db.Text)
    aid = db.Column(db.Integer)  # alliance id
    alliance_name = db.Column(db.Text)
    population = db.Column(db.Integer)
    # RoF extended fields (NULL on classic servers)
    region = db.Column(db.Text, nullable=True)
    is_capital = db.Column(db.Boolean, nullable=True)
    is_city = db.Column(db.Boolean, nullable=True)
    has_harbor = db.Column(db.Boolean, nullable=True)
    victory_points = db.Column(db.Integer, nullable=True)

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
    auto_resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)


from bot.tribes import TRIBES
TRIBE_NAMES = {t.tid: t.name_pl for t in TRIBES.values()}


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
    kill_cost_atk = db.Column(db.Text, nullable=True)  # JSON {resource: amount}
    kill_cost_def = db.Column(db.Text, nullable=True)  # JSON {resource: amount}
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
    discord_eligible = db.Column(db.Boolean, default=True)
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


class SpyReport(db.Model):
    """Spy report parsed from Travian via Chrome extension."""

    __tablename__ = "spy_reports"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    snapshot_id = db.Column(db.Integer, db.ForeignKey("snapshots.id"), nullable=True)
    spy_type = db.Column(db.Text, nullable=False)  # resources / troops / both
    target_player = db.Column(db.Text)
    target_village = db.Column(db.Text)
    target_x = db.Column(db.Integer, nullable=False)
    target_y = db.Column(db.Integer, nullable=False)
    resources_lumber = db.Column(db.Integer, nullable=True)
    resources_clay = db.Column(db.Integer, nullable=True)
    resources_iron = db.Column(db.Integer, nullable=True)
    resources_crop = db.Column(db.Integer, nullable=True)
    troops = db.Column(db.Text, nullable=True)  # JSON {"unit_name": count}
    defense_buildings = db.Column(db.Text, nullable=True)  # JSON {"wall": 10, ...}
    submitted_by = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=_utcnow)

    __table_args__ = (
        db.Index("ix_spy_reports_target", "target_x", "target_y"),
    )


class DiplomaticRelation(db.Model):
    """Diplomatic relation with another alliance (ally, pact, nap, war)."""

    __tablename__ = "diplomatic_relations"

    id = db.Column(db.Integer, primary_key=True)
    relation_type = db.Column(db.String(20), nullable=False)
    target_alliance_id = db.Column(db.Integer, nullable=False)
    target_alliance_name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    created_by = db.Column(db.String(100))
    notes = db.Column(db.Text, nullable=True)
    active = db.Column(db.Boolean, default=True)


class GameData(db.Model):
    """Generic game data captured by Chrome extension (hero, marketplace, training, etc.)."""

    __tablename__ = "game_data"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    data_type = db.Column(db.Text, nullable=False)  # hero / marketplace / training
    data = db.Column(db.Text, nullable=False)  # JSON payload
    server_url = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, default=_utcnow)

    __table_args__ = (
        db.Index("ix_game_data_type", "data_type"),
    )
