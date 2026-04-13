# ARCHIWUM — dawny plan audytu / cleanup po pivotcie RoF-first

> **Status:** zamknięty / zarchiwizowany.
>
> Ten plik **nie jest już aktywnym planem prac**. Został zachowany wyłącznie jako historyczny ślad po porządkach wykonywanych podczas pivotu do układu RoF-first i przygotowania cleanup release 0.2.1.

---

## Co obejmował ten plan

Historyczny zakres obejmował głównie:

- przejście repo do domyślnego profilu `rof-x3`,
- uporządkowanie deploymentu wokół standardowego `docker compose up -d`,
- cleanup martwych plików i starych presetów,
- synchronizację dokumentacji z faktycznym stanem repo.

## Stan repo w momencie archiwizacji

- 🌋 domyślny profil: `rof-x3`
- 🐳 aktywne compose: `docker-compose.yml` (PostgreSQL) i `docker-compose.dev.yml` (SQLite)
- 🤖 9 cogów Discord + 34 komendy slash
- 🌐 12 modułów tras Flask
- ✅ 882 testy pytest
- 🗂️ klasyczny preset odłożony do `legacy\ts31\`

## Jak traktować ten plik

- To **archiwum kontekstu**, a nie backlog do dalszej realizacji.
- Zadania opisane w starej wersji były wykonane, zastąpione lub zdezaktualizowane.
- Nowych prac nie planujemy przez reaktywowanie tej listy.

## Gdzie patrzeć zamiast tego

- `README.md` — szybki start i aktualny overview projektu
- `DEPLOY.md` — realny runtime Docker / deploy / GHCR
- `CLAUDE.md` — techniczny kontekst repo dla agentów
- `CHANGELOG.md` — historia release'ów, w tym cleanup 0.2.1
- `docs/ROADMAP.md` — aktualny kierunek rozwoju po zakończeniu cleanupu

## Notatka historyczna

Jeżeli potrzebujesz sprawdzić „co kiedyś planowaliśmy”, traktuj poprzednią zawartość tego pliku wyłącznie jako materiał archiwalny z okresu przejściowego. Nie zakładaj, że dawne checklisty, liczby lub nazwy plików nadal odpowiadają bieżącemu stanowi repo.
