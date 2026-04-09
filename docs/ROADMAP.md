# 🗺️ WITEK — Roadmap / Plan Rozwoju

> Wirtualny Informator Taktyczno-Ekonomiczny Koalicji
> Serwer: ts31.x3.europe.travian.com (x3 speed)
> Wersja: **1.0.0** | 357 testów ✅ | 10 cogów | 25+ komend

## ✅ Zrealizowane

### Slice 1 — Szkielet i Dane
- [x] Flask + Discord bot w jednym procesie (`run.py`)
- [x] Parsowanie `map.sql` (publiczne dane ~14k wiosek)
- [x] Modele bazy: Snapshot, Village, Player, Alliance, User
- [x] Web dashboard (ciemny motyw Travian, MedievalSharp)
- [x] Docker Compose dev (SQLite) + prod (PostgreSQL)
- [x] Codzienny scheduler pobierania mapy

### Slice 2 — Tożsamość i Ataki
- [x] `/tlink`, `/tunlink`, `/twhoami` — łączenie kont Discord ↔ Travian
- [x] `/tatak` — zgłaszanie ataków z auto-wątkami na #obrona
- [x] `/tdodaj` — dodawanie ataków do istniejącego wątku
- [x] `/tataki` — lista aktywnych ataków
- [x] `/trozwiaz` — zamykanie zgłoszeń + archiwizacja wątku
- [x] Analiza podróży jednostek (prędkość x3, dystans torusowy)
- [x] Ping roli @Def, reuse wątków, auto-detekcja koordynatów

### Slice 3 — Obrona i Wojska
- [x] Parser raportów bitewnych (state machine, polski)
- [x] Normalizacja polskich nazw jednostek (tabela aliasów)
- [x] Zużycie zboża dla wszystkich jednostek (3 nacje + natura + bohater)
- [x] `/traport` — wklejanie raportów (modal) + `/traport_reczny`
- [x] `/twojska` — rejestracja wojsk w wiosce
- [x] `/twsparcie` — rejestracja wsparcia między wioskami
- [x] `/tstan` — stan obrony wioski (garnizon + wsparcie)
- [x] Modele: VillageTroops, TroopSupport, BattleReport, AttackReport
- [x] WAL mode dla SQLite + duplikacja raportów (SHA-256)

### Slice 4 — Koordynacja Defensywy
- [x] Formuły Travian (dystans torusowy, czas podróży, prędkości jednostek x3)
- [x] `/tdef <kordy>` — kto z sojuszu może wysłać def, posortowane po ETA
- [x] Edytowalny embed podsumowania w wątku (aktualizowany przy nowych atakach)
- [x] Szczegóły wsparcia w podsumowaniu (jednostki + zboże per wsparcie)

### Slice 5 — Rozpoznanie, Symulacja i Dashboard
- [x] `/tsymulacja` — symulator bitwy (kalkulacja wyniku walki)
- [x] `/tporownaj` — porównanie sojuszy
- [x] `/tcropper` — wyszukiwanie cropperów (9c/15c)
- [x] `/tdigest` — dzienne podsumowanie zmian na serwerze
- [x] `/tszukaj` — wyszukiwanie graczy/wiosek
- [x] `/tnieaktywni` — detekcja nieaktywnych graczy
- [x] `/tstats` — statystyki serwera (gracze, sojusze, top 5)
- [x] `/tinfo` — info o bocie + uptime
- [x] `/thelp` — lista komend
- [x] Mapa 2D wiosek (interaktywna, Canvas)
- [x] Web: Dashboard (/), Attacks (/attacks), Defense (/defense), Map (/map)
- [x] Web: Profile graczy i sojuszy z wykresami populacji (Chart.js)
- [x] 10 cogów: alerts, attacks, defense, digest, economy, general, identity, recon, monitor, simulator
- [x] 357 testów pytest ✅

## 🔧 W trakcie (Sprint 2)

### Kalkulatory taktyczne
- [ ] `/tbezpieczne` — kalkulator bezpiecznego wysyłania surowców
- [ ] `/tileobrony` — ile obrony potrzeba na daną armię
- [ ] `/tprzechwyc` — kalkulator przechwytywania ataków (timing)

### Poprawki i ulepszenia
- [ ] Bugfixy parsera raportów (edge cases, mobilne wsparcie)
- [ ] Enhanced parser — lepsza obsługa formatów raportów
- [ ] Bilans zbożowy wioski pod obroną (produkcja vs zużycie)

## 📋 Planowane

### Bezpieczeństwo i deploy
- [ ] Discord OAuth do dashboardu web
- [ ] RBAC — role-based access control (lider/oficer/członek)
- [ ] Deploy produkcyjny (VPS + domena + HTTPS)

### Automatyzacja
- [ ] Powiadomienia o zbliżających się atakach (np. 30 min przed)
- [ ] Automatyczne rozwiązywanie ataków po czasie uderzenia
- [ ] Webhook: alerty o spadkach populacji (zniszczone wioski)

### Rozszerzenia
- [ ] Browser extension do importu raportów z gry
- [ ] Eksport danych do CSV/JSON
- [ ] Planner farm listy (wioski do grabieży)

## 💡 Pomysły (do rozważenia)
- Integracja z Travian API (travian4api)
- OCR — skanowanie raportów ze screenshotów
- System rankingowy graczy w sojuszu
- Kalkulator artefaktów i bonusów
- System rotacji obrony (grafik dyżurów)
- Powiadomienia push na telefon (przez Discord)

## 🏗️ Architektura
```
run.py                  # Flask + bot + scheduler
├── app/                # Flask (dashboard + API)
│   ├── models.py       # SQLAlchemy modele
│   ├── map_sql/        # Parser map.sql
│   └── routes/         # Blueprints web (dashboard, players, alliances, attacks, defense, map)
├── bot/                # Discord bot (py-cord)
│   ├── bot.py          # create_bot(), db_query()
│   ├── utils.py        # Stałe, prędkości, zboże
│   └── cogs/           # 10 modułów komend
├── config/             # YAML config
├── tests/              # 357 testów pytest
└── docker-compose.yml  # Produkcja (PostgreSQL)
```

## ⚙️ Kluczowe decyzje techniczne
- **Serwer x3**: prędkość wojsk ×2 (nie ×3!), produkcja ×3
- **db_query()**: Wszystkie zapytania DB w bocie przez executor (async safety)
- **Nigdy nie zwracać surowych modeli SQLAlchemy** z db_query() (detached session)
- **SQLite WAL mode**: dla współbieżności bot + Flask
- **map.sql**: publiczne dane, ~14k wiosek, bez autentykacji
