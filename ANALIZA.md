# Przegląd repozytoriów i decyzja

Przegląd: 4 listopada 2026. Kod pobrano z GitHub, a wybrane moduły odczytano lokalnie. Nie uruchamiano obcego kodu ani jego instalatorów. Same README nie były podstawą decyzji. Lokalne kopie badawcze nie są częścią dystrybucji projektu.

| Repozytorium | Sprawdzone elementy | Wniosek |
|---|---|---|
| [matercomus/otodom-cli](https://github.com/matercomus/otodom-cli) | `otodom.py`, `store.py`, testy, pliki projektu. Parser wyszukiwarki `searchAds`, parser szczegółów `props.pageProps.ad`, odczyt mapy. Kod ma kryteria `property_type`, `radius`, cenę i lokalizacje. | Najlepiej pasuje jako punkt odniesienia dla Otodom. Nie ma kompletnego monitora 10 portali. W kopii nie znaleziono jawnej licencji, dlatego nie przenoszono kodu. Odczyt współrzędnych przez pierwsze dopasowanie w całym JSON może pomylić dane oferty z innymi obiektami. W nowym parserze zakres ograniczono do lokalizacji głównego ogłoszenia. |
| [mar0ls/olx-monitor](https://github.com/mar0ls/olx-monitor) | `olx_scraper.py`, `otodom_scraper.py`, testy, GUI, licencja MIT. Parser kart OLX używa m.in. `data-testid`, analiza kosztów i ocena LLM, wysyłka i pamięć ofert. | Dużo gotowego kodu, lecz głównie dla kosztów wynajmu. Kalkulacja miesięcznego czynszu nie pasuje do zakupu domu. Wybrano pomysły pamięci ofert i jawnej analizy; nie wprowadzono zależności GUI ani płatnego LLM. |
| [Danieo6/apartment-seeker](https://github.com/Danieo6/apartment-seeker) | `src/drivers/olx.ts`, `src/drivers/otodom.ts`, licencja MIT. OLX korzysta z `.offer`, `.photo-cell`, `.title-cell`; Otodom ze złożonych selektorów i klas `css-*`. | Mały bot Telegram, ale parsery są silnie związane z konkretnym układem HTML i zwracają głównie tekst. W przeanalizowanym kodzie brak współrzędnych, stanu i analizy kredytu. Wymagałby dużej przebudowy. Nie wykorzystano kodu. |
| [marcmos/flatscraper](https://github.com/marcmos/flatscraper) | Moduły `OtodomScraper.hs`, `OlxScraper.hs`, `MorizonScraper.hs`, `NieruchOnlineScraper.hs`, wspólne moduły i GPL-3.0. | Najbogatsze podejście wieloźródłowe, lecz Haskell i kontekst najmu/dojazdu w Krakowie zwiększają koszt adaptacji. Moduł Nieruchomości-online odczytuje zmienną `var map` i zawiera uwagę o niedokładności punktu. Nowy projekt odczytuje deklarację niedokładności zamiast bezwarunkowo uznawać punkt za dokładny. Nie kopiowano implementacji. |
| [ncola/otodom_scraper](https://github.com/ncola/otodom_scraper) | `scraping/search_page.py`, `listing_page.py`, `listing_page_plot.py`, `client.py`, drzewo projektu. Parser danych Next.js, `relatedAds`, historia i konfiguracja miast. | Dobra inspiracja do rozdzielenia źródeł, modelu i historii. Schemat skupia się na mieszkaniach/działkach i PostgreSQL; dla małego osobistego monitora SQLite jest prostszy. W pobranym drzewie nie znaleziono pliku licencji, nie kopiowano kodu. |

## Decyzja

Nowy projekt w Pythonie, wyłącznie standardowa biblioteka, własna implementacja MIT. Użyto publicznie widocznych formatów danych, a nie kodu repozytoriów. Z tych projektów przyjęto pomysły architektoniczne: rozdzielone parsery, przechowywanie historii, pamięć ofert i powiadomienia.

Prawdziwe testy pokazały, że dla Morizon i Gratki potrzeba dekodowania Nuxt/devalue, a OLX ma dane ogłoszenia w `__PRERENDERED_STATE__`. Sam parser JSON-LD nie wystarczał: np. mógł nie dostać współrzędnych albo pomylić metraż działki z metrażem domu. Nowe adaptery identyfikują główny rekord po URL lub identyfikatorze i czytają osobno pole powierzchni domu.

Nie wykorzystano AI w pierwszej wersji. Wybrane wzmianki o stanie i kredycie wykrywane są regułami wraz z cytatem. To ogranicza koszty i nie tworzy pozoru potwierdzenia finansowania przez bank.

## Czego nie można uznać za zakończone

- Potwierdzenie działania Otodom na żywo: żądanie kończyło się HTTP 403.
- Pełne pokrycie i wielostronicowe wyszukiwanie na 10 portalach: test próbki tego nie dowodzi.
- Automatyczne budowanie poprawnych lokalnych wyszukiwań na wszystkich portalach.
- Pewne scalanie duplikatów między portalami, a nie tylko identycznych URL.
- Test dostarczenia na prawdziwe konto Telegram/SMTP: użytkownik nie podał konfiguracji.
- Stałe wdrożenie: przygotowano uruchomienie lokalne i Docker, ale nie aktywowano usługi.

Te ograniczenia są jawne w README i nie są ukryte za deklaracją „obsługuje 10 portali”.
