# W.I.T.E.K — Wielki Audyt Projektu + Plan Dalszych Prac

> Ten plik służy jako kontekst dla nowej sesji Copilot.
> Zawiera pełny obraz projektu, co już zrobiono, co trzeba zrobić, i jak.

---

## 1. O projekcie

**W.I.T.E.K** (Wirtualny Informator Taktyczno-Ekonomiczny Koalicji) — narzędzie analityczne dla sojuszu **UFOLODZY** w grze Travian Legends. Nazwany na cześć H2P_Gucio (Witold Tacikiewicz).

**Stack technologiczny:**
- **Backend:** Flask (dashboard web) + SQLAlchemy (DB)
- **Bot Discord:** py-cord (slash commands)
- **Baza danych:** SQLite (dev), PostgreSQL 16 (prod)
- **Źródło danych:** Publiczny endpoint `GET {server_url}/map.sql` (~1.6MB, ~14k wiosek)
- **Deployment:** Docker Compose (osobne instancje per serwer Travian)
- **Testy:** pytest (~879 testów)
- **CI:** GitHub Actions
- **Repo:** https://github.com/PeterPage2115 (konto właściciela)

**Główny cel strategiczny:** Obsługa serwera **Reign of Fire (RoF) x3 International** — serwer sezonowy Travian Legends. Architektura jest multi-server: ten sam kod, `SERVER_PROFILE` env var wybiera profil z `config.yaml`.

---

## 2. Architektura projektu

```
run.py                      # Punkt wejścia: Flask + bot + scheduler
├── app/                    # Aplikacja Flask (dashboard web)
│   ├── __init__.py         # App factory (create_app)
│   ├── config.py           # Config z .env + config/config.yaml (via server_profile)
│   ├── database.py         # SQLAlchemy + _ensure_columns (lightweight migrations)
│   ├── models.py           # Snapshot, Village, Player, Alliance, User, Alert,
│   │                       #   AttackReport, DefenseThread, VillageTroops,
│   │                       #   TroopSupport, BattleReport
│   │                       #   + MonitorSettings, PersonalAlert (DEPRECATED — do usunięcia)
│   ├── auth_utils.py       # RBAC dekoratory (login_required, role_required)
│   ├── map_sql/            # Parser + collector + alerts
│   │   ├── parser.py       # 16-field parser (region, capital, city, harbor, VP)
│   │   ├── collector.py    # Fetch map.sql + store snapshot + run alert detection
│   │   └── alerts.py       # Alert engine: pop_drops, new_villages, alliance_changes
│   ├── routes/             # Flask blueprinty (~13 blueprintów)
│   │   ├── dashboard.py    # Strona główna
│   │   ├── players.py      # Lista graczy, profil gracza, historia
│   │   ├── alliances.py    # Lista sojuszy, porównanie
│   │   ├── alerts_web.py   # Strona /alerts z filtrowaniem i paginacją
│   │   ├── auth.py         # Login/logout/register
│   │   ├── attacks.py      # Raporty ataków
│   │   ├── defense.py      # Wątki obronne
│   │   ├── map.py          # Mapa
│   │   ├── reports.py      # Raporty bitewne
│   │   └── ...
│   └── templates/          # 17 szablonów Jinja2 (styl Travian — ciemny/średniowieczny)
│
├── bot/                    # Bot Discord (py-cord)
│   ├── bot.py              # create_bot(), db_query() helper
│   ├── tribes.py           # Definicje plemion + jednostek (tid 1-9), single source of truth
│   ├── utils.py            # Unit speeds, crop tables, distance calc, time parsing, FOOTER
│   ├── deep_links.py       # In-game URL generators (map, send troops, marketplace)
│   └── cogs/               # 9 kogów (auto-loaded z bot/cogs/*.py via glob)
│       ├── general.py      # /thelp, /tinfo, /tstats
│       ├── identity.py     # /tlink, /tunlink, /twhoami
│       ├── attacks.py      # /tatak, /tdodaj, /tataki, /trozwiaz
│       ├── defense.py      # /twojska, /twsparcie, /tstan, /tdef
│       ├── alerts.py       # Auto-send alert embeds (60s loop, discord_eligible filter)
│       ├── recon.py        # /tnieaktywni (inactive finder)
│       ├── economy.py      # /tcropper, /tszukaj, /tporownaj, /tsymulacja, /tbezpieczne, /tileobrony, /tprzechwyc
│       ├── digest.py       # /tdigest (weekly digest)
│       └── diplomacy.py    # /taddsojusz, /tremovesojusz, /tsojusz, /taddpakt, ...
│
├── server_profile.py       # Shared profile loader (na root, nie w app/ — unika circular import)
├── config/
│   ├── config.yaml         # Multi-server config z sekcją servers: (ts31, rof-x3)
│   └── config.example.yaml
├── extension/              # Chrome extension do parsowania raportów bitewnych
├── tests/                  # ~879 testów pytest
├── scripts/                # apply_migrations.py (DO USUNIĘCIA), validate_rof*.py (DO USUNIĘCIA)
├── migrations/             # 003_auto_resolved.sql (DO USUNIĘCIA — redundantny z _ensure_columns)
├── docker-compose.yml      # Produkcja ts31 (PostgreSQL)
├── docker-compose.dev.yml  # Dev (SQLite, source mounted)
├── docker-compose.rof.yml  # RoF x3 (osobna instancja PostgreSQL, port 5001)
├── .env.rof.example        # Template zmiennych dla RoF instancji
├── Dockerfile
├── docker-entrypoint.sh    # Uruchamia migracje + Flask
└── docs/
    ├── ROADMAP.md          # Kierunek rozwoju (ZACHOWAĆ)
    ├── PLAN.md             # Ten plik
    └── superpowers/        # Wewnętrzne notatki z planowania (DO USUNIĘCIA)
```

