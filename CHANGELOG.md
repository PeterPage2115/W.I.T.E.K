# Changelog

Wszystkie istotne zmiany w projekcie W.I.T.E.K.

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/).

## [0.2.4] — 2026-04-14

### Dodane
- Szablony błędów 404/500 w stylu Travian (`app/templates/errors/`)
- RBAC `@role_required("leader", "officer")` na 4 trasach eksportu CSV + testy
- `wsgi.py` + `gunicorn` w requirements.txt — opcja produkcyjnego WSGI
- Uzupełnione jednostki: Grom Teutatesa (Galowie), Heimdall's Eye (Wikingowie)

### Naprawione
- Extension: race condition w `handleSend()` — guard `_isSending`
- Extension: walidacja `isNaN()` w `getVillageCoords()`
- Extension: structured error logging w service-worker (`[W.I.T.E.K]` prefix)
- API mapy: auto-swap `x_min/x_max` gdy min > max
- Komentarz tribe w `models.py` zaktualizowany do RoF (bez Teutonów)

## [0.2.3] — 2026-04-14

### Naprawione
- **P0 flat-map:** Wszystkie wywołania `torus_distance()` teraz czytają `wrap` z profilu serwera — RoF używa płaskiej mapy (`wrap=False`)
- **P0 bbox_filter:** `_bbox_filter()` i `_tiles_in_radius()` w `recon.py` i `economy.py` poprawnie clampują do granic mapy gdy `wrap=False`
- **P0 Teutoni:** Usunięto referencje do tid=2 (Teutoni) z `_DEF_UNITS`, `REPORT_UNIT_ORDER`, `TRIBE_UNITS`, `TRAINING_COSTS` i list wyboru — niedostępni na RoF x3
- Poprawiono testy (`test_economy.py`, `test_rof_features.py`) pod nowe dane RoF

### Zmienione
- `bot/cogs/recon.py`, `bot/cogs/economy.py`, `bot/cogs/attacks.py`, `bot/cogs/defense.py` — wrap+map_size z configu
- `app/map_sql/alerts.py`, `app/map_sql/collector.py`, `app/routes/attacks.py` — propagacja `wrap` przez pipeline alertów

## [0.2.2] — 2026-04-14

### Zmienione
- `docker-compose.yml` — przełączono z `build:` na `image: ghcr.io/peterpage2115/w.i.t.e.k:latest` (pull-based update zamiast ręcznego budowania)
- CI (`ci.yml`) — obraz Docker tagowany też wersją semver (`:vX.Y.Z`) obok `:latest` i `:sha`
- `docker-entrypoint.sh` — auto-kopia `config.example.yaml` → `config.yaml` przy pierwszym starcie jeśli brak
- `DEPLOY.md` — dodano sekcję "Aktualizacja" z instrukcją pull-based update i konwencją wersjonowania

## [0.2.1] — 2026-04-13

### Zmienione
- Zsynchronizowano `README.md`, `DEPLOY.md` i `CLAUDE.md` z aktualnym układem repo po pivotcie RoF-first
- Urealniono liczby w dokumentacji do bieżącego stanu repo: 9 cogów, 34 komendy slash i 882 testy pytest
- Zaktualizowano opisy domyślnego Docker runtime (`docker compose up -d`, `run.py --scheduled`, interwał collectora z YAML)
- Odświeżono przykłady tagów obrazów w `DEPLOY.md` pod cleanup release `0.2.1`

### Naprawione
- Usunięto lub przepisano odniesienia do starych, zduplikowanych ścieżek runtime po pivotcie RoF-first
- `docs/PLAN.md` przestał udawać aktywny plan — został oznaczony jako archiwum po zakończonym cleanupie
- `docs/ROADMAP.md` nie pokazuje już historycznie fałszywych wersji/liczb z epoki MVP
- Doprecyzowano zakres danych rozszerzenia w `PRIVACY.md` i opisach API (raporty bitewne, szpiegowskie, wojska, incomingi oraz `game-data`: hero / marketplace / training)

## [0.2.0] — 2026-04-12

### Naprawione
- Fix `_ensure_columns()` — dodano kompatybilność z PostgreSQL (wcześniej PRAGMA crashowało na PG)
- Fix spamowania alertów na Discord — jednorazowa migracja `discord_eligible` dla starych alertów
- Logging alertów — breakdown per typ w collector i per detektor w alerts.py

### Usunięte
- Modele deprecated: `MonitorSettings`, `PersonalAlert`, `NightWatchSetting` (oraz ich testy)
- Komendy: `/tmonitor`, `/tmonitor_ustawienia` (usunięte w Sprint 3, teraz też modele)
- Zależność: `alembic` z `requirements.txt`
- Pliki: `migrations/`, `scripts/apply_migrations.py`, `scripts/validate_rof_*.py`
- Pliki: `docs/superpowers/` (10 plików planistycznych — przeniesione do historii)
- Sekcja migracji z `docker-entrypoint.sh` (migracje teraz przez `_ensure_columns`)

### Zmienione
- Wersja: 0.1.0 → 0.2.0 (`pyproject.toml`)
- README.md — zaktualizowane komendy, architektura (9 cogów), liczba testów
- DEPLOY.md — dodano sekcję o systemie alertów
- CLAUDE.md — synchronizacja z aktualnym stanem kodu

## [0.1.0] — 2026-04-12

### Dodane
- Dashboard webowy z danymi graczy, sojuszy i wiosek
- Bot Discord z 26 komendami slash
- System alertów (spadek populacji, nowe wioski, zmiany sojuszy)
- Koordynacja obrony (wątki, garnizony, wsparcie)
- Kalkulatory taktyczne (bezpieczne wysyłanie, przechwycenie, symulacja bitwy)
- Parser map.sql z obsługą 16 pól (RoF: regiony, stolice, porty)
- Multi-server config (SERVER_PROFILE)
- Rozszerzenie Chrome do przechwytywania raportów
- Docker Compose (produkcja + dev + RoF)
- 853 testów pytest
- Moduł deep links do generowania linków w grze

### Naprawione
- Tribe ID bug — tid 8↔9 (Spartanie=8, Wikingowie=9)

