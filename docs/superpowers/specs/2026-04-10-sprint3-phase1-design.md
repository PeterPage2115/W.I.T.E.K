# Sprint 3 Phase 1 — Design Specification

**Data:** 2026-04-10
**Zakres:** Nowe nacje, bugfixy danych, auto-resolve, bilans zbożowy, testy integracyjne

---

## 1. Architektura — nowy moduł `bot/tribes.py`

### Problem
Dane jednostek (prędkości, zużycie zboża, statystyki bojowe) są rozproszone w 4 osobnych słownikach w `bot/utils.py` (UNIT_SPEEDS, UNIT_CROP, UNIT_COMBAT, _ALIASES). Dodanie 4 nowych nacji oznaczałoby dalszą duplikację i ryzyko niespójności.

### Rozwiązanie
Nowy moduł `bot/tribes.py` z ujednoliconą definicją jednostek per nacja. Każda jednostka definiowana jest raz z wszystkimi atrybutami.

### Struktura danych

```python
@dataclass(frozen=True)
class UnitDef:
    name: str           # Kanoniczna nazwa (po polsku dla tid 1-3, angielska dla 6-9)
    att: int            # Atak bazowy
    def_inf: int        # Obrona przed piechotą
    def_cav: int        # Obrona przed kawalerią
    speed: int          # Prędkość bazowa (pola/h bez mnożnika serwera)
    crop: int           # Zużycie zboża/h
    unit_type: str      # inf / cav / siege / special
    aliases: tuple[str, ...] = ()  # Alternatywne formy nazwy

@dataclass(frozen=True)
class TribeDef:
    tid: int
    name_pl: str        # Nazwa nacji po polsku
    name_en: str        # Nazwa nacji po angielsku
    wall_type: str      # Typ muru (City Wall, Earth Wall, etc.)
    units: tuple[UnitDef, ...]
    settler_name: str = "Osadnik"
    chief_idx: int = 8  # Indeks wodza w liście jednostek (domyślnie 8 = slot 9)
```

### Registry

```python
TRIBES: dict[int, TribeDef]  # tid → TribeDef
```

Dostęp: `TRIBES[3].units[0].speed` → bazowa prędkość Falangity.

### Kompatybilność wsteczna

`bot/utils.py` zachowuje istniejące interfejsy (UNIT_SPEEDS, UNIT_CROP, UNIT_COMBAT, CROP_BY_NAME, COMBAT_BY_NAME, _ALIASES, SPEED_BY_NAME). Generowane dynamicznie z `TRIBES` na starcie:

```python
from bot.tribes import TRIBES, get_speed_multiplier

TROOP_SPEED_MULTIPLIER = get_speed_multiplier()  # z config.yaml

UNIT_SPEEDS = {}
for tid, tribe in TRIBES.items():
    UNIT_SPEEDS[tid] = [
        {"name": u.name, "speed": u.speed * TROOP_SPEED_MULTIPLIER, "type": u.unit_type}
        for u in tribe.units if u.unit_type != "special" or True
    ]
# analogicznie UNIT_CROP, UNIT_COMBAT, _ALIASES
```

Żaden cog nie wymaga zmian w importach — dalej importuje z `bot.utils`.

---

## 2. Kompletne dane jednostek

### Źródło danych
`http://travian.kirilloid.ru/js/units.js` — zweryfikowane krzyżowo z oficjalną wiki Travian dla Wikingów (idealny match).

### Mapowanie kirilloid → tid w grze
- units[0] = tid 1 = Rzymianie
- units[1] = tid 2 = Germanie
- units[2] = tid 3 = Galowie
- units[5] = tid 6 = Egipcjanie
- units[6] = tid 7 = Hunowie
- units[7] = tid 8 = **Spartanie** (kirilloid index ≠ game tid!)
- units[8] = tid 9 = **Wikingowie** (kirilloid index ≠ game tid!)

**UWAGA:** Kirilloid ma Spartan=index 7, Vikings=index 8. W grze (map.sql) jest odwrotnie: Vikings=tid 8, Spartans=tid 9. Moduł `tribes.py` używa game tid.

### Bugfixy w istniejących danych (tid 1-3)

