from __future__ import annotations
import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass, asdict
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).lower().replace('ł', 'l')) if not unicodedata.combining(c))


def number(value):
    if value is None or isinstance(value, bool): return None
    if isinstance(value, dict): return number(value.get('value'))
    if isinstance(value, list): return number(value[0]) if value else None
    text = re.sub(r'[\s\u00a0\u202f]', '', str(value)).replace(',', '.')
    try:
        n = float(text)
        return n if math.isfinite(n) and n >= 0 else None
    except ValueError: return None


def canonical(url):
    p = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.startswith('utm_') and k not in {'fbclid', 'gclid', 'reason', 'search_reason', 'isPreviewActive'}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), urlencode(sorted(query)), ''))


@dataclass
class Listing:
    source: str
    url: str
    title: str = ''
    price: float | None = None
    currency: str = ''
    area_m2: float | None = None
    lat: float | None = None
    lon: float | None = None
    location: str = ''
    geo_accuracy: str = 'unknown'
    geo_radius_m: float | None = None
    property_type: str = 'unknown'
    transaction: str = 'unknown'
    description: str = ''
    published_at: str = ''
    condition: str = ''
    evidence: str = ''

    def dict(self): return asdict(self)

    @property
    def key(self): return hashlib.sha256(canonical(self.url).encode()).hexdigest()


def distance(lat1, lon1, lat2, lon2):
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = r2 - r1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(r1)*math.cos(r2)*math.sin(dlon / 2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, a)))


def analyze_text(listing):
    """Only attributed statements; no inference of bank approval or legal validity."""
    sentences = [s.strip() for s in re.split(r'[.!?\n]+', listing.description) if s.strip()]
    negative, positive = [], []
    for s in sentences:
        f = fold(s)
        if re.search(r'nie ma mozliwosci.{0,30}kredyt|nie jest mozliw.{0,30}kredyt|tylko\s+(?:za\s+)?gotowk|wylacznie\s+(?:za\s+)?gotowk|brak mozliwosci.{0,25}kredyt|nie (?:ma )?mozna.{0,25}kredyt|bez mozliwosci.{0,25}kredyt', f): negative.append(s[:350])
        elif re.search(r'mozliw.{0,35}(?:zakup.{0,15})?kredyt|kredyt.{0,25}(?:mozliw|akcept)', f): positive.append(s[:350])
    credit = {'status': 'brak danych', 'quotes': [], 'note': 'Deklaracja w ogłoszeniu nie potwierdza decyzji banku.'}
    if negative or positive:
        credit.update(status='sprzeczne deklaracje' if negative and positive else 'tylko gotówka — według ogłoszenia' if negative else 'kredyt możliwy — według ogłoszenia', quotes=(negative+positive)[:4])
    condition = {'status': listing.condition or 'brak danych', 'quotes': []}
    found = []
    for s in sentences:
        f = fold(s)
        for pattern, label in [(r'do remontu|generaln.{0,10}remont', 'do remontu'), (r'stan.{0,15}dewelopersk', 'stan deweloperski'), (r'stan.{0,15}surow', 'stan surowy'), (r'gotow.{0,20}zamieszkan|do wprowadzenia', 'do zamieszkania')]:
            if re.search(pattern, f): found.append((label, s[:350]))
    if found:
        labels = sorted(set(x[0] for x in found))
        condition = {'status': ', '.join(labels) + ' — do weryfikacji w kontekście opisu', 'quotes': [x[1] for x in found[:4]]}
    return {'credit': credit, 'condition': condition}