---

## 3. Kluczowe decyzje techniczne

### DB access w bocie Discord
Wszystkie zapytania do bazy w cogach MUSZĄ iść przez `db_query()` z `bot.bot`:
```python
from bot.bot import db_query
result = await db_query(self.bot, lambda: Player.query.get(uid))
```
Uruchamia blocking SQLAlchemy w executorze z Flask app context.
**KRYTYCZNE:** Nigdy nie zwracaj raw SQLAlchemy obiektów z `db_query()` — stają się detached po executorze. Zawsze zwracaj dict/tuple.

### System migracji
Nie używamy Alembic. Mamy `_ensure_columns()` w `app/database.py`:
- Dict `expected` definiuje kolumny per tabela
- Przy starcie sprawdza PRAGMA table_info i dodaje brakujące kolumny ALTER TABLE
- Prosty ale wystarczający dla naszego projektu

### System alertów
1. `collector.py` pobiera map.sql → `store_snapshot()` → `detect_alerts()`
2. `detect_alerts()` porównuje nowy snapshot z poprzednim, generuje listę alertów
3. Alerty zapisywane jako `Alert` rows w DB z flagami: `notified`, `discord_eligible`
4. `AlertsCog` (bot) — loop co 60s, pobiera `discord_eligible=True, notified=False`, wysyła embedy, oznacza `notified=True`
5. **discord_eligible:** `True` = pop_drop (idzie na Discord), `False` = new_village, alliance_change (tylko dashboard)

### Multi-server architecture
- `SERVER_PROFILE` env var (np. `ts31`, `rof-x3`)
- `config.yaml` ma sekcję `servers:` z profilem per serwer
- `server_profile.py` ładuje profil: url, speed, tribes, alliances, features
- Osobne Docker Compose pliki per instancja (osobna baza, token bota, port)

### Tribe IDs
1=Romans, 2=Teutons, 3=Gauls, 4=Nature, 5=Natars, 6=Egyptians, 7=Huns, **8=Spartans**, **9=Vikings**
Źródło prawdy: `bot/tribes.py`

### Inactive Finder (/tnieaktywni)
Cohort-based: porównuje najnowszy i najwcześniejszy snapshot. Gracz jest "nieaktywny" gdy ZARÓWNO `total_pop` JAK I `village_count` nie zmieniły się. Bounding-box prefilter z torus wrap-around.

### Snapshot validation
`validate_snapshot_pair()` odrzuca nowe snapshoty z < 50% wiosek poprzedniego (ochrona przed partial download → false alerty).

---

## 4. Co już zrobiono

