# ⚔️ W.I.T.E.K — Wirtualny Informator Taktyczno-Ekonomiczny Koalicji

[![CI](https://github.com/PeterPage2115/W.I.T.E.K/actions/workflows/ci.yml/badge.svg)](https://github.com/PeterPage2115/W.I.T.E.K/actions/workflows/ci.yml)

Narzędzie analityczne dla Travian Legends: dashboard Flask, bot Discord oraz opcjonalne API/rozszerzenie do ręcznego importu raportów z gry.

---

## Aktualny snapshot repo

- 🌋 **RoF-first** — domyślny profil to `rof-x3`
- 🤖 **9 cogów / 34 komendy slash** w bocie Discord
- 🌐 **12 modułów tras Flask** dla dashboardu i API
- ✅ **882 testy pytest** w aktualnym repo
- 🐳 **Docker prod + dev** — `docker-compose.yml` (PostgreSQL) i `docker-compose.dev.yml` (SQLite)
- 🗂️ **Klasyczny preset** został odłożony do `legacy\ts31\`

## Co to jest?

W.I.T.E.K przygotowany jest domyślnie pod **RoF x3** i łączy kilka narzędzi w jednym projekcie:

- 🌐 **Dashboard webowy** — gracze, sojusze, wioski, alerty, dyplomacja, wyszukiwanie
- 🤖 **Bot Discord** — koordynacja ataków i obrony, kalkulatory, statystyki, profile graczy
- 📊 **Kolektor `map.sql`** — automatyczne pobieranie snapshotów serwera Travian
- 🚨 **Alerty mapowe** — `pop_drop`, `new_village`, `alliance_change`
- 🧩 **API + rozszerzenie Chrome** — ręczne wysyłanie raportów bitewnych, szpiegowskich, wojsk, incomingów oraz danych `hero` / `marketplace` / `training`

## Szybki start

### 1. Sklonuj i skonfiguruj

```bash
git clone https://github.com/PeterPage2115/W.I.T.E.K.git
cd W.I.T.E.K
cp .env.example .env
cp config/config.example.yaml config/config.yaml
```

### 2. Uzupełnij konfigurację

- `.env.example` jest teraz **jedynym** aktywnym szablonem środowiska dla całego repo
- Domyślny profil repo to `SERVER_PROFILE=rof-x3`
- Jeśli chcesz zrobić tylko chwilowy smoke test na x10, ustaw tymczasowo:

```bash
TRAVIAN_SERVER_URL=https://rof.x10.international.travian.com
```

- Po teście usuń override i wróć do `rof-x3`
- Archiwalny preset starego świata znajdziesz w `legacy\ts31\`
- W `config/config.yaml` wpisz przede wszystkim `servers.rof-x3.our_alliances`

### 3. Uruchom

```bash
# Produkcja / domyślny stack RoF-first (PostgreSQL)
docker compose up -d

# Deweloperski stack (SQLite + bind mount kodu)
docker compose -f docker-compose.dev.yml up -d
```

Domyślny obraz startuje komendą `python run.py --scheduled --port 5000`, więc razem ruszają:

- dashboard Flask,
- bot Discord (jeśli `DISCORD_TOKEN` jest ustawiony),
- scheduler `map.sql` z interwałem z `scheduler.fetch_interval_minutes` (domyślnie 60 min).

Dashboard: http://localhost:5000

📖 **Pełna instrukcja wdrożenia:** [DEPLOY.md](DEPLOY.md)

## Uruchomienie lokalne (bez Dockera)

```bash
python -m venv venv
venv\Scripts\activate     # Windows
# source venv/bin/activate  # Linux / macOS
pip install -r requirements.txt
python run.py --scheduled
```

## Komendy Discord (34)

| Komenda | Opis |
|---------|------|
| **ℹ️ Informacyjne** | |
| `/thelp` | Wyświetla listę komend W.I.T.E.K |
| `/tinfo` | Informacje o bocie W.I.T.E.K |
| `/tstats` | Szybkie statystyki serwera Travian |
| **🔐 Tożsamość i profile** | |
| `/tlink <gracz>` | Powiąż swoje konto Discord z graczem Travian |
| `/tunlink` | Usuń powiązanie Discord ↔ Travian |
| `/twhoami` | Pokaż powiązany profil Travian |
| `/tprofil` | Pokaż profil gracza Travian |
| **⚔️ Ataki i koordynacja obrony** | |
| `/tatak` | Zgłoś atak na wioskę koalicji |
| `/tdodaj` | Dodaj atak do istniejącego wątku obrony |
| `/tataki` | Lista aktywnych ataków na sojusz |
| `/trozwiaz` | Zamknij zgłoszenie ataku i archiwizuj wątek |
| `/tdef` | Kto może wysłać def? Lista wiosek sojuszu z ETA |
| `/traport` | Wklej raport bitewny z gry |
| `/traport_reczny` | Ręczne dodanie raportu (np. z telefonu) |
| `/traporty` | Lista raportów bitewnych |
| `/twojska` | Zarejestruj wojska w wiosce |
| `/twsparcie` | Zarejestruj wysłane wsparcie |
| `/tstan` | Pokaż stan obrony wioski (wojska + wsparcie) |
| `/tzboza` | Bilans zbożowy wioski (zużycie vs produkcja) |
| **🗺️ Rozpoznanie i ekonomia** | |
| `/tenemy` | Szukaj wrogów w okolicy (pomija sojusze i pakty) |
| `/tnieaktywni` | Szukaj nieaktywnych graczy w okolicy |
| `/tcropper` | Znajdź croppery (9c/15c) w okolicy |
| `/tszukaj` | Szukaj wiosek w okolicy |
| `/tporownaj` | Porównaj dwa sojusze |
| **🧮 Kalkulatory taktyczne** | |
| `/tsymulacja` | Symulacja walki — oblicz straty |
| `/tbezpieczne` | Kalkulator bezpiecznego wysyłania (min. odległość) |
| `/tileobrony` | Kalkulator obrony — ile wojsk potrzeba do odparcia ataku |
| `/tprzechwyc` | Kalkulator przechwycenia — kiedy wysłać def |
| `/tbuildtime` | Kalkulator czasu treningu — oblicz czas i koszt szkolenia jednostek |
| `/ttraining` | Kalkulator szkolenia — czas i surowce dla jednostek |
| **📊 Podsumowania** | |
| `/tdigest` | Podsumowanie tygodnia sojuszu |
| **🕊️ Dyplomacja** | |
| `/tdyplomacja` | Pokaż relacje dyplomatyczne |
| `/tdodaj_relacje` | Dodaj relację dyplomatyczną |
| `/tusun_relacje` | Usuń relację dyplomatyczną |

## Funkcje aplikacji

- 📋 Lista graczy, sojuszy i wiosek z filtrowaniem
- 🔍 Szybkie wyszukiwanie graczy i sojuszy
- ⚔️ Widoki ataków, wątków obrony i raportów bitewnych
- 🔔 Alerty z historii snapshotów (`pop_drop`, `new_village`, `alliance_change`)
- 🕊️ Dyplomacja — relacje między sojuszami na dashboardzie i w bocie
- 🗺️ Profil serwera przez `SERVER_PROFILE` + tymczasowy override `TRAVIAN_SERVER_URL`
- 🔐 Strefa sojuszu chroniona hasłem + opcjonalny login Discord OAuth
- 🧩 API rozszerzenia (`/api/ext/report`, `/api/ext/spy-report`, `/api/ext/troops`, `/api/ext/incoming`, `/api/ext/game-data`)

## Architektura

```
run.py                  # CLI / entrypoint: Flask, bot, collector, tryb scheduled
├── app/                # Dashboard Flask + API
│   ├── map_sql/        # Parser, collector i alerty map.sql
│   ├── routes/         # 12 modułów: alerts_web, alliances, api_ext, attacks,
│   │                   # auth, dashboard, defense, diplomacy, map, players,
│   │                   # reports, search
│   └── templates/      # Szablony Jinja2
├── bot/                # Bot Discord (py-cord)
│   ├── cogs/           # 9 cogów / 34 komendy slash
│   ├── deep_links.py   # Linki do gry Travian
│   ├── tribes.py       # Źródło prawdy dla nacji i jednostek
│   └── utils.py        # Dystans, prędkości, crop, parsowanie czasu
├── extension/          # Rozszerzenie Chrome + relay do API
├── server_profile.py   # Loader profilu serwera
├── docker-compose.yml  # Domyślny stack prod (PostgreSQL)
├── docker-compose.dev.yml # Stack dev (SQLite)
└── tests/              # 882 testy pytest
```

## Testy

```bash
python -m pytest tests/ -q
```

Aktualny stan repo: **882 testy przechodzą lokalnie**.

## Technologie

- **Backend**: Flask, SQLAlchemy
- **Bot**: py-cord
- **Baza**: PostgreSQL (domyślny Docker) / SQLite (dev)
- **Scheduler**: APScheduler
- **Rozszerzenie**: Chrome Extension (Manifest V3)
- **Deploy**: Docker Compose + opcjonalnie GHCR

---

*⚔️ W.I.T.E.K — Na cześć H2P_Gucio*


