# Commands Audit + Browser Parity Roadmap Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zrobic kodowy audit komend Discord, porownac je z obecnym web/API, a wynik zamienic na capability-first roadmape dla parity webowego, RBAC/admin panelu, redesignu mapy i przegladu API.

**Architecture:** Najpierw zbieramy fakty z kodu i testow do artefaktow w sesji, zamiast od razu zmieniac repo. Audit ma byc capability-first: Discord i web sa dwoma interfejsami do tej samej logiki domenowej, a parity oznacza te same mozliwosci, nie literalne kopiowanie slash-komend.

**Tech Stack:** Python, Flask, SQLAlchemy, py-cord, pytest, ripgrep, session SQL, session artifacts w `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\`

---

## Context snapshot

- Bot ma `9` cogow i `34` komendy slash
- Flask ma `12` modulow tras, ale obecny web pokrywa glownie odczyt oraz wybrane workflow (ataki, obrona, raporty, dyplomacja, search, mapa)
- `app/routes/auth.py` + `app/models.User.role` daja zalazek OAuth/RBAC, ale:
  - nowi uzytkownicy dostaja domyslnie role `member`
  - `role_required` jeszcze nie pilnuje realnych capability na trasach
  - brak panelu admina do nadawania uprawnien
- `app/templates/map.html` daje prosta mape Leaflet z markerami i filtrami, ale nie wspiera jeszcze workflow w stylu GetterTools

## User-approved design decisions

- pierwszy podprojekt: **audit komend i analiza brakow**
- wynik pierwszego etapu: **audit + macierz komend + roadmapa priorytetow**
- roadmapa ma zachowac trzy dalsze tematy:
  - parity komend Discord -> dashboard/browser
  - redesign mapy/dashboardu
  - przeglad mozliwych API
- parity ma oznaczac **te same mozliwosci**, ale web moze miec lepszy workflow niz Discord
- dostep webowy ma byc przez **Discord OAuth + role/uprawnienia + panel admina**

## File map

- **Discord command source**
  - `E:\Projekty\Travian\bot\cogs\general.py`
  - `E:\Projekty\Travian\bot\cogs\identity.py`
  - `E:\Projekty\Travian\bot\cogs\attacks.py`
  - `E:\Projekty\Travian\bot\cogs\defense.py`
  - `E:\Projekty\Travian\bot\cogs\recon.py`
  - `E:\Projekty\Travian\bot\cogs\economy.py`
  - `E:\Projekty\Travian\bot\cogs\digest.py`
  - `E:\Projekty\Travian\bot\cogs\diplomacy.py`
  - `E:\Projekty\Travian\bot\cogs\alerts.py`
- **Web/API source**
  - `E:\Projekty\Travian\app\routes\dashboard.py`
  - `E:\Projekty\Travian\app\routes\map.py`
  - `E:\Projekty\Travian\app\routes\attacks.py`
  - `E:\Projekty\Travian\app\routes\defense.py`
  - `E:\Projekty\Travian\app\routes\reports.py`
  - `E:\Projekty\Travian\app\routes\players.py`
  - `E:\Projekty\Travian\app\routes\alliances.py`
  - `E:\Projekty\Travian\app\routes\search.py`
  - `E:\Projekty\Travian\app\routes\diplomacy.py`
  - `E:\Projekty\Travian\app\routes\auth.py`
  - `E:\Projekty\Travian\app\routes\api_ext.py`
  - `E:\Projekty\Travian\app\routes\alerts_web.py`
- **Auth / model source**
  - `E:\Projekty\Travian\app\auth_utils.py`
  - `E:\Projekty\Travian\app\models.py`
- **Key templates to inspect**
  - `E:\Projekty\Travian\app\templates\dashboard.html`
  - `E:\Projekty\Travian\app\templates\map.html`
  - `E:\Projekty\Travian\app\templates\attacks.html`
  - `E:\Projekty\Travian\app\templates\attack_detail.html`
  - `E:\Projekty\Travian\app\templates\defense.html`
  - `E:\Projekty\Travian\app\templates\defense_detail.html`
  - `E:\Projekty\Travian\app\templates\reports.html`
  - `E:\Projekty\Travian\app\templates\report_detail.html`
  - `E:\Projekty\Travian\app\templates\diplomacy.html`
- **Tests to use during audit**
  - `E:\Projekty\Travian\tests\test_general_cog.py`
  - `E:\Projekty\Travian\tests\test_identity_cog.py`
  - `E:\Projekty\Travian\tests\test_attacks_cog.py`
  - `E:\Projekty\Travian\tests\test_attack_routes.py`
  - `E:\Projekty\Travian\tests\test_defense.py`
  - `E:\Projekty\Travian\tests\test_report_routes.py`
  - `E:\Projekty\Travian\tests\test_recon_cog.py`
  - `E:\Projekty\Travian\tests\test_economy.py`
  - `E:\Projekty\Travian\tests\test_digest.py`
  - `E:\Projekty\Travian\tests\test_diplomacy.py`
  - `E:\Projekty\Travian\tests\test_diplomacy_ui.py`
  - `E:\Projekty\Travian\tests\test_dashboard_routes.py`
  - `E:\Projekty\Travian\tests\test_map.py`
  - `E:\Projekty\Travian\tests\test_auth.py`
  - `E:\Projekty\Travian\tests\test_api_ext.py`
  - `E:\Projekty\Travian\tests\test_api_ext_validation.py`
- **Session outputs (create/update)**
  - `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-inventory.json`
  - `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\web-surface-matrix.json`
  - `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-gaps.json`
  - `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-parity-matrix.json`
  - `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\capability-roadmap.md`
  - `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\rbac-admin-model.md`
  - `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\dashboard-map-api-discovery.md`

## Canonical capability taxonomy

Use these exact labels everywhere in the audit artifacts:

- `identity-profile`
- `attacks`
- `defense-reports`
- `recon-economy`
- `diplomacy`
- `digest-stats`
- `map-analysis`

## Chunk 1: Build the command audit

### Task 1: Inventory Discord commands from code

**Files:**
- Read: `E:\Projekty\Travian\bot\cogs\general.py`
- Read: `E:\Projekty\Travian\bot\cogs\identity.py`
- Read: `E:\Projekty\Travian\bot\cogs\attacks.py`
- Read: `E:\Projekty\Travian\bot\cogs\defense.py`
- Read: `E:\Projekty\Travian\bot\cogs\recon.py`
- Read: `E:\Projekty\Travian\bot\cogs\economy.py`
- Read: `E:\Projekty\Travian\bot\cogs\digest.py`
- Read: `E:\Projekty\Travian\bot\cogs\diplomacy.py`
- Read: `E:\Projekty\Travian\bot\cogs\alerts.py`
- Create: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-inventory.json`

