# WITEK — Sprint 2: Bugfixy + Nowe Ficzery

> **Data:** 2026-04-09  
> **Kontekst:** Serwer ts31.x3 (9 dni, wczesna faza), sojusz ~180 graczy  
> **Podejście:** Opcja B — bugfixy + parser razem → reszta sekwencyjnie

---

## Faza 1: Bugfixy + Ulepszony Parser Raportów

### 1.1 Duplikaty wątków obrony w forum

**Problem:** Wiele wątków w forum #obrona dla tej samej atakowanej wioski (np. 3 wątki dla 76|43).

**Rozwiązanie:**
- Przed tworzeniem nowego wątku → sprawdź `defense_threads` czy istnieje aktywny wątek dla danych koordynatów (defender_x, defender_y)
- Jeśli tak → dodaj nowy atak do istniejącego wątku (update embed + nowa wiadomość w wątku)
- Nowy wątek tylko gdy brak aktywnego lub poprzedni jest resolved/archived

**Pliki do zmiany:** `bot/cogs/attacks.py` — logika tworzenia wątków

### 1.2 Parser raportów — brakujące dane

**Problem:** `/traport` nie pokazuje zdobyczy (zasoby), siły walki ani kosztu zabitych.

**Brakujące pola:**
| Pole | Przykład z gry | Format |
|------|---------------|--------|
| Zdobycz (bounty) | `1322 drewna, 1320 gliny, 1322 żelaza, 1715 zboża` | 4 wartości |
| Pojemność zdobyczy | `5679/13455` | current/max |
| Siła w walce | `Napastnik: 20183, Obrońca: 530` | 2 wartości |
| Koszt zabitych | `Napastnik: 535, Obrońca: 0` | 2 wartości (w zasobach) |

**Rozwiązanie:**
- Rozszerz `smart_parse_report()` w `bot/cogs/defense.py` o nowe regex-y:
  - `zdobycz:?\s*([\d.]+)\s*/\s*([\d.]+)` lub per-surowiec
  - `[Ss]iła w walce:?\s*(\d+)\s*vs\.?\s*(\d+)`
  - `[Kk]oszt zabitych:?\s*(\d+)\s*vs\.?\s*(\d+)`
- Dodaj pola do embeda raportu:
  - Sekcja "🏆 Zdobycz" z ikonami surowców
  - Sekcja "⚔️ Siła walki" z porównaniem
  - Sekcja "💀 Koszt zabitych"

**Pliki do zmiany:** `bot/cogs/defense.py`, `bot/utils.py` (jeśli parser jest tam)

### 1.3 Puste nawiasy sojuszu

**Problem:** `[ ] Kolosik4` — puste nawiasy gdy gracz nie ma sojuszu.

**Rozwiązanie:** Warunek: jeśli `alliance_name` jest pusty/None → wyświetl sam nick bez nawiasów.

**Pliki do zmiany:** Wszędzie gdzie formatujemy `[alliance] player` — `bot/cogs/defense.py`, `bot/cogs/attacks.py`

### 1.4 Wersja + ROADMAP

- Bump wersji z `0.1.0` → `1.0.0` (mamy 10 cogów, 25+ komend, web dashboard — to 1.0!)
- Sync `docs/ROADMAP.md` z faktycznie zrealizowanymi funkcjami

**Pliki do zmiany:** `bot/cogs/general.py` (wersja), `docs/ROADMAP.md`

---

## Faza 2: Save Troops — `/tbezpieczne`

### Cel
Wyślij wojska na noc żeby nie dało się ich złapać atakiem.

### Logika
```python
# Wojska muszą wrócić po ilu godzinach gracz jest poza grą
# Minimum: dystans taki, że podróż TAM+WRACAM = czas_nieobecnosci
min_distance = (unit_speed * hours_away) / 2

# Na x3: speed_multiplier = 2
# Więc: min_distance = (base_speed * 2 * hours_away) / 2 = base_speed * hours_away

# Tournament Square zwiększa prędkość po 20 polach
# → dystans potrzebny jest MNIEJSZY z TS
```