### RoF Migration Phase 1 — KOMPLETNE (5 chunków)
| Chunk | Co | Commit |
|-------|----|--------|
| 1 | Tribe ID fix (tid 8↔9 swap → 8=Spartans, 9=Vikings) | `c3aa411` |
| 2 | Shared profile loader (`server_profile.py`) + config refactor | `ea8c7f4`, `ecf5cd7` |
| 3 | 16-field parser (region, capital, city, harbor, VP) | `ecf5cd7` |
| 4 | Docker multi-instance (`docker-compose.rof.yml`) + deep links | `03636e9`+ |
| 5 | Rebalanced Legionnaire stats | `c3aa411` |

### Sprint 3 — Alert Rework — KOMPLETNE (4 taski)
| Task | Co | Commit |
|------|----|--------|
| 1 | Pop_drop alerts → tylko nasz sojusz (threshold 25%, min 500, cooldown 6h) | `93f7e45` |
| 2 | Usunięte /tczuwanie, /tmonitor, /tmonitor_ustawienia | `ad965f9` |
| 3 | Nowa strona /alerts na dashboardzie | `50d726b` |
| 4 | Discord embed improvements + discord_eligible flag | `b47887c` |

### Inne ukończone
- Quick-search dla graczy i sojuszy na dashboardzie (`8d882ff`)
- CI/CD setup (GitHub Actions)
- Chrome extension do raportów bitewnych
- Docker Compose (dev + prod + RoF)
- Wersjonowanie 0.1.0

---

## 5. Znane problemy do naprawienia

### 🔴 PILNE: Alert spam na Discord
**Problem:** Stare alerty `new_village` i `alliance_change` w bazie powstały PRZED dodaniem kolumny `discord_eligible`. Kolumna ma `DEFAULT 1` (True), więc wszystkie stare alerty mają `discord_eligible=True` i bot je wysyła na Discord.
**Rozwiązanie:** Jednorazowy UPDATE w `_ensure_columns` lub `init_db`:
```sql
UPDATE alerts SET discord_eligible = 0
WHERE alert_type IN ('new_village', 'alliance_change') AND notified = 0;
```

### 🟡 Brak wystarczającego logowania
- `bot/cogs/alerts.py` — brak logów ile alertów znaleziono/wysłano
- `app/map_sql/collector.py` — brak szczegółów co detect_alerts zwrócił
- `app/map_sql/alerts.py` — brak logów per typ alertu

### 🟡 Martwy kod w repozytorium
- `alembic` w requirements.txt (nigdzie nie importowany)
- `migrations/` folder (jedna migracja, już w _ensure_columns)
- `scripts/apply_migrations.py` (wywoływany w docker-entrypoint.sh ale redundantny)
- `MonitorSettings`, `PersonalAlert` w models.py (deprecated, nigdzie nie importowane)
- `docs/superpowers/` (wewnętrzne notatki planowania)
- `scripts/validate_rof_parser.py`, `scripts/validate_rof_collector.py` (jednorazowe, już wykonane)

### 🟡 Nieaktualna dokumentacja
- README.md: nadal wymienia /tmonitor, /tmonitor_ustawienia (usunięte)
- README.md: mówi "853+ testów" (jest ~879)
- CHANGELOG.md: brak sekcji 0.2.0
- DEPLOY.md: może zawierać referencje do apply_migrations.py

---

## 6. Plan Audytu — 7 zadań

### Task 1: Naprawa alertów — data migration + logging
**Cel:** Naprawić spam alertów na Discord + dodać logowanie.

**Kroki:**
1. W `app/database.py` dodać jednorazową migrację danych po `_ensure_columns()`:
   - `UPDATE alerts SET discord_eligible=0 WHERE alert_type IN ('new_village', 'alliance_change') AND notified=0`
2. W `bot/cogs/alerts.py` dodać logging:
   - `logger.info("Znaleziono %d alertów do wysłania (discord_eligible=True, notified=False)", count)`
   - `logger.info("Wysłano %d alertów na Discord", sent_count)`
3. W `app/map_sql/collector.py` dodać logging:
   - `logger.info("detect_alerts zwrócił %d alertów: %s", len(alerts), {typ: count for typ, count in ...})`
4. W `app/map_sql/alerts.py` dodać logging per typ

**Pliki do edycji:** `app/database.py`, `bot/cogs/alerts.py`, `app/map_sql/collector.py`, `app/map_sql/alerts.py`

---

### Task 2: Usunięcie martwego kodu
**Cel:** Usunąć nieużywane pliki i kod. **⚠️ NIE USUWAJ plików RoF!**

