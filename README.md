# DomRadar — domy na sprzedaż wokół wybranych miast

Monitor w Pythonie 3.11+ z trwałą bazą SQLite i przeglądalną stroną ogłoszeń. Bez zewnętrznych bibliotek i bez płatnego API. Publiczna strona działa pod `https://a5skodafl-bit.github.io/domradar/`; szczegóły wdrożenia są w [DEPLOYMENT.md](DEPLOYMENT.md). Powiadomienia mogą trafiać na Telegram lub e-mail. Uzasadnienie projektu jest w ANALIZA.md.

Skan działa cyklicznie przez GitHub Actions, a baza i strona zachowują oferty pomiędzy skanami. Pełne pokrycie portali nie jest potwierdzone. Otodom blokował pobieranie HTTP 403; Szybko nie udostępniło współrzędnych w badanej ofercie. Szczegóły testów: WALIDACJA.md.

## Szybki start

Rozpakuj archiwum, przejdź do folderu `domradar`, a następnie:

```bash
python -m domradar init
python -m domradar demo
```

Otwórz `data/demo.html`. Są tam **fikcyjne** oferty do prezentacji raportu, oddzielone od rzeczywistej bazy. Nic nie jest wysyłane.

Gotowy profil wyszukiwania dla 10 największych miast (według ludności), promienia 15 km od centrum i ceny do 300 000 zł znajduje się w `config.top10.json`. Na docelowym serwerze skopiuj go do `config.json`. Nie ma limitu powierzchni. Aktywnym źródłem jest Morizon, z osobnym adresem wyszukiwania i filtrem ceny dla każdego miasta. Portalowe strony miast mogą pominąć oferty z miejscowości sąsiednich, choć mieszczą się one w promieniu 15 km; nie należy traktować profilu jako kompletnego przeglądu tego promienia. Morizon podaje współrzędne bez potwierdzenia ich dokładności, więc wyniki mają status „Do sprawdzenia” także wtedy, gdy wyliczona odległość jest mniejsza niż 15 km.

Otwórz utworzony `config.json`. Przykładowy budżet 1 mln zł, 80 m² i Warszawa są wyłącznie wartościami startowymi, nie ustalonymi preferencjami użytkownika.

1. Ustaw `price_min`, `price_max`, ewentualnie `area_min` i `area_max`.
2. W `cities` wpisz miasta z ich współrzędnymi. Każde może mieć osobny `radius_km`. Warunek: oferta jest w promieniu **co najmniej jednego** z nich.
3. Dla wybranych portali ustaw `enabled: true` i podmień `search_urls` na linki do wyszukiwań domów na sprzedaż w interesujących okolicach, najlepiej od najnowszych. Możesz dodać kilka linków na portal, np. osobny dla każdego miasta.
4. Uruchom próbny skan:

```bash
python -m domradar once
```

Otwórz `data/raport.html`. To przeglądalny widok zapisanej bazy: wyszukuj ogłoszenia, filtruj miasto, status i cenę, sortuj wyniki. W sekcji „Stan źródeł” sprawdzaj, które skany się udały. Testuj konfigurację na jednym portalu i jednej okolicy, zanim włączysz pozostałe.

**Ważne: filtry centralne sprawdzają pobrane oferty. Nie generują automatycznie filtrów wszystkich portali.** Wyszukiwania źródłowe muszą obejmować całą interesującą okolicę. Przykładowe linki są ogólnopolskie: pierwsze dwie strony całej Polski nie wystarczą do kompletnego monitorowania okolic Warszawy. Ustaw linki lokalne oraz odpowiednie `pages_per_search` i `max_details_per_search`. Program sygnalizuje przekroczenie limitu szczegółów oraz powtarzające się strony, ale nie gwarantuje pobrania całej bazy portalu. Paginacja z parametrem `page` wymaga sprawdzenia na każdym konkretnym wyszukiwaniu.

## Miasta, odległość i dane niepełne

```json
"cities": [
  {"name": "Warszawa", "lat": 52.2297, "lon": 21.0122, "radius_km": 40},
  {"name": "Łódź", "lat": 51.7592, "lon": 19.4560, "radius_km": 30}
]
```

Dalsze przykładowe punkty centrów: Kraków 50.0647/19.9450, Wrocław 51.1079/17.0385, Poznań 52.4064/16.9252, Gdańsk 54.3520/18.6466. Możesz wpisać dowolny punkt odniesienia — nie musisz używać centrum administracyjnego.

Odległość liczona jest **w linii prostej**, nie samochodem. Współrzędne mogą wskazywać przybliżoną lokalizację. `allow_approximate_geo: true` w przykładzie dopuszcza takie punkty do alertów; raport zawsze pokazuje ich dokładność. Ustaw `false`, jeżeli chcesz wymagać zadeklarowanej dokładnej lokalizacji. Obszar niepewności przecinający granicę promienia trafia do ręcznej weryfikacji. Brak współrzędnych, ceny, waluty, typu nieruchomości lub sprzedaży oznacza „Do sprawdzenia”, a nie automatyczny alert.