def assess(listing, config):
    missing, rejected = [], []
    if listing.property_type == 'unknown': missing.append('niepotwierdzony typ nieruchomości')
    elif listing.property_type != 'house': rejected.append('to nie jest dom')
    if listing.transaction == 'unknown': missing.append('niepotwierdzona sprzedaż')
    elif listing.transaction != 'sale': rejected.append('to nie jest sprzedaż')
    if listing.price is None: missing.append('brak ceny')
    elif not config['price_min'] <= listing.price <= config['price_max']: rejected.append('cena poza budżetem')
    if listing.currency.upper() not in {'PLN', 'ZŁ', 'ZL'}: missing.append('brak potwierdzenia ceny w PLN')
    if config.get('area_min', 0) and listing.area_m2 is None: missing.append('brak powierzchni')
    elif listing.area_m2 is not None and listing.area_m2 < config.get('area_min', 0): rejected.append('za mała powierzchnia')
    if config.get('area_max') is not None:
        if listing.area_m2 is None: missing.append('brak powierzchni')
        elif listing.area_m2 > config['area_max']: rejected.append('za duża powierzchnia')
    distances = []
    if listing.lat is None or listing.lon is None:
        missing.append('brak współrzędnych')
    else:
        for city in config['cities']:
            d = distance(listing.lat, listing.lon, city['lat'], city['lon'])
            radius = city.get('radius_km', config['radius_km'])
            uncertainty = (listing.geo_radius_m or 0) / 1000
            distances.append({'city': city['name'], 'km': round(d, 2), 'limit_km': radius, 'within': d <= radius, 'uncertainty_km': uncertainty})
        if not any(x['within'] for x in distances):
            if any(x['km'] - x['uncertainty_km'] <= x['limit_km'] for x in distances): missing.append('niepewna lokalizacja na granicy promienia')
            else: rejected.append('poza promieniem wszystkich miast')
        if listing.geo_accuracy != 'exact' and not config.get('allow_approximate_geo', False): missing.append('lokalizacja przybliżona lub o nieznanej dokładności')
        elif any(x['within'] for x in distances) and not any(x['km'] + x['uncertainty_km'] <= x['limit_km'] for x in distances): missing.append('obszar niepewności przekracza promień')
    text = fold(listing.title + ' ' + listing.description)
    # The portal can label a garden plot, a house kit, or a fractional share as a house.
    # Keep these searchable, but do not present them as confirmed purchases of a house.
    if re.search(r'\brod\b|rodzinn.{0,20}ogrod.{0,15}dzialkow|dzialk.{0,15}rekreacyjn', text):
        missing.append('ogród działkowy lub działka rekreacyjna — sprawdź prawo do nieruchomości')
    if re.search(r'\bdom(?:y|ow|ki|ek)? modulow|\bdom(?:y|ow|ki|ek)? mobiln|na (?:wlasnej )?dzialce klienta|sprzedaz gotowych domkow|gotow.{0,20}do przeniesienia|konstrukcj.{0,30}do samodzielnego montazu', text):
        missing.append('oferta budynku bez potwierdzonej działki')
    if re.search(r'udzial(?:u)?\s+(?:\d+/\d+|w wysokosci\s+\d+/\d+|w nieruchomosci|w prawie)', text):
        missing.append('sprzedaż udziału — sprawdź zakres własności')
    if re.search(r'\bdo zamiany\b|\boferujemy do zamiany\b', text):
        missing.append('oferta zamiany — sprawdź warunki sprzedaży')
    for term in config.get('exclude_keywords', []):
        if fold(term) in text: rejected.append('wykluczone słowo: ' + term)
    missing = sorted(set(missing))
    analysis = analyze_text(listing)
    nearest = min(distances, key=lambda x:x['km']) if distances else None
    # Transparent fit score, not a valuation or "bargain probability".
    parts = []
    if listing.price is not None and config['price_min'] <= listing.price <= config['price_max']:
        parts.append(('cena w budżecie', 40))
    if any(x['within'] for x in distances): parts.append(('punkt lokalizacji w promieniu miasta', 30))
    if listing.property_type == 'house' and listing.transaction == 'sale': parts.append(('potwierdzony dom na sprzedaż', 20))
    if listing.description and listing.area_m2 is not None: parts.append(('opis i powierzchnia dostępne', 10))
    return {'status': 'rejected' if rejected else 'review' if missing else 'match', 'missing': missing, 'reasons': rejected, 'distances': distances, 'nearest': nearest, 'score': sum(x[1] for x in parts), 'score_reasons': parts, 'analysis': analysis}