**Co usunąć:**
| Co | Gdzie |
|----|-------|
| `alembic` dependency | `requirements.txt` |
| `migrations/` folder | Cały folder (jedyna migracja jest w _ensure_columns) |
| `scripts/apply_migrations.py` | Plik |
| Wywołanie apply_migrations | `docker-entrypoint.sh` |
| `.gitignore` linia o alembic | `migrations/versions/__pycache__/` |
| `MonitorSettings` klasa | `app/models.py` |
| `PersonalAlert` klasa | `app/models.py` |
| `docs/superpowers/` | Cały folder (11 plików planowania) |
| `scripts/validate_rof_parser.py` | Plik (jednorazowy, wykonany) |
| `scripts/validate_rof_collector.py` | Plik (jednorazowy, wykonany) |

**⚠️ ZACHOWAJ:**
- `docker-compose.rof.yml` — instancja RoF
- `.env.rof.example` — template dla RoF
- `tests/test_collector_rof.py` — testy RoF collectora
- `tests/test_parser_rof.py` — testy RoF parsera
- `tests/test_tribes_rof.py` — testy RoF tribes
- `server_profile.py` — shared profile loader
- `bot/deep_links.py` — deep link generators
- `docs/ROADMAP.md` — kierunek rozwoju
- `extension/` — Chrome extension

---

### Task 3: README.md — aktualizacja
- Usunąć `/tmonitor` i `/tmonitor_ustawienia` z tabeli komend
- Zaktualizować liczbę testów → aktualna
- Zaktualizować liczbę kogów → 9
- Dodać do funkcji dashboardu: 🔔 Alerty (filtrowanie, historia), 🔍 Szybkie wyszukiwanie
- Zaktualizować sekcję Multi-server/RoF (to jest aktywna funkcja, nie legacy)

---

### Task 4: CHANGELOG.md — sekcja 0.2.0
Dodać nową sekcję:
```markdown
## [0.2.0]

### Dodane
- Strona /alerts na dashboardzie z filtrowaniem i paginacją
- System discord_eligible — kontrola które alerty trafiają na Discord
- Sortowanie alertów po severity + limit 10 na Discord embed
- Timestamps w embeddach Discord
- Szybkie wyszukiwanie graczy i sojuszy na dashboardzie

### Zmienione
- Alerty pop_drop ograniczone do naszego sojuszu (threshold 25%, min 500 pop, cooldown 6h)
- Usunięte komendy /tczuwanie, /tmonitor, /tmonitor_ustawienia
- Usunięty Alembic (redundantny — _ensure_columns)
- Usunięte deprecated modele MonitorSettings, PersonalAlert
- Porządki w dokumentacji i skryptach

### Naprawione
- Spam alertów na Discord (new_village/alliance_change oznaczone jako dashboard-only)
- Data migration dla istniejących alertów w bazie
```

---

### Task 5: DEPLOY.md — aktualizacja
- Usunąć referencje do `python scripts/apply_migrations.py`
- Sprawdzić czy instrukcje RoF są aktualne
- Dodać info o systemie alertów i discord_eligible

---

### Task 6: pyproject.toml + requirements.txt
- Bump wersji: `0.1.0` → `0.2.0`
- Dodać sekcję `[project.dependencies]` (mirror requirements.txt)
- Usunąć `alembic` z requirements.txt (redundantny)

---

### Task 7: Weryfikacja końcowa
1. `python -m pytest tests/ -x -q` — wszystko przechodzi
2. `ruff check app/ bot/ tests/` — brak błędów lint
3. Git commit + push
4. Sprawdzić CI na GitHub

---

## 7. Zależności między taskami

```
Wave 1 (równoległe):
  Task 1 (alert fix) ──────┐
  Task 2 (dead code) ──────┤
  Task 6 (pyproject)  ─────┤
                            │
Wave 2 (po Wave 1):        │
  Task 3 (README)    ◄─────┤ (zależy od Task 2)
  Task 4 (CHANGELOG) ◄─────┤ (zależy od Task 1 + 2)
  Task 5 (DEPLOY)    ◄─────┘ (zależy od Task 2)

Wave 3 (po wszystkich):
  Task 7 (weryfikacja) ◄── zależy od WSZYSTKICH
```

---

## 8. Konwencje kodowania

