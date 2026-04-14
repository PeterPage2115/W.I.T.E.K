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

## Unraid + Cloudflare Tunnel (home hosting)

Below are operator-grade, step-by-step notes for running W.I.T.E.K on a home Unraid server exposed via a Cloudflare Tunnel (cloudflared). This complements the RoF-first guidance above — do both: keep the default Docker stack and follow these extra steps for a safe home-hosted setup.

1. Recommended deploy location on Unraid

- Place the repo or a deployment clone under a persistent appdata path, for example:

  - /mnt/user/appdata/witek  (recommended for configs/volumes)
  - /mnt/user/docker/witek (optional alternative)

- Keep the project working directory there and mount volumes from those locations in your Compose files.

2. Environment and config

- Copy the template once in your deploy dir:

  cp .env.example .env

- Set the exact env key for OAuth callback. Example (for public hostname witek.krecik.xyz):

  DISCORD_REDIRECT_URI=https://witek.krecik.xyz/auth/callback

  (Use this exact variable name — the app reads DISCORD_REDIRECT_URI.)

- Configure config/config.yaml with real alliance IDs for your server profile. Example:

  servers:
    rof-x3:
      our_alliances: [123456, 234567]

  Replace the example IDs with the real numeric alliance IDs you want monitored.

3. Local Docker smoke on Unraid (before wiring Cloudflare Tunnel)

- From the deploy directory run:

  docker compose up -d
  docker compose ps
  docker compose exec witek-app python run.py --collect

- What to expect on success (logs / messages):
  - On startup: "Scheduler uruchomiony: map.sql co ... min"
  - When bot connects (if DISCORD_TOKEN set): "W.I.T.E.K zalogowany jako <botname>"
  - On manual collection success: "✅ Snapshot #..."

4. Cloudflare Tunnel (choose Cloudflared)

- We recommend using Cloudflare Tunnel via the official "cloudflared" tool (not alternative tunnels). Typical operator path:
  1. Follow Cloudflare docs to install/get the recommended docker image reference — note the exact image tag they advise in the install command.
  2. Create a named tunnel on your Cloudflare account: `cloudflared tunnel create witek-tunnel`
  3. Route a DNS name to the tunnel: `cloudflared tunnel route dns witek-tunnel witek.krecik.xyz`
  4. Create a config.yml for the tunnel with an ingress rule that publishes your Unraid host port (example below).

- Important: use a pinned image tag copied from Cloudflare's official install instruction, e.g. `cloudflare/cloudflared:<tag-from-install>` — do NOT rely on `:latest`.

- Example tunnel ingress (cloudflared config.yml):

  tunnel: <TUNNEL_ID>
  credentials-file: /root/.cloudflared/<TUNNEL_ID>.json
  ingress:
    - hostname: witek.krecik.xyz
      service: http://<UNRAID_LAN_IP>:5000
    - service: http_status:404

  Note: when `cloudflared` runs as a separate container on Unraid, the service MUST point to the Unraid host LAN IP (e.g. http://192.168.1.23:5000) — do NOT use `http://localhost:5000` because `localhost` inside the cloudflared container resolves to the cloudflared container itself, not the host/app container.

- If you prefer to run cloudflared as a container, include the pinned image in a Compose or Unraid template that references the same host networking or uses the Unraid LAN IP in ingress rules.

5. Publish app route and Compose notes

- The application publishes on the WITEK port (default 5000). Make sure your Compose uses that port and that cloudflared ingress maps to the host IP:5000.

- Example minimal cloudflared service entry (for reference — adapt to Unraid templates):

  image: cloudflare/cloudflared:<tag-from-install>
  container_name: cloudflared-witek
  restart: unless-stopped
  # Named-tunnel run (use the tunnel name created earlier, e.g. `witek-tunnel`).
  # This example follows the named-tunnel flow and uses the credentials file
  # referenced from the cloudflared config.yml. Do NOT mix `--token` and
  # `credentials-file` methods in the same deployment.
  command: tunnel run witek-tunnel --config /etc/cloudflared/config.yml
  volumes:
    - /mnt/user/appdata/witek/cloudflared:/etc/cloudflared

6. Exact env variable to set for OAuth

- Ensure the public OAuth callback is set with the exact key name in your .env file:

  DISCORD_REDIRECT_URI=https://witek.krecik.xyz/auth/callback

- Also set DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET from the Discord developer portal if you want Discord OAuth to work.

7. End-to-end OAuth smoke test

- With the tunnel active and the DNS record live, open in a browser:

  https://witek.krecik.xyz/auth/login

- Click the Discord login, authorize the app, and confirm the callback returns to `https://witek.krecik.xyz/auth/callback` and you land back in the dashboard.

- Troubleshooting tips: watch `docker compose logs -f witek-app` during the flow for redirect/callback errors.

8. Extension setup and test upload

- In the Chrome extension settings set:
  - serverUrl: https://witek.krecik.xyz
  - token: (value of EXT_API_TOKEN from your .env)

- Click Save → Test. A successful Test indicates the extension can contact your public host.

- Perform one real upload from the extension UI (e.g., a battle report). Verify the app received it and logs a successful message and/or `✅ Snapshot #...` where applicable.

9. Security and operational notes

- Keep your `.env` and `config/config.yaml` outside public shares and back them up.
- Use Cloudflare Access / Zero Trust rules if you need to restrict access to the dashboard.
- Pin the cloudflared image tag in any Unraid Docker template you create — record the tag you used in your deployment notes.

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