- [ ] **Step 1: Extract all slash command declarations**

Run:
```powershell
rg "@discord\.slash_command|@commands\.slash_command" E:\Projekty\Travian\bot -n
```
Expected: pelna lista definicji slash-komend z numerami linii.

- [ ] **Step 2: Build the raw inventory artifact**

Write rows in this shape:
```json
{
  "command": "/tatak",
  "cog_file": "bot/cogs/attacks.py",
  "handler": "tatak",
  "inputs": ["attacker_name", "defender_village", "coords", "attack_time"],
  "side_effects": ["db_write", "discord_thread_create"],
  "capability": "attacks",
  "notes": ""
}
```

- [ ] **Step 3: Cross-check count against project surfaces**

Run:
```powershell
(rg "@discord\.slash_command|@commands\.slash_command" E:\Projekty\Travian\bot -c --no-filename | ForEach-Object { [int]$_ } | Measure-Object -Sum).Sum
```
Expected: suma zgodna z aktualnym stanem repo (`34` po ostatnim releasie).

- [ ] **Step 4: Verify inventory against README/help only as a drift check**

Run:
```powershell
rg "^\\| `/t|\\*\\*/t" E:\Projekty\Travian\README.md -n
```
Expected: README daje liste porownawcza; rozjazdy ida do `notes`, ale **source of truth zostaje kod**.

- [ ] **Step 5: Do not patch code during inventory**

Expected: jesli znajdziesz bug lub brak, zapisz go do artefaktow zamiast od razu poprawiac. Kazdy fix ma pozniej dostac osobny TDD task.

### Task 2: Map current web and API surfaces to the same capabilities

**Files:**
- Read: `E:\Projekty\Travian\app\routes\dashboard.py`
- Read: `E:\Projekty\Travian\app\routes\map.py`
- Read: `E:\Projekty\Travian\app\routes\attacks.py`
- Read: `E:\Projekty\Travian\app\routes\defense.py`
- Read: `E:\Projekty\Travian\app\routes\reports.py`
- Read: `E:\Projekty\Travian\app\routes\players.py`
- Read: `E:\Projekty\Travian\app\routes\alliances.py`
- Read: `E:\Projekty\Travian\app\routes\search.py`
- Read: `E:\Projekty\Travian\app\routes\diplomacy.py`
- Read: `E:\Projekty\Travian\app\routes\auth.py`
- Read: `E:\Projekty\Travian\app\routes\api_ext.py`
- Read: `E:\Projekty\Travian\app\routes\alerts_web.py`
- Read: `E:\Projekty\Travian\app\templates\dashboard.html`
- Read: `E:\Projekty\Travian\app\templates\attacks.html`
- Read: `E:\Projekty\Travian\app\templates\attack_detail.html`
- Read: `E:\Projekty\Travian\app\templates\defense.html`
- Read: `E:\Projekty\Travian\app\templates\defense_detail.html`
- Read: `E:\Projekty\Travian\app\templates\reports.html`
- Read: `E:\Projekty\Travian\app\templates\report_detail.html`
- Read: `E:\Projekty\Travian\app\templates\diplomacy.html`
- Read: `E:\Projekty\Travian\app\templates\map.html`
- Create: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\web-surface-matrix.json`

