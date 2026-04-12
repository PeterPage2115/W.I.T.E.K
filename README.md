# ⚔️ W.I.T.E.K — Wirtualny Informator Taktyczno-Ekonomiczny Koalicji

[![CI](https://github.com/PeterPage2115/W.I.T.E.K/actions/workflows/ci.yml/badge.svg)](https://github.com/PeterPage2115/W.I.T.E.K/actions/workflows/ci.yml)

Narzędzie analityczne sojuszu **Travian Legends** + bot Discord.
Nazwane na cześć H2P_Gucio (Witold Tacikiewicz).

---

## Co to jest?

W.I.T.E.K to narzędzie dla sojuszu UFOLODZY na serwerze Travian Legends, które:

- 🌐 **Dashboard webowy** — przeglądanie graczy, sojuszy, wiosek z danymi z map.sql
- 🤖 **Bot Discord** — komendy slash do koordynacji ataków, statystyk, łączenia kont
- 📊 **Automatyczne zbieranie danych** — codzienne pobieranie map.sql z serwera Travian
- 🚨 **System alertów** — powiadomienia o atakach na wioski sojuszu

## Szybki start

### 1. Sklonuj i skonfiguruj

```bash
git clone https://github.com/PeterPage2115/W.I.T.E.K.git
cd W.I.T.E.K
cp .env.example .env
cp config/config.example.yaml config/config.yaml
```

### 2. Uzupełnij konfigurację

Edytuj `.env` — wpisz token bota Discord, hasło i pozostałe wartości.
Edytuj `config/config.yaml` — wpisz ID swoich sojuszy.

### 3. Uruchom

```bash
# Produkcja (PostgreSQL)
docker compose up -d

# Deweloperski (SQLite)
docker compose -f docker-compose.dev.yml up -d
```

Dashboard: http://localhost:5000

📖 **Pełna instrukcja wdrożenia:** [DEPLOY.md](DEPLOY.md)

---

## Komendy Discord

| Komenda | Opis |
|---------|------|
| **ℹ️ Informacyjne** | |
| `/thelp` | Lista komend |
| `/tinfo` | Informacje o bocie + uptime |
| `/tstats` | Statystyki serwera (gracze, sojusze, top 5) |
| **🔐 Tożsamość** | |
| `/tlink <gracz>` | Połącz konto Discord z graczem Travian |
| `/tunlink` | Usuń połączenie |
| `/twhoami` | Pokaż połączony profil Travian |
| **⚔️ Ataki i Obrona** | |
| `/tatak` | Zgłoś atak na wioskę sojuszu (tworzy wątek obrony) |
| `/tdodaj` | Dodaj kolejny atak do istniejącego wątku |
| `/tataki` | Lista aktywnych ataków |
| `/trozwiaz` | Rozwiąż zgłoszenie ataku + archiwizacja wątku |
| `/twojska` | Zarejestruj garnizon wojsk w wiosce |
| `/twsparcie` | Zarejestruj wysłane wsparcie |
| `/tstan` | Stan obrony wioski (garnizon + wsparcie + zboże) |
| `/tdef` | Kto z sojuszu może wysłać def? (sortowane po ETA) |
| **📜 Raporty** | |
| `/traport` | Wklej raport bitewny (modal) |
| `/traporty` | Lista ostatnich raportów bitewnych |
| **🗺️ Rozpoznanie** | |
| `/tnieaktywni` | Znajdź nieaktywnych graczy w okolicy |
| `/tcropper` | Szukaj cropperów (9c/15c) w zasięgu |
| `/tszukaj` | Wyszukaj wioski po nazwie, graczu, sojuszu |
| `/tporownaj` | Porównaj dwa sojusze (populacja, wioski, top gracze) |
| **🧮 Kalkulatory taktyczne** | |
| `/tbezpieczne` | Bezpieczne wysyłanie — minimalna odległość na czas nieobecności |
| `/tileobrony` | Ile obrony potrzeba na daną armię atakującą |
| `/tprzechwyc` | Kalkulator przechwycenia — kto zdąży wysłać def |
| `/tsymulacja` | Symulator bitwy (modal) |
| **📊 Monitoring** | |
| `/tdigest` | Tygodniowe podsumowanie zmian sojuszu |
| `/tmonitor` | Włącz/wyłącz monitoring wiosek (alerty DM) |
| `/tmonitor_ustawienia` | Ustaw progi monitoringu |

## Funkcje dashboardu

- 📋 Lista graczy z sortowaniem i wyszukiwaniem
- 🏘️ Szczegóły wiosek każdego gracza
- 🏛️ Przegląd sojuszy i ich członków
- 📈 Statystyki serwera (populacja, liczba graczy)
- 🗺️ Historia snapshotów map.sql
- 🔒 Strefa sojuszu zabezpieczona hasłem

## Architektura

```
run.py                  # Punkt wejścia: Flask + bot + scheduler
├── app/                # Aplikacja Flask (dashboard)
│   ├── models.py       # Modele: Snapshot, Village, Player, Alliance
│   ├── map_sql/        # Parser + kolektor danych Travian
│   ├── routes/         # Blueprinty: dashboard, gracze, sojusze
│   └── templates/      # Szablony Jinja2 (styl Travian)
├── bot/                # Bot Discord (py-cord)
│   ├── bot.py          # Fabryka bota + db_query()
│   └── cogs/           # 10 kogów z komendami slash
├── config/             # Konfiguracja YAML
└── tests/              # 853+ testów pytest
```

### Multi-server (RoF)

W.I.T.E.K obsługuje wiele serwerów Travian jednocześnie. Konfiguracja przez `SERVER_PROFILE`:

```bash
# RoF x3 International
docker compose --env-file .env.rof -f docker-compose.rof.yml up -d
```

Konfiguracja serwerów w `config/config.yaml` pod kluczem `servers:`.

## Uruchomienie lokalne (bez Dockera)

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -r requirements.txt
python run.py             # Flask + bot (jeśli DISCORD_TOKEN ustawiony)
```

## Testy

```bash
python -m pytest tests/ -v
```

## Technologie

- **Backend**: Flask, SQLAlchemy
- **Bot**: py-cord (Pycord)
- **Baza**: PostgreSQL (prod) / SQLite (dev)
- **Scheduler**: APScheduler
- **Docker**: Multi-stage build, Docker Compose

---

*⚔️ W.I.T.E.K — Na cześć Gucio*
