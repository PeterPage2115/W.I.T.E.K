# Changelog

Wszystkie istotne zmiany w projekcie W.I.T.E.K.

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/).

## [0.1.0] — 2026-04-12

### Dodane
- Dashboard webowy z danymi graczy, sojuszy i wiosek
- Bot Discord z 26 komendami slash
- System alertów (spadek populacji, nowe wioski, zmiany sojuszy)
- Koordynacja obrony (wątki, garnizony, wsparcie)
- Kalkulatory taktyczne (bezpieczne wysyłanie, przechwycenie, symulacja bitwy)
- Parser map.sql z obsługą 16 pól (RoF: regiony, stolice, porty)
- Multi-server config (SERVER_PROFILE)
- Rozszerzenie Chrome do przechwytywania raportów
- Docker Compose (produkcja + dev + RoF)
- 853 testów pytest
- Moduł deep links do generowania linków w grze

### Naprawione
- Tribe ID bug — tid 8↔9 (Spartanie=8, Wikingowie=9)
