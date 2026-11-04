# Walidacja — 4 listopada 2026

Próba sieciowa: jedna strona wyników i jedna oferta na portal. HTML pobrano rzeczywiście; parsery sprawdzano następnie na lokalnych kopiach. Nie testowano pełnej paginacji, kompletności rynku ani wysyłki na rzeczywiste konta.

| Portal | Wyniki | Szczegóły próbki | Współrzędne |
|---|---|---|---|
| otodom | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| olx | HTTP 200 przez Scrapling | Cena w PLN, typ i sprzedaż odczytane | tak |
| morizon | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| gratka | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| nieruchomosci-online | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| domiporta | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| adresowo | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| sprzedajemy | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| lento | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| szybko | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | nie |

Aktywna konfiguracja obejmuje osiem źródeł: Otodom, OLX, Morizon, Gratka, Nieruchomości-Online, Domiporta, Adresowo i Lento. Próbki wszystkich aktywnych adapterów były parsowalne; to nie potwierdza bezawaryjności całych integracji. Nieruchomości-online zwróciło 503 dla jednej oferty; inna została pobrana. Dla inwestycji deweloperskiej JSON-LD wskazywało całą inwestycję zamiast konkretnego domu — nie przyjęto ceny innego lokalu.

Otodom zwrócił bieżące dane Next.js. Standardowy klient HTTP dla OLX zwracał 403, natomiast lekki Fetcher Scrapling zwrócił publiczną stronę bez uruchamiania przeglądarki. Szybko nie jest częścią aktywnego profilu.

**31/31 testów automatycznych zaliczonych.** Obejmują budżet, obszary miast, wykluczanie ROD także z historycznych wpisów, niepełne dane, niepewność lokalizacji, brak zgadywania kredytu, parsowanie, metraż domu i działki, historię cen, powtarzanie ofert, ponawianie wysyłki, niezależność kanałów, pierwszy skan i powrót po błędzie szczegółów, a także bezpieczne wyświetlanie niezaufanego HTML i obecność osobistych stanów ofert.

Sprawdzono demonstrację, generowanie raportu i eksport JSON. Nie testowano budowania Dockera ani wysyłki na rzeczywiste konta.

Testy: `python -m unittest discover -s tests -v`. Próba sieciowa na własnej konfiguracji: `python scripts/check_sources.py config.json` (bez powiadomień). Szczegóły i hashe odpowiedzi: `live-validation.json`.