### Komenda Discord
```
/tbezpieczne x:<int> y:<int> godziny:<float=8> [ts_level:<int=0>]
```

### Output (embed)
```
🌙 Bezpieczne Wysyłanie Wojsk
📍 Twoja wioska: Warszawka (76|43)
⏰ Czas nieobecności: 8 godzin

📊 Minimalna odległość per jednostka:
┌───────────────────┬────────────┐
│ Jednostka         │ Min. dist  │
├───────────────────┼────────────┤
│ Falanga (7)       │ 56 pól     │
│ Miecznik (6)      │ 48 pól     │
│ Druid (16)        │ 128 pól    │
│ TT Thunder (19)   │ 152 pól    │
└───────────────────┴────────────┘
* Prędkości uwzgl. mnożnik x3 serwera (×2)
* Z TS20 odległość może być mniejsza

🎯 Sugerowane cele (z map.sql):
1. "Wioska1" (120|80) — 52 pól — pop: 23 — NIEAKTYWNY
2. "Oazka" (60|90) — 55 pól — pop: 0 — oaza
```

### Logika sugestii celów
- Szukaj wiosek w map.sql w dystansie [min_dla_najwolniejszej, min_dla_najwolniejszej+10]
- Priorytet: nieaktywni gracze (0 growth), niska populacja, brak sojuszu
- Filtruj: nie nasi, nie pakty (jeśli mamy listę)

**Nowe pliki:** `bot/cogs/economy.py` (dodaj komendę) lub nowy cog `bot/cogs/tools.py`

---

## Faza 3: Defense Calculator — `/tileobrony`

### Cel
Oblicz ile obrony potrzeba, żeby przetrwać dany atak.

### Logika (formuły Travian)
```python
# Punkt wyjścia: formuły z bot/utils.py (UNIT_COMBAT)
# Atak: suma (attack_value * count) per jednostka
# Obrona: suma (defense_infantry lub defense_cavalry * count) + bonus muru

# Mur:
# Rzymski: base_def * (1.03^level)  — najsilniejszy
# Galijski: base_def * (1.025^level)
# Germański: base_def * (1.02^level)

# Moat/Rów (Galowie):
# Dodatkowy bonus do obrony piechoty

# Wzór na potrzebną obronę:
# needed_def = total_attack / wall_multiplier
# → ile jednostek: needed_def / unit_defense_value
```

### Komenda Discord
```
/tileobrony jednostka:<choice> ilosc:<int> [mur:<int=0>] [mur_typ:<Rzymski|Galijski|Germański>]
```

Opcjonalnie wersja zaawansowana z wieloma typami atakujących:
```
/tileobrony_multi opis:"500 Toporników, 200 Rycerzy, 50 Taranów" mur:15 mur_typ:Galijski
```

### Output (embed)
```
🛡️ Kalkulator Obrony
⚔️ Atak: 500 Toporników (Germanie)
    Siła ataku: 500 × 60 = 30,000

🏰 Mur: lvl 15 (Galijski) → bonus ×1.45
📊 Potrzebna obrona: 30,000 / 1.45 = 20,690

🛡️ Ile jednostek obronnych potrzeba:
┌───────────────────┬────────┬──────────┐
│ Jednostka         │ Def/szt│ Potrzeba │
├───────────────────┼────────┼──────────┤
│ Falanga (inf)     │ 40     │ 518      │
│ Druid (cav+inf)   │ 115    │ 180      │
│ Pretorianin (inf) │ 65     │ 319      │
│ Legionista (mix)  │ 35/30  │ 591      │
└───────────────────┴────────┴──────────┘

💡 Rekomendacja: Mix 200 Falang + 100 Druidów 
   + mur 15 powinien wystarczyć.
```

**Pliki do zmiany:** `bot/cogs/economy.py` lub nowy `bot/cogs/tools.py`, `bot/utils.py` (wall formulas)

