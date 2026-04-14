# 🗺️ W.I.T.E.K — Roadmap / kierunek rozwoju

> Linia produktu: **0.2.1 cleanup release**
>
> Aktualny snapshot repo: **9 cogów** | **34 komendy slash** | **12 modułów tras Flask** | **882 testy pytest** | **RoF-first + Chrome extension API**

## Stan bieżący

W.I.T.E.K jest dziś ustawiony wokół domyślnego scenariusza **Reign of Fire x3**:

- `SERVER_PROFILE=rof-x3` jest standardowym profilem repo,
- `docker compose up -d` uruchamia główny stack produkcyjny,
- Dockerfile startuje aplikację jako `python run.py --scheduled --port 5000`,
- `scheduler.fetch_cron_hour` / `fetch_cron_minute` steruje kolektorem `map.sql` (domyślnie 00:05 UTC, raz dziennie),
- klasyczny preset został przesunięty do `legacy\ts31\`.

## Dostarczone filary produktu

### 1. Dashboard i dane Travian
- import oraz historia snapshotów `map.sql`,
- widoki graczy, sojuszy i wiosek,
- alerty `pop_drop`, `new_village`, `alliance_change`,
- szybkie wyszukiwanie, dyplomacja i widoki raportów/obrony,
- strefa sojuszu z hasłem i opcjonalnym loginem Discord OAuth.

### 2. Bot Discord
- 9 cogów,
- 34 komendy slash,
- koordynacja ataków, wątki obrony, rejestracja wojsk i wsparcia,
- kalkulatory taktyczne (`tbezpieczne`, `tileobrony`, `tprzechwyc`, `tsymulacja`, `tbuildtime`, `ttraining`),
- recon / economy (`tenemy`, `tnieaktywni`, `tcropper`, `tszukaj`, `tporownaj`),
- digest i dyplomacja.

### 3. Browser extension + API
- ręczny import raportów bitewnych,
- ręczny import raportów szpiegowskich,
- import stanu wojsk w wiosce,
- import incomingów z Punktu Zbornego,
- tokenizowane endpointy `/api/ext/*` po stronie Flask, w tym `/api/ext/game-data` dla `hero`, `marketplace` i `training`.

### 4. Jakość i utrzymanie
- 882 testy pytest w aktualnym repo,
- CI w GitHub Actions,
- jeden główny stack Docker + osobny stack dev,
- uproszczona dokumentacja po cleanupie 0.2.1.

## Priorytety po cleanupie 0.2.1

### P1 — release hardening
- świeży smoke test `docker compose up -d` na czystym `.env.example`,
- walidacja workflow: start webu, start bota, pierwszy snapshot `map.sql`, alert `pop_drop`,
- weryfikacja przykładowego obrazu GHCR/tagu release.

### P2 — UX dashboardu
- lepsze filtry i sortowanie alertów, raportów oraz dyplomacji,
- więcej statystyk historycznych dla graczy i sojuszy,
- dalsze dopracowanie widoków mapy / analityki RoF.

### P3 — rozszerzenie Chrome
- lepsza ergonomia popupu i komunikatów błędów,
- dodatkowe smoke testy endpointów `/api/ext/*`,
- przygotowanie do publikacji / paczkowania release buildów rozszerzenia.

### P4 — wydajność i stabilność
- optymalizacja zapytań pod większą liczbę snapshotów,
- profilowanie najcięższych widoków dashboardu,
- dalsze porządki w logowaniu i diagnostyce runtime.

## Backlog / pomysły później

- eksport danych do CSV/JSON,
- bardziej interaktywna mapa i porównania trendów,
- dodatkowe narzędzia RoF (np. regiony / VP / ruchy wokół hotspotów),
- automatyzacja release pipeline dla aplikacji i rozszerzenia,
- bardziej rozbudowane E2E / browser smoke testy.

## Snapshot architektury repo

```
run.py                  # Flask + bot + scheduler / collect CLI
├── app/                # Dashboard Flask + API
│   ├── map_sql/        # Parser, collector, alerts
│   ├── routes/         # 12 modułów tras
│   └── templates/      # UI w stylu Travian
├── bot/                # Discord bot
│   ├── cogs/           # 9 cogów / 34 komendy slash
│   ├── tribes.py       # Dane nacji i jednostek
│   └── deep_links.py   # Linki do gry
├── extension/          # Chrome extension + service worker
├── config/             # YAML config
├── docker-compose.yml  # Domyślny stack prod
├── docker-compose.dev.yml # Stack dev
├── legacy/ts31/        # Archiwum klasycznego presetu
└── tests/              # 882 testy pytest
```