- [ ] **Step 1: Extract all current Flask routes**

Run:
```powershell
rg "@.*route\(" E:\Projekty\Travian\app\routes -n
```
Expected: lista tras i endpointow do przypisania pod capability.

- [ ] **Step 2: Record one row per route or API surface**

Write rows in this shape:
```json
{
  "surface": "/attacks",
  "file": "app/routes/attacks.py",
  "type": "web",
  "capability": "attacks",
  "mode": "read_only",
  "auth": "public_or_session",
  "writes_data": false,
  "notes": ""
}
```

- [ ] **Step 3: Mark whether each surface is read-only, write-capable, or auth-only**

Expected labels:
- `read_only`
- `write_capable`
- `oauth_only`
- `extension_ingest`

- [ ] **Step 4: Identify obvious parity overlaps and gaps**

Expected: kazda komenda z `command-inventory.json` ma potem mozliwy match do:
- juz istniejacego web surface
- juz istniejacego API
- albo pelnej luki parity

### Task 3: Verify command correctness with targeted tests and code reads

**Files:**
- Test: `E:\Projekty\Travian\tests\test_general_cog.py`
- Test: `E:\Projekty\Travian\tests\test_identity_cog.py`
- Test: `E:\Projekty\Travian\tests\test_attacks_cog.py`
- Test: `E:\Projekty\Travian\tests\test_attack_routes.py`
- Test: `E:\Projekty\Travian\tests\test_defense.py`
- Test: `E:\Projekty\Travian\tests\test_report_routes.py`
- Test: `E:\Projekty\Travian\tests\test_recon_cog.py`
- Test: `E:\Projekty\Travian\tests\test_economy.py`
- Test: `E:\Projekty\Travian\tests\test_search.py`
- Test: `E:\Projekty\Travian\tests\test_buildtime_cmd.py`
- Test: `E:\Projekty\Travian\tests\test_combat_sim.py`
- Test: `E:\Projekty\Travian\tests\test_safe_distance.py`
- Test: `E:\Projekty\Travian\tests\test_defense_calc.py`
- Test: `E:\Projekty\Travian\tests\test_interception.py`
- Test: `E:\Projekty\Travian\tests\test_digest.py`
- Test: `E:\Projekty\Travian\tests\test_diplomacy.py`
- Test: `E:\Projekty\Travian\tests\test_diplomacy_ui.py`
- Test: `E:\Projekty\Travian\tests\test_dashboard_routes.py`
- Test: `E:\Projekty\Travian\tests\test_map.py`
- Test: `E:\Projekty\Travian\tests\test_auth.py`
- Test: `E:\Projekty\Travian\tests\test_api_ext.py`
- Test: `E:\Projekty\Travian\tests\test_api_ext_validation.py`
- Create: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-gaps.json`
- Create: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-parity-matrix.json`

