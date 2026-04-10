# Sprint 3 Phase 2 — Chrome Extension MVP + Webhook API

## Cel
Rozszerzenie Chrome (Manifest V3) do Travian Legends, które wyciąga dane z gry i przesyła do WITEK bota przez webhook API. Gracze klikają przycisk w rozszerzeniu, dane trafiają do bazy.

## Scope — MVP (minimum viable product)

### Funkcje rozszerzenia:
1. **Raport bitewny** — czyta stronę `berichte.php`, parsuje dane atakujący/broniący, straty, mur, zboże → wysyła do WITEK
2. **Przegląd wojsk** — czyta stronę wioski (`dorf1.php` / troop overview), wyciąga garnizon → wysyła
3. **Nadchodzące ataki** — czyta Rally Point (`build.php?gid=16&tt=1`), wyciąga timery i źródło → wysyła

### Webhook API (Flask):
1. `POST /api/ext/report` — przyjmuje sparsowany raport bitewny
2. `POST /api/ext/troops` — przyjmuje stan wojsk wioski  
3. `POST /api/ext/incoming` — przyjmuje nadchodzące ataki
4. Auth: `X-Witek-Token` header z shared secret (per-alliance)

### Popup UI:
- Pole na URL serwera WITEK (np. `http://localhost:5000`)
- Pole na token API
- Checkbox "włączone"
- Status: ✅ połączono / ❌ błąd
- Styl: ciemny, Travian-inspired

## Architektura

```
┌─────────────────────────────────┐
│  Chrome Extension (MV3)         │
│                                 │
│  content.js (na stronach gry)   │
│    ↓ chrome.runtime.sendMessage │
│  service-worker.js              │
│    ↓ fetch() POST               │
│  popup.html (ustawienia)        │
└──────────────┬──────────────────┘
               │ HTTP POST /api/ext/*
               ▼
┌─────────────────────────────────┐
│  WITEK Flask Backend            │
│  app/routes/api_ext.py          │
│    → validate token             │
│    → store in DB (existing      │
│      models: BattleReport,      │
│      VillageTroops, AttackReport│
└─────────────────────────────────┘
```

## Struktura plików

```
extension/
├── manifest.json           # Manifest V3
├── icons/
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
├── popup/
│   ├── popup.html          # Settings UI
│   ├── popup.css           # Dark Travian style
│   └── popup.js            # Settings logic
├── content/
│   ├── detector.js         # Detects page type, dispatches parser
│   ├── report-parser.js    # Battle report parser
│   ├── troops-parser.js    # Troop overview parser
│   └── incoming-parser.js  # Rally point incoming parser
├── background/
│   └── service-worker.js   # Message relay + HTTP sender
└── shared/
    └── constants.js        # Shared config, page patterns
```

## Travian URL Patterns

| Strona | URL Pattern | Dane |
|--------|-------------|------|
| Raport bitewny | `berichte.php?id=*` | Wojska, straty, zboże, mur |
| Rally Point | `build.php?gid=16*` | Nadchodzące, timery, źródło |
| Wioska | `dorf1.php*` | Garnizon, koordynaty |

## API Endpoints

### POST /api/ext/report
```json
{
  "server_url": "https://ts31.x3.europe.travian.com",
  "report_id": 12345,
  "attacker": {"name": "Player1", "x": 10, "y": -20, "troops": {"1": 100, "2": 50}, "losses": {"1": 30}},
  "defender": {"name": "Player2", "x": 5, "y": 15, "troops": {"1": 200}, "losses": {"1": 80}},
  "wall_level_before": 10,
  "wall_level_after": 8,
  "bounty": {"wood": 1000, "clay": 500, "iron": 300, "crop": 2000}
}
```

### POST /api/ext/troops  
```json
{
  "server_url": "https://ts31.x3.europe.travian.com",
  "village_id": 12345,
  "x": 76, "y": 43,
  "village_name": "Wioska gracza",
  "troops": {"1": 500, "2": 100, "3": 200},
  "timestamp": "2026-04-10T16:00:00Z"
}
```

### POST /api/ext/incoming
```json
{
  "server_url": "https://ts31.x3.europe.travian.com",
  "village_id": 12345,
  "x": 76, "y": 43,
  "incoming": [
    {"type": "attack", "from_x": 10, "from_y": -5, "arrival_unix": 1712764800, "player_name": "Enemy"}
  ]
}
```

## Security
- Token w `X-Witek-Token` header
- `EXT_API_TOKEN` w `.env` / config.yaml
- Rate limiting: 60 req/min per token
- CORS: allow extension origin

## Decyzje
- Jednostki identyfikowane po numerycznym ID (1-10 per tribe, universalne w Travian)
- Serwer wyciągany z `window.location.origin` w content script
- Rozszerzenie NIE modyfikuje stron gry (readonly, no automation)
- Chrome Web Store distribution (official)
