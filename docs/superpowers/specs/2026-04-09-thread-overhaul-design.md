# Design: Ulepszenia Wątków Obrony + Parser + Mobile
**Data:** 2026-04-09

## Problem

Aktualne wątki obrony na forum Discord mają kilka problemów:
1. **Ikona nacji** w miniaturce embeda — niepotrzebna, user chce listę wiosek zamiast niej
2. **Brak pingowania roli @Def** — gracze defensywni nie dostają powiadomień
3. **Główna wiadomość się nie aktualizuje** gdy dodajemy nowe ataki (`/tdodaj`)
4. **Parser raportów** — może nie działać poprawnie z realnymi raportami
5. **Gracze mobilni** — nie mogą skopiować raportu bitewnego na telefonie

## Rozwiązanie

### A. Edytowalna wiadomość podsumowania w wątku

**Koncepcja:** Pierwsza wiadomość w wątku = **embed podsumowania** z listą WSZYSTKICH ataków na tę wioskę/gracza. Aktualizowana automatycznie gdy:
- `/tdodaj` doda nowy atak
- `/trozwiaz` zamknie zgłoszenie
- Raport/wsparcie zostanie dodane

**Tytuł wątku:** `🚨 Obrona: {wioska} ({x}|{y})` — skupiony na BRONIONYM celu, nie atakującym

**Struktura embeda podsumowania:**
```
🚨 OBRONA — {wioska_name} ({x}|{y})
─────────────────────────────
⚔️ Ataki:
  #1: PeterPage (81|33) → Warszawka — <t:unix:R>
  #2: Inny_gracz (50|60) → Warszawka — <t:unix:R>

🏰 Informacje o wiosce:
  🧱 Mur: 15 | 🌾 Zboże: 45000 | 📈 Produkcja: 1200/h

🛡️ Obrona (zarejestrowana):
  Garnizon: 200 falangitów, 100 mieczników (🌾 300/h)
  Wsparcie #1: gracz_X (70|40) — 150 pałkarzy (🌾 150/h)
  📊 Łączne zużycie zboża: 450/h

📌 Komendy:
  /tdodaj {id} — dodaj kolejny atak
  /twsparcie ... — zarejestruj wsparcie
  /trozwiaz {id} — zamknij
```

**Implementacja:**
1. Dodaj kolumnę `summary_message_id` do `AttackReport` (na "parent" raporcie, który stworzył wątek)
2. Po stworzeniu wątku, zapisz ID pierwszej wiadomości
3. Nowa metoda `_build_summary_embed()` — buduje embed z WSZYSTKICH ataków dla danego wątku
4. Nowa metoda `_update_thread_summary()` — pobiera wszystkie ataki z wątku, buduje embed, edytuje wiadomość
5. Wywołuj `_update_thread_summary()` w: `/tdodaj`, `/trozwiaz`, po rejestracji wsparcia

**Dane do podsumowania (zbierane z DB):**
- Wszystkie AttackReport z danym `forum_thread_id`
- VillageTroops dla koordynatów obrońcy
- TroopSupport z `to_x`/`to_y` = koordynaty obrońcy

### B. Ping roli @Def

- Nowa zmienna: `DISCORD_DEF_ROLE_ID` w `.env`
- Config.py: parsuj `DISCORD_DEF_ROLE_ID` jako int (tak jak inne ID)
- W `_create_defense_thread()`: content zaczyna się od `<@&{role_id}>` (format pingu roli Discord)
- Ping tylko przy tworzeniu wątku, nie przy aktualizacjach

### C. Usunięcie ikony nacji z embeda

- W `_build_attack_embed()`: usunąć linię `embed.set_thumbnail(url=TRIBE_ICONS[...])` 
- Nacja atakującego nadal wyświetlana tekstem (emoji + nazwa) — to zostaje

### D. Poprawki embeda ataku

- Zamiast jednego celu, embed powinien wyraźniej pokazywać:
  - **Obrońca**: wioska + link na mapę + gracz
  - **Agresor**: wioska + link na mapę + gracz (oba z linkami)

### E. Parser raportów — diagnostyka i wzmocnienie

**Potencjalne problemy:**
1. Raporty z gry mogą mieć różne formatowanie (np. spacje zamiast tabów na mobile)
2. Sekcja "zdobycz" może zawierać tekst przed liczbami
3. Linia daty może mieć inny format niż `DD.MM.YY`
4. Linie z "Siła w walce" mogą używać separatorów tysięcy

**Poprawki:**
- Dodaj fallback: jeśli tab-separated nie działa, spróbuj space-separated
- Robustniejsze parsowanie "zdobycz" (regex zamiast fixed-index split)
- Więcej tolerancji na format daty
- Lepsze logowanie błędów parsowania (linia + indeks + zawartość)

### F. Gracze mobilni — `/traport_reczny`

Na telefonie nie da się skopiować raportu bitewnego w formacie tab-separated.

**Rozwiązanie:** Nowa komenda `/traport_reczny` z parametrami slash command:
```
/traport_reczny
  napastnik: str    — nazwa gracza atakującego
  obronca: str      — nazwa gracza broniącego
  wynik: str        — "wygrana_atk" / "wygrana_def" / "remis"
  straty_atk: str   — (opcjonalne) np. "80 pałkarzy, 20 toporników"
  straty_def: str   — (opcjonalne) np. "50 falangitów"
  zdobycz: str      — (opcjonalne) np. "1000 drewna, 500 gliny"
  atak_id: int      — (opcjonalne) powiązanie z wątkiem
```

Jest to uproszczona wersja — nie ma pełnych danych jak z copy-paste, ale daje podstawowe informacje dla graczy mobilnych. Parsowanie "straty" to free-text z best-effort rozpoznawaniem jednostek.

## Zmiany w plikach

| Plik | Zmiany |
|------|--------|
| `app/config.py` | + `DISCORD_DEF_ROLE_ID` |
| `app/models.py` | + `summary_message_id` na AttackReport |
| `app/database.py` | + migracja `summary_message_id` |
| `bot/cogs/attacks.py` | Refaktor embeda, summary, @Def ping, remove tribe thumbnail |
| `bot/cogs/defense.py` | + `/traport_reczny`, poprawki parsera |
| `bot/cogs/general.py` | + nowa komenda w /thelp |
| `tests/test_defense.py` | + testy parsera (edge cases) |
| `.env.example` | + `DISCORD_DEF_ROLE_ID` |

## Kolejność implementacji

1. ROADMAP.md ← już zrobione
2. Config: `DISCORD_DEF_ROLE_ID`
3. Model: `summary_message_id` + migracja
4. `_build_summary_embed()` — nowy embed podsumowania
5. `_update_thread_summary()` — metoda edycji
6. Refaktor `_create_defense_thread()` — @Def ping + summary
7. Refaktor `/tdodaj` — wywołaj update summary
8. Usunięcie tribe thumbnail z `_build_attack_embed()`
9. Poprawki parsera raportów
10. `/traport_reczny` dla mobile
11. Testy + Docker rebuild
