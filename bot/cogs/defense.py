"""Obrona i śledzenie wojsk — /traport, /twojska, /twsparcie (Defense system).

Battle report parser, troop registration, support tracking.
All DB access through db_query() for async safety.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands

from bot.bot import db_query
from bot.utils import (
    CROP_BY_NAME,
    COLOR_ATTACK, COLOR_INFO, COLOR_SUCCESS, FOOTER,
    HERO_CROP, TRIBE_EMOJI, TRIBE_NAMES,
    calc_crop_consumption, coords_display, normalize_unit_name,
    parse_coords, torus_distance, travel_time_str,
)

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Unit order in battle reports (per tribe, matches game output)
# ------------------------------------------------------------------ #
REPORT_UNIT_ORDER: dict[int, list[str]] = {
    1: [  # Romans
        "Legionista", "Pretorianin", "Imperians",
        "Equites Legati", "Equites Imperatoris", "Equites Caesaris",
        "Taran", "Katapulta ognista", "Senator", "Osadnik",
    ],
    2: [  # Teutons
        "Pałkarz", "Włócznik", "Topornik",
        "Zwiadowca", "Paladyn", "Germański rycerz",
        "Taran", "Katapulta", "Wódz", "Osadnik",
    ],
    3: [  # Gauls
        "Falangita", "Miecznik", "Tropiciel",
        "Grom Teutatesa", "Jeździec druidzki", "Haeduan",
        "Taran", "Trebusz", "Wódz", "Osadnik",
    ],
    6: [  # Egyptians
        "Slave Militia", "Ash Warden", "Khopesh Warrior",
        "Sopdu Explorer", "Anhur Guard", "Resheph Chariot",
        "Ram", "Catapult", "Nomarch", "Settler",
    ],
    7: [  # Huns
        "Mercenary", "Bowman", "Spotter",
        "Steppe Rider", "Marksman", "Marauder",
        "Ram", "Catapult", "Logades", "Settler",
    ],
    8: [  # Vikings
        "Thrall", "Shield Maiden", "Berserker",
        "Heimdall's Eye", "Huskarl Rider", "Valkyrie's Blessing",
        "Ram", "Catapult", "Jarl", "Settler",
    ],
    9: [  # Spartans
        "Hoplite", "Sentinel", "Shieldsman",
        "Twinsteel Therion", "Elpida Rider", "Corinthian Crusher",
        "Ram", "Catapult", "Ephor", "Settler",
    ],
}

# Map any recognized unit name to a tribe_id for auto-detection
_UNIT_TO_TRIBE: dict[str, int] = {}
for _tid, _names in REPORT_UNIT_ORDER.items():
    for _n in _names:
        if _n not in ("Taran", "Osadnik", "Ram", "Catapult", "Settler"):  # shared across tribes
            _UNIT_TO_TRIBE[_n] = _tid


# ------------------------------------------------------------------ #
# Battle Report Parser (state machine)
# ------------------------------------------------------------------ #
class ReportParseError(Exception):
    """Raised when a report cannot be parsed."""


def _parse_side(lines: list[str], start_idx: int) -> tuple[dict, int]:
    """Parse attacker or defender side from report lines.

    Returns (side_dict, next_line_index).
    side_dict keys: alliance, player, village, unit_names, troops, losses, trapped
    """
    side: dict = {}
    i = start_idx

    # First line: [Alliance] Player z osady Village
    header = lines[i].strip()
    alliance_m = re.match(r"\[([^\]]*)\]\s*(.+)", header)
    if alliance_m:
        side["alliance"] = alliance_m.group(1)
        rest = alliance_m.group(2)
    else:
        side["alliance"] = None
        rest = header

    village_m = re.search(r"z osady\s+(.+)", rest)
    if village_m:
        side["player"] = rest[:village_m.start()].strip()
        side["village"] = village_m.group(1).strip()
    else:
        side["player"] = rest.strip()
        side["village"] = None
    i += 1

    # Unit names line (tab-separated)
    if i >= len(lines):
        raise ReportParseError("Brak wiersza z nazwami jednostek")
    raw_names = lines[i].strip().split("\t")
    unit_names = []
    for rn in raw_names:
        canonical = normalize_unit_name(rn.strip())
        if canonical:
            unit_names.append(canonical)
        elif rn.strip():
            unit_names.append(rn.strip())  # keep unknown names as-is
    side["unit_names"] = unit_names
    i += 1

    # Troop count line(s): numbers tab-separated
    # Could be: troops_sent, losses, [trapped]
    def _parse_nums(line: str) -> list[int]:
        parts = line.strip().split("\t")
        nums = []
        for p in parts:
            p = p.strip()
            if p == "" or p == "-":
                nums.append(0)
            else:
                # Strip thousands separators: "1.500" or "1 500" → "1500"
                cleaned = re.sub(r'[\s.]', '', p)
                try:
                    nums.append(int(cleaned))
                except ValueError:
                    log.warning("Nie można sparsować liczby: %r (z %r)", p, line.strip())
                    nums.append(0)
        return nums

    # Troops sent
    if i >= len(lines):
        raise ReportParseError("Brak wiersza z liczbą wojsk")
    side["troops"] = _parse_nums(lines[i])
    i += 1

    # Losses
    if i < len(lines) and _looks_like_numbers(lines[i]):
        side["losses"] = _parse_nums(lines[i])
        i += 1
    else:
        side["losses"] = [0] * len(side["troops"])

    # Trapped (optional)
    if i < len(lines) and _looks_like_numbers(lines[i]):
        side["trapped"] = _parse_nums(lines[i])
        i += 1
    else:
        side["trapped"] = None

    return side, i


def _looks_like_numbers(line: str) -> bool:
    """Check if a line looks like tab-separated numbers (or dashes/empty)."""
    parts = line.strip().split("\t")
    if len(parts) < 2:
        return False
    num_count = 0
    for p in parts:
        p = p.strip()
        if p == "" or p == "-":
            num_count += 1
        elif re.match(r"^-?\d+$", p):
            num_count += 1
    return num_count >= len(parts) * 0.6


def parse_battle_report(raw: str) -> dict:
    """Parse a Travian battle report (Polish) into structured data.

    Returns dict with keys:
        title, date, attacker, defender, bounty, stats, raw_hash
    Each side has: alliance, player, village, unit_names, troops, losses, trapped
    """
    lines = raw.strip().split("\n")
    if len(lines) < 6:
        raise ReportParseError("Raport zbyt krótki — potrzeba minimum 6 linii")

    result = {"raw_hash": hashlib.sha256(raw.encode()).hexdigest()[:16]}

    i = 0
    # Title line: "Player verb Player"
    result["title"] = lines[i].strip()
    i += 1

    # Date line (optional — may contain DD.MM.YY, HH:MM:SS)
    if i < len(lines) and re.match(r"\d{2}\.\d{2}\.\d{2}", lines[i].strip()):
        result["date"] = lines[i].strip()
        i += 1

    # Look for "Napastnik" section
    while i < len(lines) and "Napastnik" not in lines[i]:
        i += 1
    if i >= len(lines):
        raise ReportParseError("Nie znaleziono sekcji 'Napastnik'")
    i += 1  # skip the "Napastnik" label

    attacker, i = _parse_side(lines, i)
    result["attacker"] = attacker

    # Look for bounty "zdobycz" line (optional)
    bounty = None
    while i < len(lines):
        line = lines[i].strip().lower()
        if line.startswith("zdobycz"):
            parts = lines[i].strip().split("\t")
            if len(parts) >= 5:
                try:
                    bounty = {
                        "wood": int(parts[1]) if len(parts) > 1 else 0,
                        "clay": int(parts[2]) if len(parts) > 2 else 0,
                        "iron": int(parts[3]) if len(parts) > 3 else 0,
                        "crop": parts[4] if len(parts) > 4 else "0",
                    }
                except ValueError:
                    bounty = None
            i += 1
            break
        if "Obrońca" in line or "obrońca" in line:
            break
        i += 1
    result["bounty"] = bounty

    # Look for "Obrońca" section
    while i < len(lines):
        if "Obrońca" in lines[i] or "obrońca" in lines[i]:
            i += 1
            break
        i += 1

    # Defender (optional — some reports don't have defenders)
    if i < len(lines) and not lines[i].strip().lower().startswith("statystyki"):
        try:
            defender, i = _parse_side(lines, i)
            result["defender"] = defender
        except ReportParseError:
            result["defender"] = None
    else:
        result["defender"] = None

    # Statistics section (optional)
    stats = {}
    kill_cost_atk = {}
    kill_cost_def = {}
    in_kill_cost = False

    while i < len(lines):
        line = lines[i].strip()

        if re.match(r'(?i)^koszt\s+zabitych', line):
            in_kill_cost = True
            i += 1
            continue

        if in_kill_cost:
            if not line:
                in_kill_cost = False
                i += 1
                continue
            parts = [p.strip() for p in line.split('\t') if p.strip()]
            if len(parts) >= 2:
                try:
                    kill_cost_atk[parts[0]] = int(re.sub(r'[\s.]', '', parts[1]))
                except (ValueError, IndexError):
                    pass
            if len(parts) >= 4:
                try:
                    kill_cost_def[parts[2]] = int(re.sub(r'[\s.]', '', parts[3]))
                except (ValueError, IndexError):
                    pass
            i += 1
            continue

        if "Siła w walce" in line or "siła" in line.lower():
            parts = line.split("\t")
            if len(parts) >= 3:
                try:
                    stats["power_atk"] = int(parts[1])
                    stats["power_def"] = int(parts[2])
                except (ValueError, IndexError):
                    pass
        elif "Utrzymanie" in line or "utrzymanie" in line:
            parts = line.split("\t")
            if len(parts) >= 3:
                try:
                    stats["maintenance_atk"] = int(parts[1])
                    stats["maintenance_def"] = int(parts[2])
                except (ValueError, IndexError):
                    pass
        i += 1
    result["stats"] = stats
    result["kill_cost_atk"] = kill_cost_atk if kill_cost_atk else None
    result["kill_cost_def"] = kill_cost_def if kill_cost_def else None

    return result


# ------------------------------------------------------------------ #
# Smart Report Parser — multi-strategy wrapper
# ------------------------------------------------------------------ #

def _validate_parse_quality(result: dict) -> bool:
    """Check if a parse result has recognizable unit names.

    Returns True if at least one unit name across attacker/defender is
    a known Travian unit AND no unit names contain suspicious internal
    whitespace (indicating merged columns). Catches cases where
    parse_battle_report silently produces garbage.
    """
    has_recognized = False
    for side_key in ("attacker", "defender"):
        side = result.get(side_key)
        if side is None:
            continue
        for name in side.get("unit_names", []):
            # Merged columns produce names like "Topornik   Zwiadowca"
            if re.search(r'  +', name):
                return False
            if normalize_unit_name(name):
                has_recognized = True
    return has_recognized


def smart_parse_report(raw: str) -> dict:
    """Try multiple parsing strategies for battle reports.

    Strategies tried in order:
    1. Standard tab-separated (existing parse_battle_report)
    2. Space/mixed-separator format (normalize only tabular rows)
    3. Condensed key:value format

    Always computes raw_hash from original input for consistent dedup.
    """
    errors = []
    original_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]

    # Strategy 1: existing parser as-is
    try:
        result = parse_battle_report(raw)
        if _validate_parse_quality(result):
            result["raw_hash"] = original_hash
            return result
        errors.append("standard: brak rozpoznanych jednostek")
    except ReportParseError as e:
        errors.append(f"standard: {e}")

    # Strategy 2: normalize whitespace in tabular rows and retry
    cleaned = _normalize_tabular_whitespace(raw)
    if cleaned != raw:
        try:
            result = parse_battle_report(cleaned)
            if _validate_parse_quality(result):
                result["raw_hash"] = original_hash
                return result
            errors.append("normalized: brak rozpoznanych jednostek")
        except ReportParseError as e:
            errors.append(f"normalized: {e}")

    # Strategy 3: condensed format (Unit: count)
    try:
        result = _parse_condensed_report(raw)
        result["raw_hash"] = original_hash
        return result
    except ReportParseError as e:
        errors.append(f"condensed: {e}")

    raise ReportParseError(
        f"Nie udało się sparsować raportu. Próbowano {len(errors)} metod."
    )


def _normalize_tabular_whitespace(raw: str) -> str:
    """Normalize whitespace in tabular rows only (unit names + numbers).

    Leaves non-tabular lines (title, headers, player names) intact.
    Only collapses 2+ spaces to tabs — single spaces within numbers
    like '1 500' are preserved.
    """
    lines = raw.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        # Heuristic: tabular rows have multiple columns separated by 2+ spaces
        # or mixed spaces/tabs. Detect by presence of 2+ whitespace groups.
        if re.search(r'[\t]', stripped) or re.search(r'  +', stripped):
            # Check if it looks like a data row (units or numbers)
            parts = re.split(r'[ \t]{2,}', stripped)
            if len(parts) >= 2:
                # Check if parts are mostly numbers or known unit names
                num_count = sum(
                    1 for p in parts
                    if re.match(r'^-?\d[\d\s.]*$', p.strip()) or p.strip() in ('-', '')
                )
                name_count = sum(
                    1 for p in parts if normalize_unit_name(p.strip())
                )
                if num_count >= len(parts) * 0.5 or name_count >= len(parts) * 0.3:
                    result.append("\t".join(p.strip() for p in parts))
                    continue
        result.append(line)
    return "\n".join(result)


def _parse_condensed_report(raw: str) -> dict:
    """Parse condensed format: 'Unit: count, Unit2: count2'.

    Handles formats like:
        Napastnik: Player [Alliance] z wioski Village (x|y)
        Legionista: 100, Pretorianin: 50
        Straty: Legionista: 0, Pretorianin: 10
    """
    lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        raise ReportParseError("Raport skondensowany zbyt krótki")

    result: dict = {
        "title": lines[0],
        "raw_hash": "",  # overwritten by smart_parse_report
        "bounty": None,
        "stats": {},
    }

    # Find section markers
    atk_idx = None
    def_idx = None
    for i, line in enumerate(lines):
        low = line.lower()
        if low.startswith("napastnik") and atk_idx is None:
            atk_idx = i
        elif ("obrońca" in low or "obronca" in low) and def_idx is None:
            def_idx = i

    if atk_idx is None:
        raise ReportParseError("Brak sekcji 'Napastnik' w formacie skondensowanym")

    # Parse attacker section
    atk_end = def_idx if def_idx is not None else len(lines)
    result["attacker"] = _parse_condensed_side(lines[atk_idx:atk_end])

    # Parse defender section (optional)
    if def_idx is not None:
        try:
            result["defender"] = _parse_condensed_side(lines[def_idx:])
        except ReportParseError:
            result["defender"] = None
    else:
        result["defender"] = None

    return result


def _parse_condensed_side(lines: list[str]) -> dict:
    """Parse a single side from condensed format lines.

    First line: section header (may contain player/alliance info)
    Subsequent lines: 'Unit: count' pairs or 'Straty: Unit: count' pairs
    """
    if not lines:
        raise ReportParseError("Brak danych strony w formacie skondensowanym")

    side: dict = {"alliance": None, "player": None, "village": None}

    # Parse header line: "Napastnik: Player [Alliance] z wioski Village (x|y)"
    # or just "Napastnik" / "Obrońca"
    header = lines[0]
    header_content = re.sub(r'^(?:Napastnik|Obrońca|Obronca)\s*:?\s*', '', header, flags=re.IGNORECASE)

    if header_content:
        # Extract alliance
        alliance_m = re.search(r'\[([^\]]+)\]', header_content)
        if alliance_m:
            side["alliance"] = alliance_m.group(1)
            header_content = header_content[:alliance_m.start()] + header_content[alliance_m.end():]

        # Extract village: "z wioski Village" or "z osady Village"
        village_m = re.search(r'z (?:wioski|osady)\s+(.+?)(?:\s*\(\d+\|\d+\))?$', header_content)
        if village_m:
            side["village"] = village_m.group(1).strip()
            header_content = header_content[:village_m.start()]

        side["player"] = header_content.strip() or None

    # Parse unit lines
    unit_names = []
    troops = []
    losses = []

    for line in lines[1:]:
        is_loss = False
        content = line
        if re.match(r'(?i)^straty\s*:', content):
            is_loss = True
            content = re.sub(r'(?i)^straty\s*:\s*', '', content)

        # Parse "Unit: count" pairs (comma or semicolon separated)
        pairs = re.findall(r'([A-Za-zĄąĆćĘęŁłŃńÓóŚśŹźŻż\s]+?)\s*:\s*(\d[\d\s.]*)', content)
        for name_raw, count_raw in pairs:
            canonical = normalize_unit_name(name_raw.strip())
            if not canonical:
                continue
            count_clean = re.sub(r'[\s.]', '', count_raw)
            try:
                count = int(count_clean)
            except ValueError:
                continue

            if is_loss:
                # Find matching unit or append
                if canonical in unit_names:
                    idx = unit_names.index(canonical)
                    losses[idx] = count
                else:
                    unit_names.append(canonical)
                    troops.append(0)
                    losses.append(count)
            else:
                if canonical in unit_names:
                    idx = unit_names.index(canonical)
                    troops[idx] += count
                else:
                    unit_names.append(canonical)
                    troops.append(count)
                    losses.append(0)

    if not unit_names:
        raise ReportParseError("Nie znaleziono jednostek w formacie skondensowanym")

    side["unit_names"] = unit_names
    side["troops"] = troops
    side["losses"] = losses
    side["trapped"] = None

    return side


def _side_to_dict(side: dict) -> dict[str, int]:
    """Convert parsed side troops to {canonical_name: count}."""
    troops = {}
    names = side.get("unit_names", [])
    counts = side.get("troops", [])
    for j, name in enumerate(names):
        count = counts[j] if j < len(counts) else 0
        if count > 0:
            troops[name] = count
    return troops


def _side_losses_dict(side: dict) -> dict[str, int]:
    """Convert parsed side losses to {canonical_name: count}."""
    losses = {}
    names = side.get("unit_names", [])
    counts = side.get("losses", [])
    for j, name in enumerate(names):
        count = counts[j] if j < len(counts) else 0
        if count > 0:
            losses[name] = count
    return losses


def _side_trapped_dict(side: dict) -> dict[str, int] | None:
    """Convert parsed side trapped to {canonical_name: count}."""
    if not side.get("trapped"):
        return None
    trapped = {}
    names = side.get("unit_names", [])
    counts = side["trapped"]
    for j, name in enumerate(names):
        count = counts[j] if j < len(counts) else 0
        if count > 0:
            trapped[name] = count
    return trapped or None


# ------------------------------------------------------------------ #
# Troop list parser (from village overview)
# ------------------------------------------------------------------ #
def parse_troop_list(raw: str) -> dict[str, int]:
    """Parse troop list copied from village overview.

    Format: each line is 'UnitName\\tCount\\tUnitName' or 'UnitName\\tCount'
    Also handles single-column: 'UnitName Count' or 'UnitName: Count'
    Returns {canonical_name: count}.
    """
    troops: dict[str, int] = {}
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Tab-separated: Name\tCount\tName
        parts = line.split("\t")
        if len(parts) >= 2:
            name_raw = parts[0].strip()
            count_raw = parts[1].strip()
        else:
            # Try "Name Count" or "Name: Count"
            m = re.match(r"(.+?)\s*[:]\s*(\d+)", line)
            if not m:
                m = re.match(r"(.+?)\s+(\d+)\s*$", line)
            if m:
                name_raw = m.group(1).strip()
                count_raw = m.group(2).strip()
            else:
                continue

        canonical = normalize_unit_name(name_raw)
        if not canonical:
            log.warning("Nierozpoznana jednostka: '%s'", name_raw)
            continue
        try:
            # Strip thousands separators: "1.500" or "1 500" → "1500"
            count_clean = re.sub(r'[\s.]', '', count_raw)
            count = int(count_clean)
        except ValueError:
            log.warning("Nie można sparsować liczby: '%s' dla '%s'", count_raw, name_raw)
            continue
        if count > 0:
            troops[canonical] = troops.get(canonical, 0) + count

    return troops


# ------------------------------------------------------------------ #
# Discord Modals
# ------------------------------------------------------------------ #
class ReportModal(discord.ui.Modal):
    """Modal for pasting a battle report."""

    def __init__(self, bot, attack_id: int | None = None, thread_id: int | None = None):
        super().__init__(title="📋 Wklej raport bitewny")
        self.bot = bot
        self.attack_id = attack_id
        self.thread_id = thread_id

        self.report_input = discord.ui.InputText(
            label="Raport (skopiuj z gry i wklej)",
            style=discord.InputTextStyle.long,
            placeholder="Skopiuj cały raport z gry Travian i wklej tutaj...",
            required=True,
            max_length=4000,
        )
        self.add_item(self.report_input)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        raw = self.report_input.value

        try:
            parsed = smart_parse_report(raw)
        except ReportParseError as e:
            await interaction.followup.send(
                f"❌ Błąd parsowania raportu: {e}\n"
                "Upewnij się, że wklejasz cały raport skopiowany z gry.",
                ephemeral=True,
            )
            return

        # Check for duplicate
        raw_hash = parsed["raw_hash"]

        def _check_and_save():
            from app.database import db
            from app.models import BattleReport

            existing = BattleReport.query.filter_by(
                raw_text=raw_hash
            ).first()
            if existing:
                return None, "duplicate"

            atk = parsed.get("attacker", {})
            dfn = parsed.get("defender") or {}

            report = BattleReport(
                attack_report_id=self.attack_id,
                forum_thread_id=self.thread_id,
                attacker_name=atk.get("player"),
                attacker_alliance=atk.get("alliance"),
                attacker_village=atk.get("village"),
                attacker_troops=json.dumps(_side_to_dict(atk), ensure_ascii=False) if atk else None,
                attacker_losses=json.dumps(_side_losses_dict(atk), ensure_ascii=False) if atk else None,
                attacker_trapped=json.dumps(_side_trapped_dict(atk), ensure_ascii=False) if atk and _side_trapped_dict(atk) else None,
                defender_name=dfn.get("player"),
                defender_alliance=dfn.get("alliance"),
                defender_village=dfn.get("village"),
                defender_troops=json.dumps(_side_to_dict(dfn), ensure_ascii=False) if dfn else None,
                defender_losses=json.dumps(_side_losses_dict(dfn), ensure_ascii=False) if dfn else None,
                bounty=json.dumps(parsed.get("bounty"), ensure_ascii=False) if parsed.get("bounty") else None,
                kill_cost_atk=json.dumps(parsed.get("kill_cost_atk"), ensure_ascii=False) if parsed.get("kill_cost_atk") else None,
                kill_cost_def=json.dumps(parsed.get("kill_cost_def"), ensure_ascii=False) if parsed.get("kill_cost_def") else None,
                battle_power_atk=parsed.get("stats", {}).get("power_atk"),
                battle_power_def=parsed.get("stats", {}).get("power_def"),
                raw_text=raw_hash,
                reported_by_discord=str(interaction.user.id),
            )
            db.session.add(report)
            db.session.commit()
            return report.id, "ok"

        report_id, status = await db_query(self.bot, _check_and_save)

        if status == "duplicate":
            await interaction.followup.send(
                "⚠️ Ten raport został już wcześniej dodany.", ephemeral=True,
            )
            return

        embed = _build_report_embed(parsed, report_id, self.attack_id)

        # Post in thread if available
        if self.thread_id:
            try:
                thread = await self.bot.fetch_channel(self.thread_id)
                await thread.send(embed=embed)
            except Exception:
                log.exception("Nie udało się wysłać raportu do wątku %s", self.thread_id)

        await interaction.followup.send(
            f"✅ Raport **#{report_id}** zapisany!" + (
                f" (wątek zaktualizowany)" if self.thread_id else ""
            ),
            embed=embed,
        )


class TroopsModal(discord.ui.Modal):
    """Modal for registering village troops."""

    def __init__(self, bot, village_coords: str):
        super().__init__(title="🛡️ Zarejestruj wojska w wiosce")
        self.bot = bot
        self.village_coords = village_coords

        self.troops_input = discord.ui.InputText(
            label="Wojska (skopiuj z gry)",
            style=discord.InputTextStyle.long,
            placeholder="Falangi\t510\tFalangi\nMiecznicy\t200\tMiecznicy\n...",
            required=True,
            max_length=2000,
        )
        self.add_item(self.troops_input)

        self.hero_input = discord.ui.InputText(
            label="Bohater w wiosce? (tak/nie)",
            style=discord.InputTextStyle.short,
            placeholder="tak",
            required=False,
            max_length=10,
        )
        self.add_item(self.hero_input)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        raw = self.troops_input.value

        troops = parse_troop_list(raw)
        if not troops:
            await interaction.followup.send(
                "❌ Nie rozpoznano żadnych jednostek. Sprawdź format.",
                ephemeral=True,
            )
            return

        hero_text = (self.hero_input.value or "").strip().lower()
        has_hero = hero_text in ("tak", "t", "yes", "y", "1")
        if has_hero:
            troops["Bohater"] = 1

        x, y = parse_coords(self.village_coords)
        crop = calc_crop_consumption(troops)

        def _save():
            from app.database import db
            from app.models import VillageTroops

            # Upsert: replace existing entry for same village + player
            existing = VillageTroops.query.filter_by(
                village_x=x, village_y=y,
                player_discord_id=str(interaction.user.id),
            ).first()
            if existing:
                existing.troops = json.dumps(troops, ensure_ascii=False)
                existing.crop_consumption = crop
                existing.updated_at = datetime.now(timezone.utc)
                db.session.commit()
                return existing.id, "updated"
            else:
                vt = VillageTroops(
                    village_x=x, village_y=y,
                    player_discord_id=str(interaction.user.id),
                    player_name=str(interaction.user),
                    troops=json.dumps(troops, ensure_ascii=False),
                    crop_consumption=crop,
                )
                db.session.add(vt)
                db.session.commit()
                return vt.id, "created"

        vt_id, status_text = await db_query(self.bot, _save)

        troop_lines = [f"  {name}: **{count}**" for name, count in troops.items()]
        embed = discord.Embed(
            title=f"🛡️ Wojska w ({x}|{y})",
            description="\n".join(troop_lines),
            color=COLOR_INFO,
        )
        embed.add_field(
            name="🌾 Zużycie zboża",
            value=f"**{crop}** zboża/h",
            inline=True,
        )
        status_msg = "zaktualizowane" if status_text == "updated" else "zarejestrowane"
        embed.set_footer(text=f"{FOOTER} | Wojska {status_msg}")

        await interaction.followup.send(
            f"✅ Wojska {status_msg} (ID: #{vt_id})", embed=embed,
        )

        # Update thread summary if there's an active defense thread for this village
        def _find_thread():
            from app.models import DefenseThread
            dt = DefenseThread.query.filter_by(
                defender_x=x, defender_y=y, status="active",
            ).order_by(DefenseThread.id.desc()).first()
            return dt.forum_thread_id if dt else None

        thread_id = await db_query(self.bot, _find_thread)
        if thread_id:
            attacks_cog = self.bot.get_cog("Attacks")
            if attacks_cog:
                update_fn = getattr(attacks_cog, "_update_thread_summary", None)
                if update_fn:
                    await update_fn(thread_id)
                else:
                    log.error("Attacks cog nie ma _update_thread_summary — pominięto odświeżenie")
            else:
                log.warning("Attacks cog nie załadowany — nie można odświeżyć summary")


class SupportModal(discord.ui.Modal):
    """Modal for registering support sent to a village."""

    def __init__(self, bot, from_coords: str, to_coords: str, attack_id: int | None = None):
        super().__init__(title="📤 Zarejestruj wsparcie")
        self.bot = bot
        self.from_coords = from_coords
        self.to_coords = to_coords
        self.attack_id = attack_id

        self.troops_input = discord.ui.InputText(
            label="Wysyłane wojska (skopiuj z gry lub wpisz)",
            style=discord.InputTextStyle.long,
            placeholder="Falangi\t200\tFalangi\nMiecznicy\t100\tMiecznicy",
            required=True,
            max_length=2000,
        )
        self.add_item(self.troops_input)

        self.hero_input = discord.ui.InputText(
            label="Bohater w wysyłce? (tak/nie)",
            style=discord.InputTextStyle.short,
            placeholder="nie",
            required=False,
            max_length=10,
        )
        self.add_item(self.hero_input)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        raw = self.troops_input.value

        troops = parse_troop_list(raw)
        if not troops:
            await interaction.followup.send(
                "❌ Nie rozpoznano żadnych jednostek.", ephemeral=True,
            )
            return

        hero_text = (self.hero_input.value or "").strip().lower()
        if hero_text in ("tak", "t", "yes", "y", "1"):
            troops["Bohater"] = 1

        from_x, from_y = parse_coords(self.from_coords)
        to_x, to_y = parse_coords(self.to_coords)
        crop = calc_crop_consumption(troops)
        dist = torus_distance(from_x, from_y, to_x, to_y)

        def _save():
            from app.database import db
            from app.models import TroopSupport, AttackReport, DefenseThread

            thread_id = None
            if self.attack_id:
                atk = AttackReport.query.get(self.attack_id)
                if atk:
                    thread_id = atk.forum_thread_id

            # Fallback: find active defense thread by target coordinates
            if not thread_id:
                dt = DefenseThread.query.filter_by(
                    defender_x=to_x, defender_y=to_y, status="active",
                ).order_by(DefenseThread.id.desc()).first()
                if dt:
                    thread_id = dt.forum_thread_id

            ts = TroopSupport(
                from_x=from_x, from_y=from_y,
                to_x=to_x, to_y=to_y,
                player_discord_id=str(interaction.user.id),
                player_name=str(interaction.user),
                troops=json.dumps(troops, ensure_ascii=False),
                crop_consumption=crop,
                attack_report_id=self.attack_id,
                forum_thread_id=thread_id,
                status="in_transit",
            )
            db.session.add(ts)
            db.session.commit()
            return ts.id, thread_id

        support_id, thread_id = await db_query(self.bot, _save)

        troop_lines = [f"  {name}: **{count}**" for name, count in troops.items()]
        embed = discord.Embed(
            title="📤 Wsparcie wysłane!",
            description="\n".join(troop_lines),
            color=COLOR_SUCCESS,
        )
        embed.add_field(
            name="📍 Trasa",
            value=f"({from_x}|{from_y}) → ({to_x}|{to_y}) | 📏 {dist:.2f} pól",
            inline=False,
        )
        embed.add_field(
            name="🌾 Zużycie zboża",
            value=f"**{crop}** zboża/h",
            inline=True,
        )
        embed.set_footer(text=FOOTER)

        # Avoid duplicate: if interaction is inside the thread, followup IS the thread post
        in_thread = thread_id and interaction.channel_id == thread_id

        if thread_id and not in_thread:
            try:
                thread = await self.bot.fetch_channel(thread_id)
                await thread.send(
                    content=f"📤 **Wsparcie #{support_id}** od {interaction.user.display_name}",
                    embed=embed,
                )
            except Exception:
                log.exception("Nie udało się wysłać wsparcia do wątku %s", thread_id)

        if in_thread:
            await interaction.followup.send(
                content=f"📤 **Wsparcie #{support_id}** od {interaction.user.display_name}",
                embed=embed,
            )
        else:
            await interaction.followup.send(
                f"✅ Wsparcie **#{support_id}** zarejestrowane!", embed=embed,
                ephemeral=True,
            )

        # Update thread summary with new support data
        if thread_id:
            attacks_cog = self.bot.get_cog("Attacks")
            if attacks_cog:
                update_fn = getattr(attacks_cog, "_update_thread_summary", None)
                if update_fn:
                    await update_fn(thread_id)
                else:
                    log.error("Attacks cog nie ma _update_thread_summary — pominięto odświeżenie")
            else:
                log.warning("Attacks cog nie załadowany — nie można odświeżyć summary")


# ------------------------------------------------------------------ #
# Helper: build embed from parsed report
# ------------------------------------------------------------------ #
def _build_report_embed(parsed: dict, report_id: int, attack_id: int | None) -> discord.Embed:
    """Build a rich embed from a parsed battle report."""
    title = parsed.get("title", "Raport bitewny")
    date = parsed.get("date", "")

    embed = discord.Embed(
        title=f"📋 Raport #{report_id}" + (f" (atak #{attack_id})" if attack_id else ""),
        description=f"**{title}**" + (f"\n📅 {date}" if date else ""),
        color=COLOR_ATTACK,
    )

    # Attacker side
    atk = parsed.get("attacker", {})
    if atk:
        atk_troops = _side_to_dict(atk)
        atk_losses = _side_losses_dict(atk)
        atk_trapped = _side_trapped_dict(atk)

        atk_text = ""
        if atk.get("alliance", "").strip():
            atk_text += f"[{atk['alliance']}] "
        atk_text += f"**{atk.get('player', '?')}**"
        if atk.get("village"):
            atk_text += f" z **{atk['village']}**"

        troop_lines = []
        for name, count in atk_troops.items():
            loss = atk_losses.get(name, 0)
            trap = atk_trapped.get(name, 0) if atk_trapped else 0
            line = f"{name}: {count}"
            extras = []
            if loss > 0:
                extras.append(f"💀{loss}")
            if trap > 0:
                extras.append(f"🪤{trap}")
            if extras:
                line += f" ({', '.join(extras)})"
            troop_lines.append(line)
        atk_text += "\n" + "\n".join(troop_lines)

        crop = calc_crop_consumption(atk_troops)
        atk_text += f"\n🌾 Utrzymanie: **{crop}/h**"

        embed.add_field(name="⚔️ Napastnik", value=atk_text[:1024], inline=False)

    # Defender side
    dfn = parsed.get("defender")
    if dfn:
        dfn_troops = _side_to_dict(dfn)
        dfn_losses = _side_losses_dict(dfn)

        dfn_text = ""
        if dfn.get("alliance", "").strip():
            dfn_text += f"[{dfn['alliance']}] "
        dfn_text += f"**{dfn.get('player', '?')}**"
        if dfn.get("village"):
            dfn_text += f" z **{dfn['village']}**"

        troop_lines = []
        for name, count in dfn_troops.items():
            loss = dfn_losses.get(name, 0)
            line = f"{name}: {count}"
            if loss > 0:
                line += f" (💀{loss})"
            troop_lines.append(line)
        dfn_text += "\n" + "\n".join(troop_lines)

        crop = calc_crop_consumption(dfn_troops)
        dfn_text += f"\n🌾 Utrzymanie: **{crop}/h**"

        embed.add_field(name="🛡️ Obrońca", value=dfn_text[:1024], inline=False)

    # Bounty
    bounty = parsed.get("bounty")
    if bounty:
        embed.add_field(
            name="💰 Zdobycz",
            value=(
                f"🪵 {bounty.get('wood', 0):,} | "
                f"🧱 {bounty.get('clay', 0):,} | "
                f"⚙️ {bounty.get('iron', 0):,} | "
                f"🌾 {bounty.get('crop', 0)}"
            ),
            inline=False,
        )

    # Kill cost
    kill_cost_atk = parsed.get("kill_cost_atk")
    kill_cost_def = parsed.get("kill_cost_def")
    if kill_cost_atk or kill_cost_def:
        kc_text = ""
        if kill_cost_atk:
            kc_text += "⚔️ **Napastnik:**\n"
            for res, amount in kill_cost_atk.items():
                kc_text += f"  {res}: {amount:,}\n"
        if kill_cost_def:
            kc_text += "🛡️ **Obrońca:**\n"
            for res, amount in kill_cost_def.items():
                kc_text += f"  {res}: {amount:,}\n"
        embed.add_field(name="💀 Koszt zabitych", value=kc_text[:1024], inline=False)

    # Stats
    stats = parsed.get("stats", {})
    if stats.get("power_atk") or stats.get("power_def"):
        embed.add_field(
            name="📊 Statystyki",
            value=(
                f"Siła: ⚔️ {stats.get('power_atk', '?'):,} vs 🛡️ {stats.get('power_def', '?'):,}"
            ),
            inline=False,
        )

    embed.set_footer(text=FOOTER)
    return embed


# ------------------------------------------------------------------ #
# Cog
# ------------------------------------------------------------------ #
class Defense(commands.Cog):
    """System obrony — raporty, wojska, wsparcie."""

    def __init__(self, bot):
        self.bot = bot

    def _server_url(self) -> str:
        return self.bot.flask_app.config.get(
            "TRAVIAN_SERVER_URL", "https://ts31.x3.europe.travian.com"
        )

    async def _detect_thread_coords(self, channel_id: int):
        """Auto-detect village coords from a defense thread channel ID."""
        def _query():
            from app.models import DefenseThread
            dt = DefenseThread.query.filter_by(
                forum_thread_id=channel_id, status="active",
            ).first()
            if dt:
                return (dt.defender_x, dt.defender_y)
            return None
        return await db_query(self.bot, _query)

    # ------------------------------------------------------------------ #
    # /traport — paste battle report
    # ------------------------------------------------------------------ #
    @discord.slash_command(name="traport", description="Wklej raport bitewny z gry")
    @discord.option(
        "atak_id", int,
        description="Numer zgłoszenia ataku (opcjonalnie — linkuje raport do wątku)",
        required=False, default=None,
    )
    async def traport(self, ctx: discord.ApplicationContext, atak_id: int | None):
        # Resolve thread if attack_id provided
        thread_id = None
        if atak_id:
            def _get_thread():
                from app.models import AttackReport
                atk = AttackReport.query.get(atak_id)
                return atk.forum_thread_id if atk else None

            thread_id = await db_query(self.bot, _get_thread)

        modal = ReportModal(self.bot, attack_id=atak_id, thread_id=thread_id)
        await ctx.send_modal(modal)

    # ------------------------------------------------------------------ #
    # /twojska — register village troops
    # ------------------------------------------------------------------ #
    @discord.slash_command(name="twojska", description="Zarejestruj wojska w wiosce")
    @discord.option("wioska", str, description="Koordynaty wioski (auto w wątku obrony)", required=False, default=None)
    async def twojska(self, ctx: discord.ApplicationContext, wioska: str | None):
        if wioska is None:
            coords = await self._detect_thread_coords(ctx.channel_id)
            if coords:
                x, y = coords
                wioska = f"{x}|{y}"
            else:
                await ctx.respond(
                    "❌ Podaj koordynaty wioski lub użyj komendy w wątku obrony.",
                    ephemeral=True,
                )
                return
        else:
            x, y = parse_coords(wioska)
            if x is None:
                await ctx.respond(
                    "❌ Nieprawidłowe koordynaty. Użyj formatu `76|43`.",
                    ephemeral=True,
                )
                return

        modal = TroopsModal(self.bot, wioska)
        await ctx.send_modal(modal)

    # ------------------------------------------------------------------ #
    # /twsparcie — register support
    # ------------------------------------------------------------------ #
    @discord.slash_command(name="twsparcie", description="Zarejestruj wysłane wsparcie")
    @discord.option("z", str, description="Koordynaty wioski wysyłającej np. 76|43", required=True)
    @discord.option("do", str, description="Koordynaty celu (auto w wątku obrony)", required=False, default=None)
    @discord.option("atak_id", int, description="Numer zgłoszenia ataku (opcjonalnie)", required=False, default=None)
    async def twsparcie(
        self,
        ctx: discord.ApplicationContext,
        z: str,
        do: str | None,
        atak_id: int | None,
    ):
        from_x, from_y = parse_coords(z)
        if from_x is None:
            await ctx.respond("❌ Nieprawidłowe koordynaty źródła.", ephemeral=True)
            return

        if do is None:
            coords = await self._detect_thread_coords(ctx.channel_id)
            if coords:
                to_x, to_y = coords
                do = f"{to_x}|{to_y}"
            else:
                await ctx.respond(
                    "❌ Podaj koordynaty celu lub użyj komendy w wątku obrony.",
                    ephemeral=True,
                )
                return
        else:
            to_x, to_y = parse_coords(do)
            if to_x is None:
                await ctx.respond("❌ Nieprawidłowe koordynaty celu.", ephemeral=True)
                return

        modal = SupportModal(self.bot, z, do, attack_id=atak_id)
        await ctx.send_modal(modal)

    # ------------------------------------------------------------------ #
    # /tstan — show village defense status
    # ------------------------------------------------------------------ #
    @discord.slash_command(name="tstan", description="Pokaż stan obrony wioski (wojska + wsparcie)")
    @discord.option("wioska", str, description="Koordynaty wioski (auto w wątku obrony)", required=False, default=None)
    async def tstan(self, ctx: discord.ApplicationContext, wioska: str | None):
        await ctx.defer()

        if wioska is None:
            coords = await self._detect_thread_coords(ctx.channel_id)
            if coords:
                x, y = coords
            else:
                await ctx.followup.send(
                    "❌ Podaj koordynaty wioski lub użyj komendy w wątku obrony.",
                    ephemeral=True,
                )
                return
        else:
            x, y = parse_coords(wioska)
            if x is None:
                await ctx.followup.send(
                    "❌ Nieprawidłowe koordynaty.", ephemeral=True
                )
                return

        server_url = self._server_url()

        def _get_status():
            from app.models import VillageTroops, TroopSupport

            # Own troops
            own = VillageTroops.query.filter_by(
                village_x=x, village_y=y,
            ).order_by(VillageTroops.updated_at.desc()).first()

            # Incoming support
            supports = TroopSupport.query.filter_by(
                to_x=x, to_y=y, status="in_transit",
            ).all()

            own_data = None
            if own:
                own_data = {
                    "troops": json.loads(own.troops),
                    "crop": own.crop_consumption,
                    "player": own.player_name,
                    "updated": own.updated_at.isoformat() if own.updated_at else "?",
                }

            support_data = []
            for s in supports:
                support_data.append({
                    "id": s.id,
                    "from_x": s.from_x, "from_y": s.from_y,
                    "troops": json.loads(s.troops),
                    "crop": s.crop_consumption,
                    "player": s.player_name,
                })

            return own_data, support_data

        own_data, support_data = await db_query(self.bot, _get_status)

        coord_display = coords_display(server_url, x, y)
        embed = discord.Embed(
            title=f"🏰 Stan obrony {coord_display}",
            color=COLOR_INFO,
        )

        total_crop = 0

        # Own troops
        if own_data:
            lines = [f"  {name}: **{count}**" for name, count in own_data["troops"].items()]
            own_crop = own_data["crop"] or 0
            total_crop += own_crop
            embed.add_field(
                name=f"🛡️ Garnizon ({own_data['player']})",
                value="\n".join(lines) + f"\n🌾 {own_crop}/h",
                inline=False,
            )
        else:
            embed.add_field(
                name="🛡️ Garnizon",
                value="_Brak zarejestrowanych wojsk_\nUżyj `/twojska` aby dodać",
                inline=False,
            )

        # Support
        if support_data:
            for s in support_data[:10]:
                lines = [f"  {name}: **{count}**" for name, count in s["troops"].items()]
                s_crop = s["crop"] or 0
                total_crop += s_crop
                embed.add_field(
                    name=f"📤 Wsparcie #{s['id']} od {s['player']} ({s['from_x']}|{s['from_y']})",
                    value="\n".join(lines) + f"\n🌾 {s_crop}/h",
                    inline=False,
                )

        # Total crop
        embed.add_field(
            name="🌾 Łączne zużycie zboża",
            value=f"**{total_crop}** zboża/h",
            inline=False,
        )

        embed.set_footer(text=FOOTER)
        await ctx.followup.send(embed=embed)

    # ------------------------------------------------------------------ #
    # /traporty — list battle reports for an attack
    # ------------------------------------------------------------------ #
    @discord.slash_command(name="traporty", description="Lista raportów bitewnych")
    @discord.option("atak_id", int, description="Numer zgłoszenia ataku (opcjonalnie)", required=False, default=None)
    @discord.option("limit", int, description="Ile raportów wyświetlić", required=False, default=5, min_value=1, max_value=20)
    async def traporty(self, ctx: discord.ApplicationContext, atak_id: int | None, limit: int):
        await ctx.defer()

        def _get_reports():
            from app.models import BattleReport
            query = BattleReport.query
            if atak_id:
                query = query.filter_by(attack_report_id=atak_id)
            reports = query.order_by(BattleReport.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": r.id,
                    "attack_id": r.attack_report_id,
                    "atk_name": r.attacker_name,
                    "atk_alliance": r.attacker_alliance,
                    "atk_village": r.attacker_village,
                    "def_name": r.defender_name,
                    "def_alliance": r.defender_alliance,
                    "def_village": r.defender_village,
                    "power_atk": r.battle_power_atk,
                    "power_def": r.battle_power_def,
                    "created": r.created_at.strftime("%d.%m %H:%M") if r.created_at else "?",
                }
                for r in reports
            ]

        reports = await db_query(self.bot, _get_reports)

        if not reports:
            embed = discord.Embed(
                title="📋 Brak raportów",
                description="Nie znaleziono raportów." + (
                    f" (atak #{atak_id})" if atak_id else ""
                ),
                color=COLOR_INFO,
            )
            embed.set_footer(text=FOOTER)
            await ctx.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title="📋 Raporty bitewne" + (f" (atak #{atak_id})" if atak_id else ""),
            description=f"Znaleziono **{len(reports)}** raportów",
            color=COLOR_INFO,
        )

        for r in reports:
            atk_text = r["atk_name"] or "?"
            if r["atk_alliance"] and str(r["atk_alliance"]).strip():
                atk_text = f"[{r['atk_alliance']}] {atk_text}"
            dfn_text = r["def_name"] or "?"
            if r["def_alliance"] and str(r["def_alliance"]).strip():
                dfn_text = f"[{r['def_alliance']}] {dfn_text}"

            power_text = ""
            if r["power_atk"] or r["power_def"]:
                power_text = f" | ⚡ {r['power_atk'] or '?'} vs {r['power_def'] or '?'}"

            embed.add_field(
                name=f"#{r['id']} — {r['created']}",
                value=f"⚔️ {atk_text} → 🛡️ {dfn_text}{power_text}",
                inline=False,
            )

        embed.set_footer(text=FOOTER)
        await ctx.followup.send(embed=embed)

    # ------------------------------------------------------------------ #
    # /traport_reczny — manual report for mobile users
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="traport_reczny",
        description="Ręczne dodanie raportu (np. z telefonu)"
    )
    @discord.option("atak_id", int, description="Numer zgłoszenia ataku", required=True)
    @discord.option("wynik", str, description="Wynik bitwy",
                    choices=["wygrana_obrony", "przegrana_obrony", "remis", "szpieg"])
    @discord.option("notatki", str, description="Opis co się stało, straty, szczegóły",
                    required=False, default="")
    @discord.option("napastnik", str, description="Co wysłał napastnik (np. 500 pałkarzy, 200 toporników)",
                    required=False, default="")
    @discord.option("obronca", str, description="Co miał obrońca (np. 300 falang, mur 15)",
                    required=False, default="")
    async def traport_reczny(
        self,
        ctx: discord.ApplicationContext,
        atak_id: int,
        wynik: str,
        notatki: str,
        napastnik: str,
        obronca: str,
    ):
        await ctx.defer()

        result_map = {
            "wygrana_obrony": "Wygrana obrony ✅",
            "przegrana_obrony": "Przegrana obrony ❌",
            "remis": "Remis ⚖️",
            "szpieg": "Szpiegostwo 🔍",
        }

        def _save():
            from app.database import db
            from app.models import AttackReport, BattleReport

            attack = AttackReport.query.get(atak_id)
            if not attack:
                return None, "not_found"

            raw_parts = [f"Wynik: {result_map.get(wynik, wynik)}"]
            if napastnik:
                raw_parts.append(f"Napastnik: {napastnik}")
            if obronca:
                raw_parts.append(f"Obrońca: {obronca}")
            if notatki:
                raw_parts.append(f"Notatki: {notatki}")
            raw_text = "\n".join(raw_parts)

            report = BattleReport(
                attack_report_id=atak_id,
                raw_text=raw_text,
                attacker_name=attack.attacker_name,
                defender_name=attack.defender_name,
                result=wynik,
                is_manual=True,
                reported_by_discord=str(ctx.author.id),
                reported_by_name=str(ctx.author),
            )
            db.session.add(report)
            db.session.commit()

            return {
                "id": report.id,
                "attack_id": atak_id,
                "thread_id": attack.forum_thread_id,
                "attacker": attack.attacker_name or "?",
                "defender": attack.defender_name or "?",
            }, "ok"

        result, status = await db_query(self.bot, _save)

        if status == "not_found":
            await ctx.followup.send(f"❌ Atak #{atak_id} nie istnieje.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 Raport ręczny zapisany",
            description=(
                f"Raport **#{result['id']}** dla ataku **#{atak_id}**\n"
                f"⚔️ {result['attacker']} → 🛡️ {result['defender']}\n"
                f"Wynik: **{result_map.get(wynik, wynik)}**"
            ),
            color=COLOR_INFO,
        )
        if napastnik:
            embed.add_field(name="⚔️ Napastnik", value=napastnik, inline=False)
        if obronca:
            embed.add_field(name="🛡️ Obrońca", value=obronca, inline=False)
        if notatki:
            embed.add_field(name="📝 Notatki", value=notatki, inline=False)
        embed.set_footer(text=f"{FOOTER} | ⚠️ Raport ręczny — niezweryfikowany")
        await ctx.followup.send(embed=embed)

        # Post in defense thread if available
        if result.get("thread_id"):
            try:
                thread = await self.bot.fetch_channel(result["thread_id"])
                await thread.send(
                    content=f"📋 **Raport ręczny** od {ctx.author.display_name}",
                    embed=embed,
                )
            except Exception:
                log.exception("Błąd wysyłania raportu do wątku")


def setup(bot):
    bot.add_cog(Defense(bot))
