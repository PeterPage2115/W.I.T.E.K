# W.I.T.E.K — Przewodnik wdrożenia

Kompletna instrukcja uruchomienia W.I.T.E.K w środowisku produkcyjnym i deweloperskim.

---

## 📋 Wymagania

| Składnik | Wersja | Uwagi |
|----------|--------|-------|
| Docker | 24+ | `docker --version` |
| Docker Compose | v2+ | Wbudowany w Docker Desktop |
| Token bota Discord | — | [Discord Developer Portal](https://discord.com/developers/applications) |
| Serwer / VPS | — | Min. 512 MB RAM, otwarty port 5000 (lub inny) |
| Git | — | Do klonowania repozytorium |

---

## ⚙️ Konfiguracja

### 1. Sklonuj repozytorium

```bash
git clone https://github.com/PeterPage2115/W.I.T.E.K.git
cd W.I.T.E.K
```

### 2. Utwórz plik `.env`

```bash
cp .env.example .env
```

Otwórz `.env` i uzupełnij wartości:

| Zmienna | Opis | Przykład |
|---------|------|---------|
| `FLASK_SECRET_KEY` | Losowy ciąg znaków do sesji Flask | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FLASK_DEBUG` | Tryb debugowania (`true` / `false`) | `false` (produkcja) |
| `ALLIANCE_PASSWORD` | Hasło dostępu do strefy sojuszu | Ustaw własne |
| `DISCORD_TOKEN` | Token bota Discord | Ze strony Developer Portal |
| `DISCORD_GUILD_ID` | ID serwera Discord | Prawy klik → Kopiuj ID |
| `DISCORD_ALERTS_CHANNEL_ID` | ID kanału alertów | Prawy klik → Kopiuj ID |
| `DISCORD_DEFENSE_FORUM_ID` | ID forum obrony | Prawy klik → Kopiuj ID |
| `DISCORD_DEF_ROLE_ID` | ID roli obrońców | Ustawienia serwera → Role |
| `TRAVIAN_SERVER_URL` | URL serwera Travian | `https://ts31.x3.europe.travian.com` |
| `DATABASE_URL` | Adres bazy (puste = SQLite) | Puste dla dev, automatyczne dla Docker prod |
| `POSTGRES_DB` | Nazwa bazy PostgreSQL | `witek` |
| `POSTGRES_USER` | Użytkownik PostgreSQL | `witek` |
| `POSTGRES_PASSWORD` | Hasło PostgreSQL | Silne, losowe hasło |
| `WITEK_PORT` | Port zewnętrzny | `5000` |

### 3. Utwórz konfigurację YAML

```bash
cp config/config.example.yaml config/config.yaml
```

Edytuj `config/config.yaml` — najważniejsze:

```yaml
servers:
  ts31:
    our_alliances: [123, 456]  # ← Wstaw ID swoich sojuszy z map.sql
```

ID sojuszy znajdziesz w map.sql (pole `aid` w danych wioski).

---

## 🚀 Uruchomienie

### Tryb deweloperski (SQLite)

Prosty tryb do testowania — bez PostgreSQL, kod montowany z dysku:

```bash
docker compose -f docker-compose.dev.yml up -d
```

- Dashboard: http://localhost:5000
- Baza: SQLite (plik `witek.db`)
- Zmiany w kodzie widoczne po restarcie kontenera

### Tryb produkcyjny (PostgreSQL)

Pełna konfiguracja z bazą PostgreSQL:

```bash
docker compose up -d
```

- Dashboard: http://localhost:5000 (lub port z `WITEK_PORT`)
- Baza: PostgreSQL w osobnym kontenerze
- Dane zachowane w wolumenie `witek-pgdata`

### Reign of Fire (RoF)

Oddzielna instancja dla serwera RoF:

```bash
cp .env.rof.example .env.rof
# Uzupełnij .env.rof (osobny token bota!)
docker compose --env-file .env.rof -f docker-compose.rof.yml up -d
```

- Dashboard: http://localhost:5001 (port 5001)
- Baza: Oddzielny PostgreSQL (`witek_rof`)
- Oddzielna sieć Docker, wolumen i token bota

### Sprawdzenie statusu

```bash
# Status kontenerów
docker compose ps

# Logi aplikacji (na żywo)
docker compose logs -f witek-app

# Logi bazy danych
docker compose logs witek-db
```

---

## 🎯 Pierwsze kroki po uruchomieniu

### 1. Zaproś bota na serwer Discord

Wejdź na [Discord Developer Portal](https://discord.com/developers/applications), wybierz aplikację bota i w zakładce **OAuth2 → URL Generator**:

- Scopes: `bot`, `applications.commands`
- Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Use Slash Commands`, `Create Public Threads`
- Skopiuj wygenerowany URL i otwórz go w przeglądarce

### 2. Skonfiguruj kanały Discord

- Utwórz kanał tekstowy na alerty (np. `#alerty-witek`)
- Utwórz forum na obronę (np. `forum-obrona`)
- Utwórz rolę obrońców (np. `@Obrońca`)
- Wpisz ich ID do `.env`

### 3. Połącz konta Travian z Discord

Każdy gracz na serwerze Discord powinien użyć:
```
/tlink <nazwa_gracza_travian>
```

### 4. Pierwsze pobranie map.sql

Scheduler pobiera dane automatycznie raz dziennie (domyślnie o 02:00 UTC). Aby pobrać od razu:

```bash
# Wewnątrz kontenera
docker exec witek-app python run.py --collect

# Lub z pliku lokalnego
docker exec witek-app python run.py --from-file /app/map.sql
```

### 5. Sprawdź dashboard

Otwórz http://localhost:5000 (lub `http://YOUR_SERVER:5000`) — powinny się pojawić dane po pierwszym pobraniu.

---

## 🔄 Aktualizacja

```bash
# Pobierz najnowszy kod
git pull

# Przebuduj i uruchom ponownie
docker compose up -d --build
```

Dane w PostgreSQL są zachowane w wolumenie — aktualizacja nie kasuje bazy.

---

## 💾 Backup i przywracanie

### Backup bazy PostgreSQL

```bash
# Eksport do pliku SQL
docker exec witek-db pg_dump -U witek witek > backup_$(date +%Y%m%d).sql
```

### Przywracanie z backupu

```bash
# Import z pliku SQL
docker exec -i witek-db psql -U witek witek < backup.sql
```

### Automatyczny backup (cron)

Dodaj do crontab na serwerze:

```bash
# Codziennie o 03:00 — backup bazy W.I.T.E.K
0 3 * * * docker exec witek-db pg_dump -U witek witek > /backups/witek_$(date +\%Y\%m\%d).sql
```

---

## 🐛 Troubleshooting

### Bot nie łączy się z Discordem

- Sprawdź `DISCORD_TOKEN` w `.env` — czy jest poprawny?
- Sprawdź logi: `docker compose logs witek-app | grep -i discord`
- Upewnij się, że bot ma włączone **Message Content Intent** w Developer Portal

### Brak danych na dashboardzie

- Uruchom ręczne pobranie: `docker exec witek-app python run.py --collect`
- Sprawdź URL serwera Travian w `.env` (`TRAVIAN_SERVER_URL`)
- Sprawdź logi: `docker compose logs witek-app | grep -i collect`

### Błędy bazy danych

- Sprawdź czy kontener bazy działa: `docker compose ps witek-db`
- Sprawdź `DATABASE_URL` — w trybie prod jest ustawiany automatycznie przez docker-compose
- Zresetuj bazę (UWAGA — kasuje dane!): `docker compose down -v && docker compose up -d`

### Kontener się restartuje

```bash
# Sprawdź logi ostatniego restartu
docker compose logs --tail=50 witek-app

# Sprawdź healthcheck
docker inspect witek-app | grep -A 10 Health
```

### Port zajęty

Zmień `WITEK_PORT` w `.env` na inny wolny port, np. `8080`.

---

## 📦 Docker Registry (opcjonalnie)

Aby opublikować obraz w GitHub Container Registry:

### Logowanie do GHCR

```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u peterpage2115 --password-stdin
```

### Budowanie i publikacja

```bash
# Zbuduj z tagiem
docker build -t ghcr.io/peterpage2115/w.i.t.e.k:latest .

# Wypchnij do registry
docker push ghcr.io/peterpage2115/w.i.t.e.k:latest

# Z wersjonowaniem
docker build -t ghcr.io/peterpage2115/w.i.t.e.k:1.0.0 .
docker push ghcr.io/peterpage2115/w.i.t.e.k:1.0.0
```

### Użycie w docker-compose.yml

Zamiast budowania lokalnego, użyj gotowego obrazu:

```yaml
services:
  witek-app:
    image: ghcr.io/peterpage2115/w.i.t.e.k:latest
    # zakomentuj sekcję build:
    # build:
    #   context: .
    #   dockerfile: Dockerfile
```

---

## 📁 Struktura plików

```
witek/
├── .env.example          # Szablon konfiguracji
├── .env                  # Twoja konfiguracja (nie commituj!)
├── config/
│   ├── config.example.yaml  # Szablon YAML
│   └── config.yaml          # Twoja konfiguracja
├── Dockerfile            # Multi-stage build (produkcja)
├── docker-compose.yml    # Produkcja (PostgreSQL)
├── docker-compose.dev.yml # Deweloperski (SQLite)
├── app/                  # Flask — dashboard webowy
├── bot/                  # Discord bot — komendy slash
├── tests/                # Testy pytest
└── run.py                # Punkt wejścia aplikacji
```

---

*⚔️ W.I.T.E.K — Na cześć Gucio*