| Jednostka | Pole | Stara wartość | Poprawna | Źródło |
|-----------|------|---------------|----------|--------|
| Grom Teutatesa | att | 90 | **100** | kirilloid (brak T4 override) |
| Gaul Taran | def_cav | 70 | **105** | kirilloid |
| Equites Legati | crop | 3 | **2** | kirilloid cu=2 |
| Teuton Wódz | crop | 5 | **4** | kirilloid cu=4 |
| Gaul Wódz | crop | 5 | **4** | kirilloid cu=4 |

### Nowe nacje — statystyki bazowe

#### Egipcjanie (tid=6)

| Jednostka | ATK | Def(I) | Def(C) | Speed | Crop | Typ |
|-----------|-----|--------|--------|-------|------|-----|
| Slave Militia | 10 | 30 | 20 | 7 | 1 | inf |
| Ash Warden | 30 | 55 | 40 | 6 | 1 | inf |
| Khopesh Warrior | 65 | 50 | 20 | 7 | 1 | inf |
| Sopdu Explorer | 0 | 20 | 10 | 16 | 2 | cav |
| Anhur Guard | 50 | 110 | 50 | 15 | 2 | cav |
| Resheph Chariot | 110 | 120 | 150 | 10 | 3 | cav |
| Ram | 55 | 30 | 95 | 4 | 3 | siege |
| Catapult | 65 | 55 | 10 | 3 | 6 | siege |
| Nomarch | 40 | 50 | 50 | 4 | 4 | special |

#### Hunowie (tid=7)

| Jednostka | ATK | Def(I) | Def(C) | Speed | Crop | Typ |
|-----------|-----|--------|--------|-------|------|-----|
| Mercenary | 35 | 40 | 30 | 7 | 1 | inf |
| Bowman | 50 | 30 | 10 | 6 | 1 | inf |
| Spotter | 0 | 20 | 10 | 19 | 2 | cav |
| Steppe Rider | 120 | 30 | 15 | 16 | 2 | cav |
| Marksman | 110 | 80 | 70 | 15 | 2 | cav |
| Marauder | 180 | 60 | 40 | 14 | 3 | cav |
| Ram | 65 | 30 | 90 | 4 | 3 | siege |
| Catapult | 45 | 55 | 10 | 3 | 6 | siege |
| Logades | 50 | 40 | 30 | 5 | 4 | special |

*Mercenary speed: kirilloid=6, oficjalna tabela porównawcza=7. Używamy **7** (oficjalne źródło).*

#### Wikingowie (tid=8) — zweryfikowane z oficjalną wiki ✅

| Jednostka | ATK | Def(I) | Def(C) | Speed | Crop | Typ |
|-----------|-----|--------|--------|-------|------|-----|
| Thrall | 45 | 22 | 5 | 7 | 1 | inf |
| Shield Maiden | 20 | 50 | 30 | 7 | 1 | inf |
| Berserker | 70 | 30 | 25 | 5 | 2 | inf |
| Heimdall's Eye | 0 | 10 | 5 | 9 | 1 | cav |
| Huskarl Rider | 45 | 95 | 100 | 12 | 2 | cav |
| Valkyrie's Blessing | 160 | 50 | 75 | 9 | 2 | cav |
| Ram | 65 | 30 | 80 | 4 | 3 | siege |
| Catapult | 50 | 60 | 10 | 3 | 6 | siege |
| Jarl | 40 | 40 | 60 | 5 | 4 | special |

*Viking Ram crop: kirilloid=2, oficjalna wiki=3. Używamy **3** (oficjalne źródło).*

#### Spartanie (tid=9)

| Jednostka | ATK | Def(I) | Def(C) | Speed | Crop | Typ |
|-----------|-----|--------|--------|-------|------|-----|
| Hoplite | 50 | 35 | 30 | 6 | 1 | inf |
| Sentinel | 0 | 40 | 22 | 9 | 1 | inf |
| Shieldsman | 40 | 85 | 45 | 8 | 1 | inf |
| Twinsteel Therion | 90 | 55 | 40 | 6 | 1 | inf |
| Elpida Rider | 55 | 120 | 90 | 16 | 2 | cav |
| Corinthian Crusher | 195 | 80 | 75 | 9 | 3 | cav |
| Ram | 65 | 30 | 80 | 4 | 3 | siege |
| Catapult | 50 | 60 | 10 | 3 | 6 | siege |
| Ephor | 40 | 60 | 40 | 4 | 4 | special |

