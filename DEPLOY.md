# W.I.T.E.K — Przewodnik wdrożenia

Kompletna instrukcja uruchomienia W.I.T.E.K w aktualnym układzie **RoF-first**.

---

## Co uruchamia domyślny stack

`docker compose up -d` to dziś **jedyny domyślny stack produkcyjny** repo:

- `docker-compose.yml` — Flask + bot + scheduler + PostgreSQL
- profil serwera: `SERVER_PROFILE=rof-x3`
- start aplikacji: `python run.py --scheduled --port 5000`
- kolektor `map.sql`: interwał z `scheduler.fetch_interval_minutes` (domyślnie 60 min)

RoF to standardowy tryb działania repo — korzystasz po prostu z domyślnego stacku produkcyjnego.

---

## 📋 Wymagania

| Składnik | Wersja | Uwagi |
|----------|--------|-------|
| Docker | 24+ | `docker --version` |
| Docker Compose | v2+ | Wbudowany w Docker Desktop / plugin CLI |
| Git | — | Do pobrania repozytorium |
| Token bota Discord | opcjonalny dla web-only smoke, wymagany dla bota | Discord Developer Portal |
| Serwer / VPS | — | Min. 512 MB RAM, otwarty port 5000 (lub inny z `WITEK_PORT`) |

---

## ⚙️ Konfiguracja

### 1. Sklonuj repozytorium

```bash
git clone https://github.com/PeterPage2115/W.I.T.E.K.git
cd W.I.T.E.K
```

### 2. Utwórz `.env`

```bash
cp .env.example .env
```

`.env.example` jest teraz głównym szablonem dla całego repo.

| Zmienna | Czy wymagana | Opis |
|---------|--------------|------|
| `FLASK_SECRET_KEY` | ✅ | Sekret sesji Flask |
| `ALLIANCE_PASSWORD` | ✅ | Hasło strefy sojuszu |
| `DISCORD_TOKEN` | ⚠️ | Wymagany, jeśli ma wystartować bot |
| `DISCORD_GUILD_ID` | ⚠️ | Potrzebny dla slash komend i integracji Discord |
| `DISCORD_ALERTS_CHANNEL_ID` | ⚠️ | Kanał alertów mapowych |
| `DISCORD_DEFENSE_FORUM_ID` | ⚠️ | Forum do wątków obrony |
| `DISCORD_DEF_ROLE_ID` | ⚠️ | Rola pingowana przy obronie |
| `DISCORD_CLIENT_ID` | opcjonalny | Login Discord OAuth do dashboardu |
| `DISCORD_CLIENT_SECRET` | opcjonalny | Sekret OAuth |
| `DISCORD_REDIRECT_URI` | opcjonalny | Callback OAuth, np. `http://localhost:5000/auth/callback` |
| `SERVER_PROFILE` | ✅ | Aktywny profil serwera, domyślnie `rof-x3` |
| `TRAVIAN_SERVER_URL` | opcjonalny | Tymczasowy override URL `map.sql` (np. smoke test x10) |
| `EXT_API_TOKEN` | opcjonalny | Włącza API rozszerzenia Chrome |
| `DATABASE_URL` | zwykle puste | Poza Dockerem: puste = SQLite, w Dockerze nadpisywane automatycznie |
| `POSTGRES_DB` | ✅ dla domyślnego compose | Nazwa bazy PostgreSQL, domyślnie `witek_rof` |
| `POSTGRES_USER` | ✅ dla domyślnego compose | Użytkownik PostgreSQL |
| `POSTGRES_PASSWORD` | ✅ dla domyślnego compose | Hasło PostgreSQL |
| `WITEK_PORT` | opcjonalny | Port publikowany przez Docker, domyślnie `5000` |

### 3. Utwórz konfigurację YAML

```bash
cp config/config.example.yaml config/config.yaml
```

Najważniejsze ustawienia w `config/config.yaml`:

```yaml
servers:
  rof-x3:
    our_alliances: [123, 456]

scheduler:
  fetch_interval_minutes: 60

alerts:
  pop_drop_threshold: 25
  min_pop_for_alerts: 500
  alert_cooldown_hours: 6
  new_village_radius: 30
```