- [ ] **Step 1: Run the command- and surface-focused test subset**

Run:
```powershell
python -m pytest `
  E:\Projekty\Travian\tests\test_general_cog.py `
  E:\Projekty\Travian\tests\test_identity_cog.py `
  E:\Projekty\Travian\tests\test_attacks_cog.py `
  E:\Projekty\Travian\tests\test_attack_routes.py `
  E:\Projekty\Travian\tests\test_defense.py `
  E:\Projekty\Travian\tests\test_report_routes.py `
  E:\Projekty\Travian\tests\test_recon_cog.py `
  E:\Projekty\Travian\tests\test_economy.py `
  E:\Projekty\Travian\tests\test_search.py `
  E:\Projekty\Travian\tests\test_buildtime_cmd.py `
  E:\Projekty\Travian\tests\test_combat_sim.py `
  E:\Projekty\Travian\tests\test_safe_distance.py `
  E:\Projekty\Travian\tests\test_defense_calc.py `
  E:\Projekty\Travian\tests\test_interception.py `
  E:\Projekty\Travian\tests\test_digest.py `
  E:\Projekty\Travian\tests\test_diplomacy.py `
  E:\Projekty\Travian\tests\test_diplomacy_ui.py `
  E:\Projekty\Travian\tests\test_dashboard_routes.py `
  E:\Projekty\Travian\tests\test_map.py `
  E:\Projekty\Travian\tests\test_auth.py `
  E:\Projekty\Travian\tests\test_api_ext.py `
  E:\Projekty\Travian\tests\test_api_ext_validation.py -q
```
Expected: zielony lub z konkretnymi failami pokazujacymi rozjazdy w obiecanym zachowaniu.

- [ ] **Step 2: Compare test coverage against command inventory**

Expected: oznacz w `command-gaps.json`, ktore komendy:
- maja bezposredni test
- sa pokryte tylko posrednio
- nie maja sensownej oslonki testowej

- [ ] **Step 3: Record correctness findings instead of fixing them**

Write rows in this shape:
```json
{
  "command": "/tdef",
  "status": "needs_fix",
  "evidence": ["tests/test_attacks_cog.py", "bot/cogs/attacks.py"],
  "issue": "Opis i rzeczywiste zachowanie nie sa w pelni zgodne",
  "fix_strategy": "spin out separate TDD task later"
}
```

- [ ] **Step 4: Build the final command parity matrix artifact**

Write rows in this shape:
```json
{
  "command": "/tatak",
  "capability": "attacks",
  "discord_status": "implemented",
  "web_status": "partial",
  "api_status": "none",
  "correctness_status": "ok",
  "min_role": "officer",
  "priority": "high",
  "next_step": "workflow_upgraded_web"
}
```
Expected: `command-parity-matrix.json` jest handoff-ready artefaktem per-komenda, a nie tylko "logiczna" synteza kilku plikow.