---

## Faza 4: Interception Calculator — `/tprzechwyc`

### Cel
Złap wracającą armię wroga w jego wiosce (atak na pustą wioskę kiedy armia wraca).

### Logika
```python
# Scenariusz: wróg wysłał atak z (90|30) na (76|43)
# Znamy: czas uderzenia (ETA)
# Znamy (lub szacujemy): prędkość wroga → czas podróży wroga
# 
# czas_powrotu_wroga = ETA_ataku + czas_podrozy_wroga
# (bo po ataku armia wraca tą samą drogą)
#
# moj_czas_podrozy = travel_time(moje_coords, wrog_coords, moja_jednostka)
# moj_czas_wyslania = czas_powrotu_wroga - moj_czas_podrozy
#
# Jeśli moj_czas_wyslania < teraz → za późno!
```

### Komenda Discord
```
/tprzechwyc cel_x:<int> cel_y:<int> moje_x:<int> moje_y:<int> 
             eta_ataku:<HH:MM> [predkosc_wroga:<float>] [ts:<int=0>]
```

**Alternatywnie** z koordynatami celu ataku wroga (automatycznie oblicz prędkość):
```
/tprzechwyc wrog_x:90 wrog_y:30 cel_x:76 cel_y:43 moje_x:80 moje_y:50 eta:14:30
```

### Output (embed)
```
⚔️ Kalkulator Przechwycenia
🎯 Cel przechwycenia: (90|30) — wioska wroga
📍 Twoja wioska: (80|50)

⏰ ETA ataku wroga: 14:30
🔄 Szacowany powrót wroga: ~14:50 (20 min powrót)

📊 Kiedy wysłać Twoje jednostki:
┌───────────────────┬────────────┬──────────┬────────────┐
│ Jednostka         │ Czas podr. │ Wyślij o │ Status     │
├───────────────────┼────────────┼──────────┼────────────┤
│ TT Thunder (19)   │ 0h 42m     │ 14:08    │ ✅ Zdążysz │
│ Druid (16)        │ 0h 50m     │ 14:00    │ ✅ Zdążysz │
│ Eq. Caesaris (10) │ 1h 20m     │ 13:30    │ ✅ Zdążysz │
│ Falanga (7)       │ 1h 55m     │ 12:55    │ ⚠️ Mało    │
│ Miecznik (6)      │ 2h 13m     │ 12:37    │ ❌ Za późno │
└───────────────────┴────────────┴──────────┴────────────┘

💡 Wskazówka: Wyślij szybkie jednostki (konnicę) 
   żeby przechwycić wroga bez strat po stronie piechoty.
```

**Pliki do zmiany:** `bot/cogs/economy.py` lub `bot/cogs/tools.py`, `bot/utils.py`

---

## Multi-serwer

**Decyzja:** Osobna instancja per serwer (oddzielny Docker container z innym `.env`).

**Co trzeba:** 
- Upewnij się że `TRAVIAN_SERVER_URL`, `DISCORD_TOKEN`, `DISCORD_GUILD_ID` itp. są w `.env`
- Dokumentacja w `DEPLOY.md` jak uruchomić drugą instancję
- Brak zmian w kodzie — już wspiera to przez konfigurację

---

## Rozszerzenie przeglądarki (backlog — do przemyślenia)

**Pomysły:**
- Quick Report: przycisk przy raporcie → wysyła dane do WITEK
- Detekcja ataku: powiadomienie gdy widać incoming attack w grze
- Popup z kalkulatorami

**Status:** Do zaprojektowania osobno po zakończeniu tego sprintu.

---

## Kolejność implementacji

1. **Faza 1** — Bugfixy + parser (razem, bo powiązane)
2. **Faza 2** — `/tbezpieczne` (Save Troops)
3. **Faza 3** — `/tileobrony` (Defense Calculator)  
4. **Faza 4** — `/tprzechwyc` (Interception Calculator)

Każda faza: implementacja → testy → test na Discordzie → następna.
