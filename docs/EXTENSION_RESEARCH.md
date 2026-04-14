# Badanie: TravianResourceBarPlus vs W.I.T.E.K Extension

## Kontekst

Analiza userscriptu [TravianResourceBarPlus](https://github.com/adipiciu/Travian-scripts/blob/main/TravianResourceBarPlus/TravianResourceBarPlus.user.js) pod kątem funkcji, które moglibyśmy dodać do rozszerzenia W.I.T.E.K.

## TravianResourceBarPlus — przegląd

- **Rozmiar**: ~466 KB monolityczny userscript (Tampermonkey/Greasemonkey)
- **Licencja**: GPL-3.0
- **Architektura**: Manipulacja DOM Traviana, odczyt zmiennych JS z `window.Travian.*`
- **Języki**: 26+ tłumaczeń (w tym polski)

### Główne funkcje

| Funkcja | Opis | Trudność implementacji |
|---------|------|----------------------|
| Resource Bar | Pasek zasobów z produkcją/h na górze ekranu | 🟡 Średnia |
| Village Overview | Lista wszystkich wiosek z zasobami | 🔴 Wysoka |
| Crop Balance | Ostrzeżenie gdy zboże < 0 | 🟢 Niska |
| Distance Calculator | Kalkulator odległości z mapy | ✅ Mamy już |
| Village Notes | Notatki per wioska | 🟡 Średnia |
| Attack Tracking | Śledzenie nadchodzących ataków | ✅ Mamy już |
| Troop Resource Calc | Koszt wojsk w zasobach | ✅ Mamy (bot /tbuildtime) |

## Co mamy teraz w rozszerzeniu W.I.T.E.K

Aktualna wersja 0.2.1 — **detector.js** wykrywa strony Traviana i dodaje przycisk "Wyślij do W.I.T.E.K":

- **Raporty bitewne** → POST `/api/ext/report`
- **Raporty szpiegowskie** → POST `/api/ext/spy-report`
- **Punkt zbiórki** (nadchodzące ataki) → POST `/api/ext/incoming`
- **Wioska** (zasoby, produkcja) → POST `/api/ext/game-data`
- **Bohater** (statystyki) → POST `/api/ext/game-data`
- **Rynek** (oferty handlowe) → POST `/api/ext/game-data`
- **Koszary/Stajnia** (kolejka treningowa) → POST `/api/ext/game-data`

## Funkcje warte dodania (priorytet)

### 1. 🟢 Crop Balance Warning (łatwe)
**Co**: Odczyt aktualnej produkcji zboża z DOM (`dorf1.php`), alert gdy bilans < 0.
**Jak**: Content script już parsuje `dorf1.php` — wystarczy dodać logikę sprawdzania.
**Gdzie**: Overlay na stronie Traviana (badge na ikonce rozszerzenia).
**Wysiłek**: ~2h

### 2. 🟡 Resource Bar Overlay (średnie)
**Co**: Mały pasek na górze ekranu Traviana pokazujący zasoby + produkcję/h dla aktywnej wioski.
**Jak**: Content script odczytuje `#stockBar` DOM, wstrzykuje dodatkowy element HTML z produkcją/h.
**Problem**: Travian już pokazuje zasoby — value add to głównie **produkcja/h** i **czas do pełnego magazynu**.
**Wysiłek**: ~4h

### 3. 🟡 Village Notes (średnie)
**Co**: Notatki tekstowe per wioska, zapisywane w `chrome.storage.local`.
**Jak**: Content script dodaje ikonkę notatki obok nazwy wioski, popup z textarea.
**Backend**: Opcjonalnie sync do W.I.T.E.K API.
**Wysiłek**: ~4h

### 4. 🔴 Village Overview Dashboard (trudne)
**Co**: Lista wszystkich wiosek z zasobami, produkcją, kolejkami.
**Jak**: Wymaga scrapingu `dorf3.php` (overview) lub iterowania po wioskach. Duże parsowanie DOM.
**Problem**: Dużo kodu, łamliwe przy zmianach DOM Traviana.
**Wysiłek**: ~12h+

## Rekomendacja

**Faza 1 (teraz)**: Nie dodajemy nowych funkcji — obecne rozszerzenie działa dobrze.

**Faza 2 (przyszły sprint)**:
1. Crop Balance Warning — szybkie, przydatne taktycznie
2. Village Notes — użyteczne dla koordynacji sojuszowej

**Faza 3 (jeśli będzie potrzeba)**:
3. Resource Bar z produkcją/h — nice-to-have
4. Village Overview — duże przedsięwzięcie, wymaga dedykowanego sprintu

## Ograniczenia techniczne

- **MV3 vs userscript**: Rozszerzenie Chrome (MV3) nie ma bezpośredniego dostępu do `window.Travian.*` — wymaga wstrzykiwania skryptu do page context via `world.MAIN`
- **GPL licencja**: Nie kopiujemy kodu z TravianResourceBarPlus — tylko inspirujemy się funkcjami
- **DOM fragility**: Parsowanie DOM Traviana jest łamliwe — każda aktualizacja gry może złamać scraping
- **User-triggered**: W.I.T.E.K extension wymaga akcji użytkownika (kliknięcie przycisku) — nie background scraping