## Chunk 2: Turn the audit into a roadmap

### Task 4: Group commands into capabilities and set migration priority

**Files:**
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-inventory.json`
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\web-surface-matrix.json`
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-gaps.json`
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-parity-matrix.json`
- Create: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\capability-roadmap.md`

- [ ] **Step 1: Group commands into stable capability domains**

Start with:
- `identity-profile`
- `attacks`
- `defense-reports`
- `recon-economy`
- `diplomacy`
- `digest-stats`
- `map-analysis`

Expected: kazda komenda nalezy do jednej glownej capability.

- [ ] **Step 2: Score each capability for browser parity value**

Use these factors:
- frequency proxy when no telemetry exists:
  - `high` if the capability coordinates alliance operations or writes shared state
  - `medium` if it is repeatedly used as a calculator/search with multi-field input
  - `low` if it is mostly informational and already visible on the dashboard
- browser/API coverage from `web-surface-matrix.json`
- gap severity from `command-gaps.json`
- number of manual inputs
- amount of tabular/detail data
- need for batch actions
- need for role-based gating

Expected: capability dostaje priorytet `high`, `medium`, albo `low` z jawnym uzasadnieniem opartym na coverage + gap severity, a nie tylko na intuicji.

- [ ] **Step 3: Mark which web parity should be literal, and which should be workflow-upgraded**

Expected examples:
- attack/defense/report capability -> `workflow_upgraded`
- simple info surfaces with already equivalent browser behavior -> `existing_equivalent`
- simple info surfaces without equivalent browser behavior -> `literal_web_needed`

- [ ] **Step 4: Write the prioritized roadmap summary**

Write headings like:
```markdown
## High priority
- attacks
- defense-reports

## Medium priority
- identity-profile
- diplomacy
```

### Task 5: Define RBAC and admin-panel scope from current auth model

**Files:**
- Read: `E:\Projekty\Travian\app\routes\auth.py`
- Read: `E:\Projekty\Travian\app\auth_utils.py`
- Read: `E:\Projekty\Travian\app\models.py`
- Read: `E:\Projekty\Travian\app\routes\*.py`
- Read: `E:\Projekty\Travian\app\templates\*.html`
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\capability-roadmap.md`
- Create: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\rbac-admin-model.md`

- [ ] **Step 1: Document the current auth state exactly**

Run:
```powershell
rg "role_required\(|admin|role" E:\Projekty\Travian\app\routes E:\Projekty\Travian\app\templates -n
```
Expected: potwierdzony obraz, czy sa jakiekolwiek route-level role checks albo istniejace admin UI surface'y.

Expected facts to capture:
- OAuth creates or logs in `User`
- default role is `member`
- no route-level `role_required` coverage today
- no admin UI exists

- [ ] **Step 2: Propose the minimal role model**

Start with:
```text
member -> personal/profile/basic read + permitted self-service
officer -> operational write actions for alliance workflows
leader -> diplomacy / sensitive coordination actions
admin -> role assignment and system governance
```

- [ ] **Step 3: Map capabilities to roles**

Expected output: tabela `capability -> minimum role -> notes`.

- [ ] **Step 4: Define the smallest useful admin panel**

Expected scope:
- list users
- show Discord identity + linked Travian player
- change role
- filter by current role / linked state
- no extra governance features unless audit proves they are needed

### Task 6: Turn dashboard/map redesign and API review into explicit follow-up work

**Files:**
- Read: `E:\Projekty\Travian\app\routes\dashboard.py`
- Read: `E:\Projekty\Travian\app\templates\dashboard.html`
- Read: `E:\Projekty\Travian\app\routes\map.py`
- Read: `E:\Projekty\Travian\app\templates\map.html`
- Read: `E:\Projekty\Travian\app\routes\api_ext.py`
- Read: `E:\Projekty\Travian\app\routes\players.py`
- Read: `E:\Projekty\Travian\app\routes\alliances.py`
- Read: `E:\Projekty\Travian\app\routes\search.py`
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\capability-roadmap.md`
- Create: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\dashboard-map-api-discovery.md`

- [ ] **Step 1: Write the current dashboard and map limitations from code, not vibes**

Expected notes:
- current dashboard blocks / read paths
- current filters
- current marker model
- current popup data
- missing workflow support

- [ ] **Step 2: Translate "GetterTools-like" into concrete questions**

Write prompts like:
```markdown
- Czy potrzebna jest selekcja obszaru / sektorow?
- Czy potrzebne sa warstwy i zapisane widoki?
- Czy potrzebne sa workflow pod croppery, zagrozenia, obrony, wrogow?
- Czy mapa ma byc tylko analityczna, czy tez operacyjna?
```

- [ ] **Step 3: Separate internal API work from external API speculation**

Expected split:
- internal API candidates -> endpoints that would help dashboard/admin/map and existing data views (`players`, `alliances`, `search`, `map`, `api_ext`)
- external API candidates -> only if they reduce scraping/manual work in a real way

- [ ] **Step 4: Rank the follow-up discovery tasks**

Expected output:
- dashboard UX discovery
- map UX discovery
- admin panel UX discovery
- internal API expansion shortlist
- external API research shortlist

### Task 7: Final handoff for the next implementation cycle

**Files:**
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-inventory.json`
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\web-surface-matrix.json`
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-gaps.json`
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\command-parity-matrix.json`
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\capability-roadmap.md`
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\rbac-admin-model.md`
- Read: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files\dashboard-map-api-discovery.md`
- Modify: `C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\plan.md`