### Typy murów per nacja

| tid | Nacja | Mur | Uwagi |
|-----|-------|-----|-------|
| 1 | Rzymianie | City Wall | Najsilniejszy |
| 2 | Germanie | Earth Wall | Średni |
| 3 | Galowie | Palisade | Średni |
| 6 | Egipcjanie | Stone Wall | Bardzo wytrzymały |
| 7 | Hunowie | Makeshift Wall | Słaby |
| 8 | Wikingowie | Barricade | Średni |
| 9 | Spartanie | Defensive Wall | Słaby |

---

## 3. Konfiguracja per-serwer

### Zmiany w `config/config.yaml`

```yaml
travian:
  server_url: "https://ts31.x3.europe.travian.com"
  map_size: 401
  speed_multiplier: 3          # Prędkość serwera (x1/x2/x3/x5)
  troop_speed_multiplier: 2    # Mnożnik prędkości jednostek (na x3 = 2x)
  available_tribes: [1, 2, 3, 6, 7, 8, 9]  # Dostępne nacje na serwerze
  our_alliances: [14, 32, 46, 120]
```

### Wpływ na kod

1. **`bot/utils.py`**: `TROOP_SPEED_MULTIPLIER` ładowany z configu zamiast hardcoded `= 2`
2. **Autocomplete w komendach**: `/tsymulacja`, `/tdef`, `/tszukaj` filtrują nacje po `available_tribes`
3. **`app/models.py`**: `TRIBE_NAMES` rozszerzony o tid 6-9
4. **Walidacja**: Jeśli `available_tribes` nie podano, domyślnie `[1, 2, 3]` (kompatybilność wsteczna)

---

## 4. Auto-rozwiązywanie ataków

### Problem
Wątki obronne wiszą w nieskończoność jeśli nikt nie użyje `/trozwiaz`.

### Rozwiązanie
Background task w `Attacks` cog, uruchamiany co 5 minut.

### Algorytm

```
co 5 minut:
  1. Znajdź AttackReport z:
     - status IN ('reported', 'defending')
     - attack_unix < now() - auto_resolve_minutes * 60
  2. Dla każdego:
     a. Ustaw status = "resolved", resolved_at = now, auto_resolved = True
     b. Zamknij powiązany DefenseThread (status = "resolved")
     c. Wyślij wiadomość do wątku Discord:
        "🕐 Atak #X automatycznie rozwiązany (czas ataku minął 2h temu)"
     d. Archiwizuj wątek (thread.edit(archived=True))
```

### Zmiany w modelu

```python
# AttackReport — nowa kolumna
auto_resolved = db.Column(db.Boolean, default=False)
```

### Konfiguracja

```yaml
attacks:
  auto_resolve_after_minutes: 120  # Domyślnie 2h po czasie uderzenia
```

### Edge cases
- Atak bez `attack_unix` (nie podano czasu) → nie podlega auto-resolve
- Wątek z wieloma atakami → resolve dopiero gdy WSZYSTKIE ataki miną threshold
- Bot restart → loop wznawia się automatycznie, przetwarza zaległe ataki

---

## 5. Bilans zbożowy — `/tzboza`

### Komenda

```
/tzboza [kordy]
```

- `kordy` (opcjonalne) — koordynaty wioski np. `76|43`
- Jeśli pominięte i użyte w wątku obrony → auto-detect z DefenseThread

### Źródła danych

| Dane | Źródło | Model |
|------|--------|-------|
| Garnizon | `/twojska` | VillageTroops |
| Wsparcie przysłane | `/twsparcie` | TroopSupport (status=arrived) |
| Produkcja zboża | `/tatak` (pole produkcja) | AttackReport.crop_production |
| Bohater | Założenie: 6 crop/h jeśli jest | stała HERO_CROP |

### Kalkulacja