## Powiadomienia na Telegram

Utwórz własnego bota przez BotFather i ustal identyfikator swojego czatu. Przechowuj token w zmiennej środowiskowej, nie w pliku konfiguracji ani repozytorium.

W `config.json`: `notifications.telegram.enabled: true`.

```bash
export TELEGRAM_BOT_TOKEN='TWÓJ_TOKEN'
export TELEGRAM_CHAT_ID='TWÓJ_CHAT_ID'
python -m domradar watch --send
```

W PowerShell ustaw zmienne przez `$env:TELEGRAM_BOT_TOKEN = '...'` i `$env:TELEGRAM_CHAT_ID = '...'`. Wyłącz komputer — monitoring przestanie działać. Pierwszy skan tworzy punkt odniesienia bez zasypywania starymi ofertami (`notify_initial: false`). Kolejne nowe wykryte oferty spełniające filtry trafiają do kolejki. `notify_initial: true` pozwala dostać również oferty początkowe.

`poll_minutes` określa odstęp między końcem skanu a następnym skanem; domyślnie 60 min. `digest_minutes` określa minimalny odstęp między wysyłkami; domyślnie 360 min. E-mail łączy oferty w zestawienie, Telegram wysyła serię wiadomości podczas tej samej wysyłki. Pierwsza wysyłka kolejki może nastąpić od razu; dalsze zgodnie z interwałem. Nie ma tutaj automatycznego zadania w ChatGPT.

Wysłane oferty są zapamiętywane w SQLite. Błąd jednego kanału nie blokuje drugiego; niewysłane wpisy pozostają w kolejce. Dostarczenie ma semantykę **co najmniej raz** — awaria po zaakceptowaniu wiadomości przez usługę, ale przed zapisem potwierdzenia, może spowodować powtórzenie. Ponowne uruchomienie z zachowaną bazą nie zeruje historii.

## E-mail

Włącz `notifications.email.enabled`, ustaw `SMTP_HOST`, `SMTP_PORT` (domyślnie 465), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO`, a następnie użyj `watch --send`. Obsługiwane jest SMTP przez TLS od początku połączenia (SMTPS), nie STARTTLS na 587. Hasło aplikacji może być wymagane przez dostawcę poczty. Bez `--send` nie ma wysyłki; powstają raport i kolejka.

## Docker — uruchomienie ciągłe

Po przygotowaniu konfiguracji skopiuj `.env.example` do `.env`, uzupełnij dane i uruchom:

```bash
docker compose up -d --build
docker compose logs -f
```

Dane są w `./data`, konfiguracja w `./config.json`. `docker compose down` zatrzymuje usługę, ale nie usuwa bazy. Konfigurację i sekrety zmieniaj lokalnie. Domyślny obraz ma strefę Europe/Warsaw. Uruchomienie bez Dockera używa czasu lokalnego systemu.

### Udostępnienie raportu przez HTTPS

Opcjonalna usługa `web` serwuje wyłącznie aktualny `data/raport.html` pod adresem `/`, z hasłem HTTP Basic. Baza SQLite, konfiguracja i eksport JSON nie są dostępne przez WWW. Serwer Caddy automatycznie uzyskuje i odnawia certyfikat HTTPS dla domeny wskazującej na serwer.

1. Przygotuj `config.json` z własnymi miastami, budżetem i co najmniej jednym włączonym źródłem. Skopiuj `.env.example` do `.env` i uzupełnij potrzebne zmienne powiadomień. Jeśli chcesz tylko raport, pozostaw powiadomienia wyłączone; `--send` bez włączonego kanału nic nie wyśle.
2. Skieruj rekord DNS A lub AAAA domeny na publiczny adres serwera. Otwórz porty TCP 80 i 443. Na komputerze w domu potrzebne jest także przekierowanie portów na routerze dla IPv4; komputer musi działać stale.
3. W `.env` ustaw `DOMRADAR_DOMAIN` na swoją domenę (bez `https://`) oraz `DOMRADAR_USER` na nazwę użytkownika. Wygeneruj hash hasła, wpisując hasło w interaktywnym terminalu:

   ```bash
   docker run --rm -it caddy:2.10-alpine caddy hash-password
   ```

   W `.env` wklej wynik jako `DOMRADAR_PASSWORD_HASH='...hash...'`. Pojedyncze cudzysłowy chronią znaki `$` przed interpretacją przez Compose. Nie zapisuj jawnego hasła w `.env`.
4. Uruchom obie usługi:

   ```bash
   docker compose --profile web up -d --build
   docker compose ps
   docker compose logs --tail=100 monitor web
   ```