Archiwalny preset klasycznego świata znajdziesz w `legacy\ts31\`.

---

## 🚀 Uruchomienie

### Produkcja / domyślny Docker (PostgreSQL)

```bash
docker compose up -d --build
```

Co dostajesz:

- dashboard na `http://localhost:5000` (lub porcie z `WITEK_PORT`),
- PostgreSQL w kontenerze `witek-rof-db`,
- bota Discord, jeśli ustawiono `DISCORD_TOKEN`,
- scheduler `map.sql` uruchomiony przez `run.py --scheduled`.

> **Ważne:** domyślny stack używa nazw RoF (`witek-rof-app`, `witek-rof-db`, `witek-rof-pgdata`) oraz bazy `witek_rof`, żeby nie mieszać danych nowego świata ze starym stackiem `witek-*`. Jeśli aktualizujesz dawny deployment `witek-app` / `witek-db` / `witek-pgdata`, samo `docker compose up -d --build` uruchomi nowy, pusty stack — to **nie** jest inplace upgrade. Najpierw zrób backup starej bazy i zdecyduj, czy chcesz czysty start, czy ręczne odtworzenie danych do `witek_rof`.

### Deweloperski stack (SQLite)

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

Tryb dev używa:

- SQLite (`witek.db`),
- bind mountów kodu,
- `FLASK_DEBUG=true`,
- tego samego entrypointu i trybu `--scheduled`.

### Tymczasowy smoke test na x10

Jeśli chcesz tylko sprawdzić pobieranie `map.sql` przed live RoF x3:

```bash
# w .env ustaw tymczasowo
TRAVIAN_SERVER_URL=https://rof.x10.international.travian.com
```

Po teście usuń override, aby wrócić do profilu `rof-x3`.

### Sprawdzenie statusu

```bash
docker compose ps
docker compose logs -f witek-app
docker compose logs witek-db
```

---

## 🎯 Pierwsze kroki po starcie

### 1. Zaproś bota na serwer Discord

W Discord Developer Portal ustaw:

- Scopes: `bot`, `applications.commands`
- Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Use Slash Commands`, `Create Public Threads`

### 2. Skonfiguruj kanały i role

- kanał alertów (`DISCORD_ALERTS_CHANNEL_ID`),
- forum obrony (`DISCORD_DEFENSE_FORUM_ID`),
- rolę obrońców (`DISCORD_DEF_ROLE_ID`).

### 3. Pierwszy snapshot `map.sql`

W trybie `--scheduled` aplikacja sama pobierze snapshot przy starcie, jeśli baza jest pusta. Możesz też wymusić pobranie ręcznie:

```bash
docker compose exec witek-app python run.py --collect
```

### 4. Alerty mapowe

| Typ alertu | Opis | Discord? |
|------------|------|----------|
| `pop_drop` | Spadek populacji gracza ≥ próg | ✅ Tak |
| `new_village` | Nowa niealiancka wioska w pobliżu | ❌ Dashboard only |
| `alliance_change` | Wejście / wyjście / zmiana sojuszu | ❌ Dashboard only |

### 5. API rozszerzenia Chrome (opcjonalnie)

Ustaw `EXT_API_TOKEN`, jeśli chcesz używać rozszerzenia do ręcznego importu danych z gry (raporty, wojska, incomingi oraz dane `hero` / `marketplace` / `training`). Aktualne endpointy:

- `POST /api/ext/report`
- `POST /api/ext/spy-report`
- `POST /api/ext/troops`
- `POST /api/ext/incoming`
- `POST /api/ext/game-data`

### 6. Dashboard i OAuth

- podstawowy dostęp do strefy sojuszu działa przez hasło,
- login Discord OAuth wymaga `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`.

---

## 🔄 Aktualizacja

Poniższa procedura dotyczy istniejącego stacku `witek-rof-*`.

```bash
git pull
docker compose up -d --build
```

Dane PostgreSQL są trzymane w wolumenie `witek-rof-pgdata`, więc sama aktualizacja nie usuwa bazy.

> **Uwaga:** Migracje schematu są wykonywane przy starcie aplikacji przez `_ensure_columns()`. Nie ma potrzeby uruchamiania osobnych skryptów migracyjnych.

### Migracja ze starego stacku `witek-*`

Jeśli przechodzisz ze starego deploymentu o nazwach `witek-app` / `witek-db` / `witek-pgdata`, potraktuj ten release jak migrację do nowej przestrzeni danych:

```bash
# 1. Zrób backup starej bazy
docker compose exec -T witek-db pg_dump -U witek witek > backup_old_stack.sql

