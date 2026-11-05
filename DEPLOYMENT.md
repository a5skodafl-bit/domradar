# DomRadar: bezpłatny serwer działający niezależnie od komputera

## Wariant bez karty: GitHub Actions + GitHub Pages

Publiczna baza ogłoszeń jest publikowana pod adresem `https://a5skodafl-bit.github.io/domradar/`. Strona umożliwia wyszukiwanie, filtrowanie po mieście, cenie i statusie oraz sortowanie zapisanych ofert. Workflow `.github/workflows/scan-and-publish.yml` uruchamia monitor co 3 godziny na maszynie GitHub, zachowuje stan SQLite w publicznym repozytorium i publikuje widok HTML przez Pages. Nie potrzeba VM ani karty. Skan można uruchomić ręcznie przez **Actions → Scan offers and publish report → Run workflow**. Publikacja wymaga ustawienia **Pages → Build and deployment → GitHub Actions**.

Wymagane jest publiczne repozytorium GitHub na darmowym planie. GitHub Pages jest publiczny bez logowania. Plik SQLite w repozytorium również jest publiczny; nie zapisuj w nim sekretów. Strona pokazuje stan zapisanej bazy z ostatniego ukończonego skanu, a filtry działają w przeglądarce. Skan działa cyklicznie, a nie jako stały proces. Zaplanowane zadania mogą się opóźnić lub zostać pominięte przy obciążeniu GitHub. Skany mogą także zostać wyłączone po 60 dniach bez aktywności repozytorium. Sprawdzaj historię Actions i stan źródeł na stronie.

Profil `config.top10.json` obejmuje 10 największych miast, promień 15 km, brak limitu metrażu oraz limity ceny per miasto: Warszawa 700 000 zł, Kraków 500 000 zł, Wrocław i Lublin 400 000 zł, pozostałe miasta 300 000 zł. Aktywne są miejskie wyszukiwania Otodom, OLX, Morizon, Gratka, Nieruchomości-Online, Domiporta, Adresowo i Lento. OLX jest pobierany przez lekki klient HTTP Scrapling z odciskiem TLS Chrome; nie jest uruchamiana pełna przeglądarka. Adresowo pobiera dostępny w portalu promień 20 km, po czym DomRadar stosuje właściwy limit 15 km. Niepotwierdzona dokładność współrzędnych powoduje oznaczenie „Do sprawdzenia”, zanim lokalizacja zostanie uznana za pewną. Zdjęcia są ładowane bezpośrednio z adresów udostępnionych w metadanych portali; niedostępny obraz jest automatycznie ukrywany. Mapy OpenStreetMap są ładowane dopiero w pobliżu widoku, aby nie obciążać przeglądarki.

### Domena DigitalPlat FreeDomain

[DigitalPlat FreeDomain](https://github.com/DigitalPlatDev/FreeDomain) oferuje nazwy w `.dpdns.org`, `.us.kg`, `.qzz.io`, `.xx.kg` i `.qd.je`, ale **nie hostuje aplikacji**. Daje domyślnie jedną domenę na konto i wymaga zewnętrznych serwerów nazw DNS; rejestracja wymaga danych kontaktowych. Aktualne warunki i ewentualne wymagania dotyczące slotów lub opłat trzeba sprawdzić w panelu przed rejestracją. Domena może wskazywać na GitHub Pages po uruchomieniu strony i skonfigurowaniu DNS. Sam adres `github.io` jest już darmowy, więc domena DigitalPlat jest opcjonalna.

## Wybór hostingu

Najbliższy wymaganiu ciągłej pracy bez opłat jest **Oracle Cloud Always Free VM**. Bezpłatne zasoby obejmują maszyny wirtualne, dysk i publiczny adres IP. Wybierz oznaczony „Always Free eligible” wariant Ampere A1, jeśli jest dostępny, albo AMD E2.1.Micro. Założenie konta wymaga danych karty do weryfikacji. Oracle może odzyskać bezczynne instancje i czasem brakuje wolnych maszyn; darmowy plan nie ma SLA ani gwarancji 100% dostępności.

Alternatywa: **Google Cloud Free Tier e2-micro** w jednym z trzech kwalifikujących się regionów USA. Trzeba pilnować limitów dysku i transferu oraz aktywnego konta rozliczeniowego; po zakończeniu okresu próbnego pełne konto może naliczyć opłaty za zasoby poza darmowym limitem.

Render Free nie pasuje do działającego stale monitora: usypia serwis po 15 minutach bez ruchu i traci lokalną bazę SQLite przy ponownym uruchomieniu.

## Bezpłatny adres

- `sslip.io` tworzy nazwę DNS z publicznego IPv4 bez rejestracji: dla adresu `203.0.113.10` użyj `domradar.203-0-113-10.sslip.io`. Nazwa zmienia się wraz ze zmianą IP. Certyfikat HTTPS może być wystawiony przez Caddy, jeśli porty 80/443 są publiczne.
- DuckDNS daje darmową subdomenę `nazwa.duckdns.org`, ale wymaga konta i aktualizacji rekordu po zmianie IP. dynv6 jest podobną alternatywą.

## Uruchomienie na Oracle VM

1. Utwórz konto Oracle Cloud Free Tier i maszynę Ubuntu oznaczoną **Always Free eligible**, z publicznym IPv4. Dodaj swój klucz publiczny SSH podczas tworzenia maszyny.
2. W regułach sieci Oracle otwórz przychodzące TCP 22, 80 i 443. Na maszynie zainstaluj Docker Engine i wtyczkę Docker Compose według instrukcji Dockera dla Ubuntu.
3. Skopiuj pliki projektu na maszynę. Na serwerze uruchom `cp config.top10.json config.json` oraz `cp .env.example .env`.
4. Ustaw w `.env` `DOMRADAR_DOMAIN` na wybraną subdomenę, `DOMRADAR_USER` na nazwę użytkownika i `DOMRADAR_PASSWORD_HASH` na hash wygenerowany poleceniem `docker run --rm -it caddy:2.10-alpine caddy hash-password`. Hash w `.env` ujmij w pojedyncze cudzysłowy.
5. W katalogu projektu uruchom `docker compose --profile web up -d --build`. Sprawdź `docker compose ps` oraz `docker compose logs --tail=100 monitor web`, potem otwórz adres przez HTTPS.

Monitor zapisuje bazę w `./data`, a Caddy wystawia jedynie raport HTML. Kontenery mają `restart: unless-stopped`. Warto robić kopię `data/domradar.sqlite3`, bo awaria lub usunięcie VM może utracić historię.
