# Polityka Prywatności — W.I.T.E.K

**Data wejścia w życie:** 13 kwietnia 2026

## 1. Wprowadzenie

W.I.T.E.K to rozszerzenie przeglądarki Chrome / Chromium przeznaczone dla sojuszów grających w Travian Legends. Rozszerzenie pomaga graczom ręcznie przekazywać dane taktyczne do systemu analitycznego sojuszu.

Ta polityka wyjaśnia, jakie dane są wysyłane i jak są przetwarzane.

## 2. Dane zbierane przez rozszerzenie

Rozszerzenie zbiera **wyłącznie dane, które gracz aktywnie wysyła** po kliknięciu przycisku „Wyślij do W.I.T.E.K”. Mogą to być:

- **Raporty bitewne**: jednostki atakujące/broniące, straty, zdobycz
- **Raporty szpiegowskie**: zasoby, wojska, typ raportu szpiega
- **Stan wojsk**: liczba jednostek w wiosce
- **Nadchodzące ataki**: źródło, cel, jednostki, czas przyjazdu
- **Wybrane dane gospodarcze i bohatera**: stan bohatera, dane rynku i kolejki szkolenia

Wszystkie dane pochodzą ze stron Travian Legends, które gracz już widzi w swojej przeglądarce. Dane trafiają do token-protected API W.I.T.E.K-a pod ścieżkami `/api/ext/*`, w tym `/api/ext/game-data` dla danych `hero` / `marketplace` / `training`.

**Rozszerzenie NIE:**
- nie śledzi aktywności gracza automatycznie,
- nie zbiera danych z innych stron niż strony Travian Legends, na których działa rozszerzenie,
- nie rejestruje historii przeglądania,
- nie wysyła niczego bez wyraźnej akcji użytkownika.

## 3. Przechowywanie danych

- **Na urządzeniu gracza**: ustawienia (URL API, token) przechowywane w `chrome.storage.sync`
- **Na serwerze sojuszu**: dane wysłane przez gracza, wykorzystywane do analityki i koordynacji
- Gracz może usunąć dane lokalne, odinstalowując rozszerzenie

## 4. Udostępnianie danych

Dane wysłane do serwera sojuszu mogą być widoczne dla:
- liderów i oficerów sojuszu (do celów taktycznych),
- administratorów systemu W.I.T.E.K (do celów technicznych).

Dane **nie** są sprzedawane stronom trzecim ani wykorzystywane do celów reklamowych.

## 5. Bezpieczeństwo

- rozszerzenie wysyła dane pod adres serwera skonfigurowany przez użytkownika; zalecamy używanie adresu `https://`,
- token API jest przechowywany w pamięci przeglądarki (`chrome.storage.sync`),
- rekomendujemy używanie silnych haseł do kont sojuszu i prywatnego tokena API.

## 6. Zmiany polityki

Zmiany w tej polityce będą publikowane na tej stronie. Korzystając z rozszerzenia po zmianach, akceptujesz nową wersję polityki.

## 7. Kontakt

W razie pytań dotyczących prywatności skontaktuj się z administratorem narzędzia lub liderami sojuszu korzystającego z W.I.T.E.K-a.

---

**W.I.T.E.K — Wirtualny Informator Taktyczno-Ekonomiczny Koalicji**  
W.I.T.E.K dla Travian Legends — profil serwera konfigurowany w aplikacji