```python
garrison_crop = sum(CROP_BY_NAME[unit] * count for unit, count in troops.items())
support_crop = sum(
    CROP_BY_NAME[unit] * count
    for support in supports
    for unit, count in json.loads(support.troops).items()
)
hero_crop = HERO_CROP if has_hero else 0
total_consumption = garrison_crop + support_crop + hero_crop
balance = production - total_consumption
```

### Embed wyjściowy

```
🌾 Bilans zbożowy — Wioska (76|43)
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏠 Garnizon:      -245 🌾/h
🤝 Wsparcie (2):  -180 🌾/h
🦸 Bohater:         -6 🌾/h
━━━━━━━━━━━━━━━━━━━━━━━━━━━
📉 Zużycie:       -431 🌾/h
📈 Produkcja:     +620 🌾/h
💰 Bilans:        +189 🌾/h

⚠️ Przy obecnym zużyciu spichlerz (800k) starczy na ~34h
```

### Opcjonalne flagi
- `/tzboza 76|43 bohater:tak` — uwzględnij bohatera
- Domyślnie bohater NIE jest wliczany (nie wiemy czy jest w wiosce)

---

## 6. Testy integracyjne z testcord

### Narzędzie
**testcord** (`pip install testcord`) — fork dpytest dla py-cord. Symuluje Discord gateway bez prawdziwego połączenia.

### Struktura plików

```
tests/
├── conftest.py                    # Istniejące fixtures (Flask app)
├── test_*.py                      # Istniejące 385 unit testów
└── integration/
    ├── __init__.py
    ├── conftest.py                # testcord bot fixture + mock DB
    ├── test_cog_loading.py        # Czy wszystkie cogi ładują się
    ├── test_attacks_integration.py # /tatak, /tdodaj, /trozwiaz flow
    ├── test_defense_integration.py # /twojska, /twsparcie, /tstan, /tzboza
    └── test_economy_integration.py # /tsymulacja, /tszukaj, /tcropper
```

### Fixture wzorzec

```python
import pytest
import testcord  # dpytest fork for py-cord

@pytest.fixture
async def bot(flask_app):
    """Testcord bot z załadowanymi cogami i mock DB."""
    bot = commands.Bot()
    bot.flask_app = flask_app
    await bot.add_cog(Attacks(bot))
    await bot.add_cog(Defense(bot))
    testcord.configure(bot)
    yield bot
    await testcord.empty_queue()
```

### Zakres testów

1. **Cog loading** (~5 testów): Każdy cog ładuje się bez ImportError
2. **Attack flow** (~10 testów): `/tatak` → wątek → `/tdodaj` → `/trozwiaz`
3. **Defense flow** (~8 testów): `/twojska` → `/twsparcie` → `/tstan` → `/tzboza`
4. **Auto-resolve** (~3 testy): Background task prawidłowo zamyka stare ataki
5. **Tribe filtering** (~5 testów): Komendy respektują `available_tribes`

### CI/CD
Testy integracyjne w osobnym pytest marker: `pytest -m integration`. Uruchamiane osobno od unit testów, bo wymagają asyncio event loop.

---

## Podsumowanie zmian

| Komponent | Typ zmiany |
|-----------|-----------|
| `bot/tribes.py` | **NOWY** — ujednolicone definicje nacji |
| `bot/utils.py` | MODYFIKACJA — generuje słowniki z tribes.py, bugfixy |
| `config/config.yaml` | MODYFIKACJA — speed_multiplier, available_tribes |
| `app/config.py` | MODYFIKACJA — ładowanie nowych pól configu |
| `app/models.py` | MODYFIKACJA — auto_resolved kolumna, TRIBE_NAMES rozszerzenie |
| `bot/cogs/attacks.py` | MODYFIKACJA — auto-resolve background task |
| `bot/cogs/defense.py` | MODYFIKACJA — `/tzboza` komenda |
| `bot/cogs/economy.py` | MODYFIKACJA — tribe filtering w autocomplete |
| `tests/integration/` | **NOWY** — testy integracyjne z testcord |
| `migrations/` | **NOWY** — migracja auto_resolved kolumny |
| `requirements.txt` | MODYFIKACJA — dodanie testcord |
