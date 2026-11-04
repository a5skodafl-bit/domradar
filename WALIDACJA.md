# Walidacja — 4 listopada 2026

Próba sieciowa: jedna strona wyników i jedna oferta na portal. HTML pobrano rzeczywiście; parsery sprawdzano następnie na lokalnych kopiach. Nie testowano pełnej paginacji, kompletności rynku ani wysyłki na rzeczywiste konta.

| Portal | Wyniki | Szczegóły próbki | Współrzędne |
|---|---|---|---|
| otodom | HTTP Error 403: Forbidden | Niepotwierdzone | nie |
| olx | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| morizon | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| gratka | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| nieruchomosci-online | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| domiporta | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| adresowo | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| sprzedajemy | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| lento | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | tak |
| szybko | HTTP 200 | Cena w PLN, typ i sprzedaż odczytane | nie |

**9 parsowalnych przykładowych ogłoszeń, 8 ze współrzędnymi.** To nie potwierdza bezawaryjności całych integracji. Nieruchomości-online zwróciło 503 dla jednej oferty; inna została pobrana. Dla inwestycji deweloperskiej JSON-LD wskazywało całą inwestycję zamiast konkretnego domu — nie przyjęto ceny innego lokalu.

Otodom: HTTP 403; dedykowany parser zweryfikowano tylko syntetycznie. Szybko: brak współrzędnych w próbce — ręczna weryfikacja zamiast automatycznego alertu odległości.

**28/28 testów automatycznych zaliczonych.** Obejmują budżet, obszary miast, niepełne dane, niepewność lokalizacji, brak zgadywania kredytu, parsowanie, metraż domu i działki, historię cen, powtarzanie ofert, ponawianie wysyłki, niezależność kanałów, pierwszy skan i powrót po błędzie szczegółów, a także wyświetlanie niezaufanego HTML.

Sprawdzono demonstrację, generowanie raportu i eksport JSON. Nie testowano budowania Dockera ani wysyłki na rzeczywiste konta.

Testy: `python -m unittest discover -s tests -v`. Próba sieciowa na własnej konfiguracji: `python scripts/check_sources.py config.json` (bez powiadomień). Szczegóły i hashe odpowiedzi: `live-validation.json`.
