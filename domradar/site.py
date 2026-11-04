"""Build a searchable, static view of the persistent listings database."""

from __future__ import annotations

import html
import json
import time
from pathlib import Path


def _escape(value):
    return html.escape(str(value if value is not None else 'brak danych'), quote=True)


def _number(value, suffix=''):
    if value is None:
        return 'brak danych'
    return f'{value:,.0f}'.replace(',', ' ') + suffix


def render(db, path, include_analysis=False, config=None):
    rows = db.execute('''SELECT payload, assessment, first_seen, last_seen
                         FROM listings ORDER BY last_seen DESC''').fetchall()
    scans = db.execute('''SELECT at, source, status, discovered, parsed, error
                          FROM scans ORDER BY at DESC LIMIT 100''').fetchall()
    cards = []
    city_names = set()
    for payload, assessment, first_seen, last_seen in rows:
        item = json.loads(payload)
        result = json.loads(assessment)
        near = result.get('nearest') or {}
        city = near.get('city') or ''
        if city:
            city_names.add(city)
        status = result['status']
        label = {'match': 'Pasuje', 'review': 'Do sprawdzenia', 'rejected': 'Poza kryteriami'}.get(status, status)
        price = item.get('price')
        distance = f"{near['km']} km od {city}" if near else 'Brak współrzędnych'
        note = '; '.join(result.get('missing', []) + result.get('reasons', []))
        analysis = result.get('analysis') or {}
        extra = ''
        if include_analysis:
            extra = (f"<p>Stan: {_escape((analysis.get('condition') or {}).get('status'))} · "
                     f"Kredyt: {_escape((analysis.get('credit') or {}).get('status'))}</p>")
        cards.append(f'''<article class="offer" data-status="{_escape(status)}" data-city="{_escape(city)}"
            data-price="{_escape(price if price is not None else '')}" data-distance="{_escape(near.get('km', ''))}"
            data-seen="{_escape(last_seen)}">
          <div class="offer-top"><span class="badge { _escape(status) }">{_escape(label)}</span><span class="source">{_escape(item.get('source'))}</span></div>
          <h2><a href="{_escape(item.get('url'))}" target="_blank" rel="noopener noreferrer">{_escape(item.get('title') or 'Ogłoszenie bez tytułu')}</a></h2>
          <p class="price">{_escape(_number(price, ' zł'))}</p>
          <p>{_escape(item.get('location') or 'Brak lokalizacji')} · {_escape(distance)} · {_escape(_number(item.get('area_m2'), ' m²'))}</p>
          <p class="meta">Widziane: {_escape(time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(last_seen)))} · Lokalizacja: {_escape(item.get('geo_accuracy'))}</p>
          {f'<p class="note">{_escape(note)}</p>' if note else ''}{extra}
          <details><summary>Opis i szczegóły</summary><p class="description">{_escape(item.get('description') or 'Brak opisu')}</p>
          <p class="meta">Pierwszy raz w bazie: {_escape(time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(first_seen)))}</p></details>
        </article>''')

    options = ''.join(f'<option value="{_escape(city)}">{_escape(city)}</option>' for city in sorted(city_names))
    max_price = config.get('price_max') if config else None
    last_scan = max((row[0] for row in scans), default=None)
    freshness = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(last_scan)) if last_scan else 'jeszcze nie wykonano'
    scan_rows = ''.join(
        f'<tr><td>{_escape(time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(at)))}</td>'
        f'<td>{_escape(source)}</td><td>{_escape(status)}</td><td>{discovered}/{parsed}</td>'
        f'<td>{_escape(error)}</td></tr>'
        for at, source, status, discovered, parsed, error in scans
    )
    document = f'''<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DomRadar — baza ogłoszeń domów</title>
<style>
:root{{font-family:system-ui,sans-serif;color:#163047;background:#f2f6f8}}*{{box-sizing:border-box}}
body{{max-width:1120px;margin:0 auto;padding:28px 20px 70px}}h1{{font-size:clamp(2rem,5vw,3.4rem);margin:.2em 0}}
h2{{font-size:1.2rem;margin:12px 0}}a{{color:#087083}}a:hover{{text-decoration-thickness:2px}}
.intro,.meta,.source{{color:#597184}}.intro{{max-width:750px;line-height:1.55}}
.summary{{display:flex;gap:14px;flex-wrap:wrap;margin:22px 0}}.summary span{{background:#fff;padding:12px 16px;border-radius:12px;box-shadow:0 2px 8px #1330470d}}
.filters{{display:grid;grid-template-columns:2fr repeat(3,1fr);gap:12px;background:#fff;padding:18px;border-radius:18px;box-shadow:0 2px 12px #13304712}}
label{{display:grid;gap:5px;font-weight:600;font-size:.88rem}}input,select{{font:inherit;width:100%;padding:11px;border:1px solid #b8cbd3;border-radius:9px;background:#fff;color:#163047}}
.sortbar{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:24px 0 12px;flex-wrap:wrap}}.sortbar label{{display:flex;align-items:center;gap:8px}}
.sortbar select{{width:auto}}.offer{{background:#fff;padding:20px 24px;margin:12px 0;border-radius:16px;box-shadow:0 2px 12px #13304712}}
.offer-top{{display:flex;justify-content:space-between;align-items:center;gap:12px}}.badge{{padding:4px 10px;border-radius:100px;font-size:.85rem;font-weight:700;background:#dbe9ec}}
.badge.match{{background:#d9f4e6;color:#17613b}}.badge.review{{background:#fff0c8;color:#795500}}.badge.rejected{{background:#e6e9ec;color:#56616b}}
.price{{font-weight:750;font-size:1.3rem;margin:8px 0}}.note{{color:#8a4b19}}.description{{white-space:pre-wrap;line-height:1.55}}
details{{border-top:1px solid #e4eaed;padding-top:12px}}summary{{cursor:pointer;font-weight:600}}button{{padding:11px 18px;border:1px solid #087083;color:#087083;background:white;border-radius:9px;cursor:pointer}}
#more{{display:block;margin:24px auto}}#empty{{background:#fff;padding:28px;border-radius:16px}}.hidden{{display:none!important}}
table{{border-collapse:collapse;width:100%;font-size:.82rem}}td,th{{border-bottom:1px solid #d7e0e5;text-align:left;padding:8px;vertical-align:top;overflow-wrap:anywhere}}
.table-wrap{{overflow-x:auto}}.health{{margin-top:55px}}.health details{{margin-top:16px}}@media(max-width:760px){{.filters{{grid-template-columns:1fr 1fr}}}}@media(max-width:510px){{.filters{{grid-template-columns:1fr}}}}
</style></head><body>
<header><h1>DomRadar</h1><p class="intro">Baza domów na sprzedaż w pobliżu 10 największych miast Polski. Przeszukuj zapisane ogłoszenia, filtruj wyniki i otwieraj oferty u źródła.</p></header>
<div class="summary"><span><strong>{len(rows)}</strong> ogłoszeń w bazie</span><span>Ostatni skan: <strong>{_escape(freshness)}</strong></span><span>Budżet: <strong>do {_escape(_number(max_price, ' zł'))}</strong></span></div>
<section class="filters" aria-label="Filtry ogłoszeń">
<label>Szukaj<input id="query" type="search" placeholder="Miejscowość, tytuł, opis"></label>
<label>Miasto<select id="city"><option value="">Wszystkie</option>{options}</select></label>
<label>Status<select id="status"><option value="eligible">Pasujące i do sprawdzenia</option><option value="match">Tylko pasujące</option><option value="review">Do sprawdzenia</option><option value="all">Wszystkie zapisane</option></select></label>
<label>Cena do (zł)<input id="price" type="number" min="0" step="1000" value="{_escape(max_price if max_price is not None else '')}" placeholder="Bez limitu"></label>
</section>
<div class="sortbar"><strong id="count" aria-live="polite"></strong><label>Sortowanie <select id="sort"><option value="recent">Ostatnio widziane</option><option value="price">Najtańsze</option><option value="distance">Najbliżej miasta</option></select></label></div>
<main id="offers">{''.join(cards)}</main><p id="empty" class="hidden">Brak ogłoszeń spełniających te filtry. Zmień filtry lub wybierz „Wszystkie zapisane”.</p><button id="more" class="hidden" type="button">Pokaż więcej</button>
<section class="health"><h2>Stan źródeł</h2><p class="meta">Wyniki mogą być niepełne: portal może ograniczyć dostęp lub nie pokazać wszystkich ofert w promieniu 15 km. Status „ok” potwierdza tylko wykonanie danej próby skanu.</p>
<details><summary>Historia skanów ({len(scans)})</summary><div class="table-wrap"><table><thead><tr><th>Czas</th><th>Źródło</th><th>Status</th><th>Odkryte/odczytane</th><th>Błędy</th></tr></thead><tbody>{scan_rows}</tbody></table></div></details></section>
<script>
const cards=[...document.querySelectorAll('.offer')];let limit=20;
const fields={{query:document.getElementById('query'),city:document.getElementById('city'),status:document.getElementById('status'),price:document.getElementById('price'),sort:document.getElementById('sort')}};
function update(){{
  const q=fields.query.value.trim().toLocaleLowerCase('pl');const city=fields.city.value;const status=fields.status.value;const max=fields.price.value===''?Infinity:Number(fields.price.value);
  const found=cards.filter(card=>{{const state=card.dataset.status;return (!q||card.textContent.toLocaleLowerCase('pl').includes(q))&&(!city||card.dataset.city===city)&&(status==='all'||state===status||(status==='eligible'&&state!=='rejected'))&&(card.dataset.price===''?max===Infinity:Number(card.dataset.price)<=max)}});
  const value=fields.sort.value;found.sort((a,b)=>value==='price'?(Number(a.dataset.price||Infinity)-Number(b.dataset.price||Infinity)):value==='distance'?(Number(a.dataset.distance||Infinity)-Number(b.dataset.distance||Infinity)):(Number(b.dataset.seen)-Number(a.dataset.seen)));
  const root=document.getElementById('offers');found.forEach(card=>root.appendChild(card));cards.forEach(card=>card.classList.add('hidden'));found.slice(0,limit).forEach(card=>card.classList.remove('hidden'));
  document.getElementById('count').textContent=`Znaleziono: ${{found.length}}`;
  document.getElementById('empty').classList.toggle('hidden',found.length!==0);
  document.getElementById('more').classList.toggle('hidden',found.length<=limit);
}}
Object.values(fields).forEach(field=>field.addEventListener('input',()=>{{limit=20;update()}}));document.getElementById('more').addEventListener('click',()=>{{limit+=20;update()}});update();
</script></body></html>'''
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix('.tmp')
    tmp.write_text(document, encoding='utf-8')
    tmp.replace(dest)