- **Język:** Komentarze i UI po polsku; identyfikatory kodu po angielsku
- **Discord embeds:** Kolory — red=atak, green=obrona/sukces, yellow=warning, blue=info, gold=identity
- **Footer:** `"⚔️ W.I.T.E.K — Na cześć Gucio"` na wszystkich embedach
- **Błędy:** Polskie komunikaty z emoji (✅ ❌ ⚠️ 💡)
- **Testy:** pytest; `python -m pytest tests/ -v`; każdy plik testowy ma własne fixtures (brak shared conftest)
- **Commity:** Krótkie, zwięzłe, z `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer
- **Wersjonowanie:** SemVer (0.x.y), CHANGELOG w formacie Keep a Changelog
- **Styl kodu:** Minimalne komentarze — tylko to co wymaga wyjaśnienia
- **Bot cogs auto-load:** `bot/bot.py` ładuje `bot/cogs/*.py` via glob — usunięcie pliku = usunięcie coga

---

## 9. Komendy

```bash
# Lokalne uruchomienie
python run.py                       # Flask + bot (jeśli DISCORD_TOKEN ustawiony)
python run.py --scheduled           # Flask + bot + scheduler (daily map.sql)
python run.py --bot-only            # Tylko bot Discord (bez Flask)
python run.py --collect             # Jednorazowe pobranie map.sql
python run.py --from-file map.sql   # Import z lokalnego pliku

# Docker
docker compose -f docker-compose.dev.yml up    # Dev (SQLite)
docker compose up -d                           # Produkcja ts31 (PostgreSQL)
docker compose -f docker-compose.rof.yml up -d # RoF x3 (PostgreSQL, port 5001)

# Testy
python -m pytest tests/ -v
python -m pytest tests/ -x -q       # Szybki run (stop on first failure)
ruff check app/ bot/ tests/          # Lint
```

---

## 10. Pliki konfiguracyjne

### .env (wymagane)
```
DISCORD_TOKEN=...
DISCORD_GUILD_ID=...
DISCORD_ALERTS_CHANNEL_ID=...
DISCORD_DEFENSE_FORUM_ID=...
DISCORD_DEF_ROLE_ID=...
FLASK_SECRET_KEY=...
SERVER_PROFILE=ts31          # lub rof-x3
TRAVIAN_SERVER_URL=...
DATABASE_URL=...             # PostgreSQL w produkcji
```

### config/config.yaml (wieloserwerowy)
```yaml
servers:
  ts31:
    url: "https://ts31.x3.europe.travian.com"
    speed: 3
    tribes: [1, 2, 3, 6, 7, 8, 9]
    our_alliances: [14, 32, 46, 120]
    features: { ships: false, regions: false, cities: false }
    legionnaire_rebalanced: false

  rof-x3:
    url: "https://rof.x3.international.travian.com"
    speed: 3
    tribes: [1, 3, 6, 7, 8, 9]        # Brak Teutonów na RoF
    our_alliances: []
    features: { ships: true, regions: true, cities: true }
    legionnaire_rebalanced: true

alerts:
  pop_drop_threshold: 25
  min_pop_for_alerts: 500
  alert_cooldown_hours: 6
  new_village_radius: 30
  max_alerts_per_type: 10
```

---

## 11. Travian CDN Assets

Icon base URL: `https://cdn.legends.travian.com/gpack/417.3/img_ltr/`
- Tribe icons: `global/tribes/{roman|teuton|gaul}_medium.png` (też `_small.png`; `_large.png` NIE istnieje)
- Resources: `global/resources/{lumber|clay|iron|crop}_small.png` (też `_tiny.png`)
- Attack icons: `legacy/a/att1.gif` (raid), `att2.gif` (attack), `att3.gif` (spy), `def1.gif` (defense)
- Hero: `hud/topBar/hero/states/heroHome.png`

---

## 12. Co dalej po audycie

Po zakończeniu audytu (Tasks 1-7) priorytetem jest:
1. **Uruchomienie na RoF x3** — deploy z docker-compose.rof.yml, konfiguracja bota dla nowego serwera
2. **Dashboard improvements** — wykresy populacji, mapa interaktywna, lepsze filtry
3. **Nowe komendy bota** — analityka regionów (RoF feature), zarządzanie Victory Points
4. **Performance** — caching, optymalizacja zapytań dla dużych snapshotów