# 2. Zatrzymaj stary stack
docker compose down

# 3. Wstań na nowym RoF-first stacku
docker compose up -d --build

# 4. Opcjonalnie odtwórz backup do nowej bazy RoF
docker compose exec -T witek-db psql -U witek witek_rof < backup_old_stack.sql
```

Jeśli nie chcesz przenosić danych ze starego świata, pomiń krok 4 i zacznij od czystej bazy `witek_rof`.

---

## 💾 Backup i przywracanie

### Backup PostgreSQL

```bash
docker compose exec -T witek-db pg_dump -U witek witek_rof > backup_$(date +%Y%m%d).sql
```

### Przywracanie

```bash
docker compose exec -T witek-db psql -U witek witek_rof < backup.sql
```

### Cron / harmonogram backupu (przykład Linux)

```bash
0 3 * * * docker compose exec -T witek-db pg_dump -U witek witek_rof > /backups/witek_$(date +\%Y\%m\%d).sql
```

---

## 🐛 Troubleshooting

### Bot nie wystartował

- sprawdź `DISCORD_TOKEN`,
- sprawdź `docker compose logs witek-app | grep -i discord`,
- jeśli chcesz tylko smoke test webu, brak tokena jest dozwolony — bot po prostu nie ruszy.

### Brak danych na dashboardzie

- sprawdź `SERVER_PROFILE` i ewentualny `TRAVIAN_SERVER_URL`,
- wymuś pobranie: `docker compose exec witek-app python run.py --collect`,
- sprawdź logi: `docker compose logs witek-app | grep -i collect`.

### Scheduler działa inaczej niż oczekiwano

- interwał ustawia `scheduler.fetch_interval_minutes` w `config/config.yaml`,
- domyślna wartość repo to `60`, a nie „raz dziennie”.

### Błędy bazy danych

- `docker compose ps witek-db`
- sprawdź `POSTGRES_*` w `.env`,
- pełny reset danych: `docker compose down -v && docker compose up -d`.

### Port zajęty

Zmień `WITEK_PORT` w `.env`, np. na `8080`.

---

## 📦 Docker Registry (opcjonalnie)

### Logowanie do GHCR

```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u peterpage2115 --password-stdin
```

### Budowanie i publikacja

```bash
docker build -t ghcr.io/peterpage2115/w.i.t.e.k:latest .
docker push ghcr.io/peterpage2115/w.i.t.e.k:latest

docker build -t ghcr.io/peterpage2115/w.i.t.e.k:0.2.1 .
docker push ghcr.io/peterpage2115/w.i.t.e.k:0.2.1
```

### Użycie gotowego obrazu w compose

```yaml
services:
  witek-app:
    image: ghcr.io/peterpage2115/w.i.t.e.k:0.2.1
    # usuń / zakomentuj sekcję build:
    # build:
    #   context: .
    #   dockerfile: Dockerfile
```

---

## 📁 Struktura plików

```
.env.example            # Jedyny aktywny template środowiska
config/config.example.yaml
docker-compose.yml      # Domyślny stack prod (RoF-first)
docker-compose.dev.yml  # Stack dev (SQLite)
Dockerfile              # Obraz uruchamia run.py --scheduled
app/                    # Flask dashboard + API
bot/                    # Discord bot
extension/              # Chrome extension
tests/                  # Testy pytest
legacy/ts31/            # Archiwum klasycznego presetu
```

---

*⚔️ W.I.T.E.K — Na cześć H2P_Gucio*



