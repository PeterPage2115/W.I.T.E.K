# 🗺️ WITEK — Roadmap / Plan Rozwoju

> Wirtualny Informator Taktyczno-Ekonomiczny Koalicji
> Serwer: ts31.x3.europe.travian.com (x3 speed)

## ✅ Zrealizowane

### Faza 1 — Szkielet
- [x] Flask + Discord bot w jednym procesie
- [x] Parsowanie `map.sql` (publiczne dane wiosek)
- [x] Modele bazy: Snapshot, Village, Player, Alliance
- [x] Web dashboard (ciemny motyw Travian)
- [x] Docker Compose (dev: SQLite, prod: PostgreSQL)
- [x] Codzienny scheduler pobierania mapy

### Faza 2 — Tożsamość i Ataki
- [x] `/tlink`, `/tunlink`, `/twhoami` — łączenie kont Discord ↔ Travian
- [x] `/tatak` — zgłaszanie ataków (kordy atakującego wymagane)
- [x] `/tdodaj` — dodawanie ataków do istniejącego wątku
- [x] `/tataki` — lista aktywnych ataków
- [x] `/trozwiaz` — zamykanie zgłoszeń + archiwizacja wątku
- [x] Analiza podróży jednostek (prędkość x3, dystans torusowy)
- [x] Automatyczne wątki na forum #obrona

### Faza 3 — Obrona i Wojska
- [x] Parser raportów bitewnych (state machine, polski)
- [x] Normalizacja polskich nazw jednostek (tabela aliasów)
- [x] Zużycie zboża dla wszystkich jednostek (3 nacje + natura + bohater)
- [x] `/traport` — wklejanie raportów (modal)
- [x] `/twojska` — rejestracja wojsk w wiosce
- [x] `/twsparcie` — rejestracja wsparcia między wioskami
- [x] `/tstan` — stan obrony wioski (garnizon + wsparcie)
- [x] `/traporty` — lista raportów bitewnych
- [x] Modele: VillageTroops, TroopSupport, BattleReport
- [x] WAL mode dla SQLite (współbieżność)
- [x] Duplikacja raportów — detekcja SHA-256

## 🔧 W trakcie

### Faza 3.5 — Ulepszenia wątków obrony ✅
- [x] Edytowalny embed podsumowania w wątku (aktualizowany przy nowych atakach)
- [x] Lista atakowanych wiosek w głównej wiadomości (zamiast ikony nacji)
- [x] Ping roli @Def (gracze defensywni)
- [x] Usunięcie ikony nacji z embeda ataku
- [x] Reuse istniejących wątków (/tatak nie tworzy duplikatów)
- [x] Auto-detekcja koordynatów w wątku (/twojska, /twsparcie, /tstan, /tdodaj)
- [x] Szczegóły wsparcia w podsumowaniu (jednostki + zboże per wsparcie)
- [x] Auto-fill atakującego z koordynatów wioski źródłowej
- [x] Walidacja koordynatów celu w /tdodaj (muszą pasować do wątku)
- [ ] Poprawki parsera raportów (mobilne wsparcie)
- [ ] Wsparcie dla graczy mobilnych (`/traport_reczny`)

### Faza 4 — Koordynacja Defensywy (w toku)
- [x] Formuły Travian (dystans torusowy, czas podróży, prędkości jednostek x3)
- [x] `/tdef <kordy>` — kto z sojuszu może wysłać def, posortowane po ETA
- [ ] Automatyczne liczenie całkowitego defu w wątku (garnizon + wsparcie)

## 📋 Planowane

### Faza 4 — Koordynacja Defensywy (kontynuacja)
- [ ] Bilans zbożowy wioski pod obroną (produkcja vs zużycie)
- [ ] Powiadomienia o zbliżających się atakach (np. 30 min przed)
- [ ] Oznaczanie statusu ataku (reported → defending → resolved)

### Faza 5 — Dashboard Web
- [x] Wykresy historii populacji (Chart.js)
- [x] Strona szczegółów gracza (info + wykres + wioski)
- [x] Strona szczegółów sojuszu (info + wykres + członkowie)
- [ ] Mapa 2D wiosek (interaktywna, Canvas/SVG)
- [ ] Lista raportów bitewnych w przeglądarce
- [ ] Stan obrony wiosek — widok web
- [ ] Porównanie sojuszy (populacja, liczba graczy)
- [ ] Detekcja nieaktywnych graczy (brak wzrostu populacji >X dni)

### Faza 6 — Alerty i Automatyzacja
- [ ] Webhook: alerty o spadkach populacji (zniszczone wioski)
- [ ] Wykrywanie nowych wiosek wrogów w okolicy
- [ ] Automatyczne rozwiązywanie ataków po czasie uderzenia
- [ ] Raport dzienny: podsumowanie aktywności serwera

### Faza 7 — Zaawansowane
- [ ] Symulator bitwy (kalkulacja wyniku walki)
- [ ] Planner farm listy (wioski do grabieży)
- [ ] Kalkulator czasu budowy/badań
- [ ] Eksport danych do CSV/JSON

## 💡 Pomysły (do rozważenia)
- Integracja z Travian API (jeśli zadziała: travian4api)
- Bot do automatycznego skanowania raportów ze screenshotów (OCR)
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
│   └── routes/         # Blueprints web
├── bot/                # Discord bot (py-cord)
│   ├── bot.py          # create_bot(), db_query()
│   ├── utils.py        # Stałe, prędkości, zboże
│   └── cogs/           # Moduły komend
├── config/             # YAML config
├── tests/              # pytest
└── docker-compose.yml  # Produkcja (PostgreSQL)
```

## ⚙️ Kluczowe decyzje techniczne
- **Serwer x3**: prędkość wojsk ×2 (nie ×3!), produkcja ×3
- **db_query()**: Wszystkie zapytania DB w bocie przez executor (async safety)
- **Nigdy nie zwracać surowych modeli SQLAlchemy** z db_query() (detached session)
- **SQLite WAL mode**: dla współbieżności bot + Flask
- **map.sql**: publiczne dane, ~14k wiosek, bez autentykacji