Otwórz `https://TWOJA_DOMENA/`. Raport pojawi się po pierwszym zakończonym skanie; przy domyślnej konfiguracji może to potrwać, ponieważ skan pobiera strony po kolei z opóźnieniem między żądaniami. Kod HTTP 404 wcześniej oznacza, że raport jeszcze nie powstał. Zmiana `config.json` wymaga ponownego uruchomienia monitora: `docker compose restart monitor`.

### Tymczasowy publiczny podgląd bez domeny

`compose.preview.yaml` udostępnia oznaczony raport demonstracyjny przez Cloudflare Quick Tunnel. Nie uruchamia monitora prawdziwych ofert. Raport jest chroniony hasłem z lokalnego `.env`. Uruchomienie i odczyt aktualnego adresu:

```bash
docker compose -f compose.preview.yaml up -d
docker compose -f compose.preview.yaml logs tunnel
```

Adres `*.trycloudflare.com` jest tymczasowy: zmienia się po odtworzeniu tunelu i przestaje działać, gdy ten komputer lub kontener są wyłączone. Do stałego adresu użyj własnej domeny i wdrożenia HTTPS opisanego wyżej.

Wariant z darmową maszyną działającą niezależnie od komputera opisano w `DEPLOYMENT.md`.

## Stan i możliwość kredytu (opcjonalne)

Domyślny alert zawiera tylko podstawowe informacje i link do źródła. Ustaw `include_analysis: true`, aby dołączyć ocenę, stan i wzmianki o kredycie. Brak opisu, stanu lub informacji o kredycie nie blokuje alertu; metraż jest wymagany tylko wtedy, gdy ustawiono jego filtr.

Analiza jest regułowa, bez LLM: wykrywa wybrane wzmianki w opisie, zachowuje cytaty i oznacza sprzeczne deklaracje. „Brak informacji” nie znaczy „nie można kupić na kredyt”. Księga wieczysta lub pełna własność same nie powodują oznaczenia możliwości kredytu. Gotowość banku do finansowania wymaga osobnego sprawdzenia.

Ocena 0–100 mierzy **dopasowanie i kompletność**: 40 pkt za budżet, 30 za punkt w promieniu, 20 za potwierdzony dom na sprzedaż, 10 za opis i powierzchnię. To nie jest wycena, ocena stanu technicznego ze zdjęć ani wykrywanie okazji. Oferty są traktowane jako niezaufane dane i nie sterują zachowaniem programu.

## Zakres i ograniczenia

- Dziesięć skonfigurowanych portali nie oznacza dziesięciu niezawodnych integracji. Zmiany HTML mogą wymagać aktualizacji.
- Otodom: dedykowany parser danych Next.js, ale bieżący odczyt sieciowy z tego środowiska blokowany.
- OLX: JSON-LD i dane prerenderowane; Morizon/Gratka: JSON-LD i Nuxt; pozostałe: JSON-LD, metadane i wybrane dane map.
- Osiągnięcie HTTP 200 i parsowanie jednej oferty nie potwierdza pokrycia całego portalu ani skutecznej paginacji.
- Deduplikacja dotyczy tego samego kanonicznego URL, także gdy występuje w kilku wyszukiwaniach. **Nie ma jeszcze pewnego łączenia tej samej nieruchomości między portalami.** Może przyjść więcej niż jeden alert o tym samym domu.
- Odświeżenie starego ogłoszenia pod tym samym URL nie jest nową ofertą. Nowy URL może wygenerować nowy alert. „Nowe” oznacza nowo wykryte przez monitor, nie gwarantowaną datę publikacji.
- Historia cen jest zapisywana, ale alerty dotyczą nowych ofert, nie każdej obniżki.
- Nie oznaczamy automatycznie ofert jako usuniętych: nieobecność w ograniczonej liczbie stron tego nie dowodzi.
- Błędy i braki są widoczne w raporcie. Nie ma osobnego alarmu o awarii portalu; raport trzeba okresowo kontrolować.
- Brak omijania CAPTCHA lub blokad. Nie wysyłamy żądań równolegle do jednego portalu, a opóźnienie minimalne to 1 s.

## Pozostałe komendy

```bash
python -m domradar report               # odśwież HTML z bazy, bez sieci
python -m domradar export               # data/oferty.json
python -m domradar flush --send         # wyślij kolejkę teraz
python -m unittest discover -s tests -v
```

Testy automatyczne używają syntetycznych danych i atrap sieci. Wyniki prób rzeczywistych są oddzielnie opisane w WALIDACJA.md. Do stałego uruchomienia trzeba ustalić miasta, budżet i kanał powiadomień oraz sprawdzić lokalne wyszukiwania. Projekt można rozwijać bez opłat licencyjnych; własny serwer, poczta lub dostęp do internetu mogą kosztować.