- [ ] **Step 1: Check that every approved design requirement has a concrete artifact**

Checklist:
- audit matrix
- correctness findings
- per-command parity matrix
- parity priorities
- RBAC/admin model
- dashboard redesign follow-up
- map redesign follow-up
- API follow-up

- [ ] **Step 2: Update this plan with final findings**

Expected: replace assumptions with audit results, but keep the plan structure readable for the next execution cycle.

- [ ] **Step 3: Create fix spinoffs instead of bundling surprise implementation**

Expected: if the audit finds real bugs, record them as separate implementation tasks with TDD, not as side work inside the audit phase.

- [ ] **Step 4: Verify the audit package is ready for execution handoff**

Run:
```powershell
Get-ChildItem C:\Users\piotr\.copilot\session-state\4befbdce-e0c6-40c2-b965-cb27cb55b5e1\files
```
Expected: wszystkie planowane artefakty istnieja i sa gotowe do wykorzystania w kolejnym cyklu.

## Todo IDs

- `commands-audit-matrix`
- `commands-correctness-review`
- `commands-parity-roadmap`
- `rbac-admin-model`
- `map-ux-discovery` (dashboard + map discovery)
- `api-opportunities-review`

## Dependencies

- `commands-correctness-review` depends on `commands-audit-matrix`
- `commands-parity-roadmap` depends on `commands-audit-matrix` and `commands-correctness-review`
- `rbac-admin-model` depends on `commands-audit-matrix` and `commands-parity-roadmap`
- `map-ux-discovery` (dashboard + map discovery) depends on `commands-parity-roadmap`
- `api-opportunities-review` depends on `commands-parity-roadmap`

## Notes / guardrails

- Source of truth for the audit is **code + tests**, not README or Discord help text
- Any bugfix discovered during the audit must become its own TDD task; do not "just fix it while reading"
- Keep repo clean during the audit unless the user explicitly asks to persist audit results into tracked files
- The admin panel is part of the product requirement, not a stretch goal
- The map redesign stays in scope as a follow-up phase, but the first execution cycle is still the command audit
