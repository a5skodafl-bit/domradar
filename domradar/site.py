"""Build a searchable, static view of the persistent listings database."""

from __future__ import annotations

import html
import json
import math
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit


def _escape(value):
    return html.escape(str(value if value is not None else 'brak danych'), quote=True)


def _number(value, suffix=''):
    if value is None:
        return 'brak danych'
    return f'{value:,.0f}'.replace(',', ' ') + suffix


def _photos(item):
    values=item.get('image_urls') or [item.get('image_url')]
    if isinstance(values,str):values=[values]
    result=[]
    for value in values:
        if not isinstance(value,str) or not value.strip():continue
        parsed=urlsplit(value.strip())
        if (parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password
                and parsed.port in {None,443} and len(value)<=3000 and value not in result):
            result.append(value)
    return result[:12]


def _map_data(item):
    try:
        lat=float(item.get('lat'));lon=float(item.get('lon'))
    except (TypeError,ValueError):
        return ''
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:return ''
    lat_delta=.018
    lon_delta=.018/max(math.cos(math.radians(lat)),.2)
    bbox=f'{lon-lon_delta:.6f},{lat-lat_delta:.6f},{lon+lon_delta:.6f},{lat+lat_delta:.6f}'
    embed='https://www.openstreetmap.org/export/embed.html?'+urlencode({'bbox':bbox,'layer':'mapnik','marker':f'{lat:.6f},{lon:.6f}'})
    link='https://www.openstreetmap.org/?'+urlencode({'mlat':f'{lat:.6f}','mlon':f'{lon:.6f}','zoom':14})
    accuracy='dokładna' if item.get('geo_accuracy')=='exact' else 'przybliżona'
    return {'embed':embed,'link':link,'accuracy':accuracy}


def render(db, path, include_analysis=False, config=None):
    rows = db.execute('''SELECT key, payload, assessment, first_seen, last_seen
                         FROM listings ORDER BY last_seen DESC''').fetchall()
    scans = db.execute('''SELECT at, source, status, discovered, parsed, error
                          FROM scans ORDER BY at DESC LIMIT 100''').fetchall()
    records = []
    city_names = set()
    source_names = set()
    for key, payload, assessment, first_seen, last_seen in rows:
        item = json.loads(payload)
        result = json.loads(assessment)
        if 'poza promieniem wszystkich miast' in result.get('reasons', []):
            continue
        if any(reason.startswith('syndyk —') for reason in result.get('reasons', [])):
            continue
        near = result.get('nearest') or {}
        city = near.get('city') or ''
        if city:
            city_names.add(city)
        if item.get('source'):
            source_names.add(item['source'])
        status = result['status']
        label = {'match': 'Pasuje', 'review': 'Do sprawdzenia', 'rejected': 'Poza kryteriami'}.get(status, status)
        price = item.get('price')
        distance = f"{near['km']} km od {city}" if near else 'Brak współrzędnych'
        note = '; '.join(result.get('missing', []) + result.get('reasons', []))
        analysis = result.get('analysis') or {}
        extra = ''
        if include_analysis:
            extra = (f"Stan: {(analysis.get('condition') or {}).get('status') or 'brak danych'} · "
                     f"Kredyt: {(analysis.get('credit') or {}).get('status') or 'brak danych'}")
        records.append({
            'key':key,'status':status,'label':label,'city':city,'source':item.get('source') or '',
            'price':price,'distance_km':near.get('km'),'distance':distance,'seen':last_seen,
            'title':item.get('title') or 'Ogłoszenie bez tytułu','url':item.get('url') or '',
            'location':item.get('location') or 'Brak lokalizacji','area_m2':item.get('area_m2'),
            'geo_accuracy':item.get('geo_accuracy') or 'unknown','note':note,'analysis':extra,
            'description':(item.get('description') or 'Brak opisu')[:350],
            'first_seen':time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime(first_seen)),
            'last_seen':time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime(last_seen)),
            'photos':_photos(item),'map':_map_data(item)
        })

    city_budgets={city['name']:city.get('price_max',config.get('price_max')) for city in (config or {}).get('cities',[])}
    options = ''.join(f'<option value="{_escape(city)}" data-price-max="{_escape(city_budgets.get(city, ""))}">{_escape(city)}</option>' for city in sorted(city_names))
    source_options = ''.join(f'<option value="{_escape(source)}">{_escape(source)}</option>' for source in sorted(source_names))
    max_price = config.get('price_max') if config else None
    budget_summary=', '.join(f'{_escape(name)}: do {_escape(_number(value," zł"))}' for name,value in city_budgets.items())
    dest = Path(path)
    api_relative = Path('api') / f'{dest.stem}-listings.json'
    api_url_json = json.dumps(api_relative.as_posix(),ensure_ascii=False)
    last_scan = max((row[0] for row in scans), default=None)
    freshness = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(last_scan)) if last_scan else 'jeszcze nie wykonano'
    scan_rows = ''.join(
        f'<tr><td>{_escape(time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(at)))}</td>'
        f'<td>{_escape(source)}</td><td>{_escape(status)}</td><td>{discovered}/{parsed}</td>'
        f'<td>{_escape(error)}</td></tr>'
        for at, source, status, discovered, parsed, error in scans
    )
    document = f'''<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,">
<title>DomRadar — baza ogłoszeń domów</title>
<style>
:root{{font-family:system-ui,sans-serif;color:#163047;background:#f2f6f8}}*{{box-sizing:border-box}}
body{{max-width:1120px;margin:0 auto;padding:28px 20px 70px}}h1{{font-size:clamp(2rem,5vw,3.4rem);margin:.2em 0}}
h2{{font-size:1.2rem;margin:12px 0}}a{{color:#087083}}a:hover{{text-decoration-thickness:2px}}
.intro,.meta,.source{{color:#597184}}.intro{{max-width:750px;line-height:1.55}}
.summary{{display:flex;gap:14px;flex-wrap:wrap;margin:22px 0}}.summary span{{background:#fff;padding:12px 16px;border-radius:12px;box-shadow:0 2px 8px #1330470d}}
.filters{{display:grid;grid-template-columns:2fr repeat(5,1fr);gap:12px;background:#fff;padding:18px;border-radius:18px;box-shadow:0 2px 12px #13304712}}
label{{display:grid;gap:5px;font-weight:600;font-size:.88rem}}input,select{{font:inherit;width:100%;padding:11px;border:1px solid #b8cbd3;border-radius:9px;background:#fff;color:#163047}}
.sortbar{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:24px 0 12px;flex-wrap:wrap}}.sortbar label{{display:flex;align-items:center;gap:8px}}
.sortbar select{{width:auto}}.offer{{display:grid;grid-template-columns:minmax(250px,35%) 1fr;background:#fff;margin:12px 0;border-radius:16px;box-shadow:0 2px 12px #13304712;overflow:hidden}}.offer:not(.has-media){{grid-template-columns:1fr}}.offer-body{{padding:20px 24px;min-width:0}}
.media{{display:grid;align-content:start;background:#dce6ea;border-right:1px solid #d7e0e5}}.gallery{{position:relative;min-width:0}}.photo{{display:block;min-height:250px;background:#dce6ea}}.photo img{{width:100%;height:100%;min-height:250px;max-height:340px;object-fit:cover;display:block}}
.gallery-prev,.gallery-next{{position:absolute;top:50%;translate:0 -50%;width:44px;height:54px;padding:0;border:0;border-radius:0;background:#102d3dcc;color:#fff;font-size:2rem;line-height:1}}.gallery-prev{{left:0;border-radius:0 9px 9px 0}}.gallery-next{{right:0;border-radius:9px 0 0 9px}}.gallery-count{{position:absolute;right:10px;bottom:10px;padding:4px 8px;border-radius:20px;background:#102d3dcc;color:#fff;font-size:.8rem;font-weight:700}}
.map{{display:grid;background:#fff}}.map-frame{{position:relative;height:190px;border-top:1px solid #d7e0e5;background:#e9f0f2}}.map iframe{{position:relative;z-index:1;width:100%;height:190px;border:0}}.map-placeholder{{position:absolute;inset:0;display:grid;place-items:center;color:#597184;font-weight:650}}.map.is-loaded .map-placeholder{{display:none}}.map>a{{padding:8px 12px;font-size:.78rem;text-align:center}}
.offer-top{{display:flex;justify-content:space-between;align-items:center;gap:12px}}.badge{{padding:4px 10px;border-radius:100px;font-size:.85rem;font-weight:700;background:#dbe9ec}}
.badge.match{{background:#d9f4e6;color:#17613b}}.badge.review{{background:#fff0c8;color:#795500}}.badge.rejected{{background:#e6e9ec;color:#56616b}}
.price{{font-weight:750;font-size:1.3rem;margin:8px 0}}.note{{color:#8a4b19}}.description{{white-space:pre-wrap;line-height:1.55}}
details{{border-top:1px solid #e4eaed;padding-top:12px}}summary{{cursor:pointer;font-weight:600}}button{{padding:11px 18px;border:1px solid #087083;color:#087083;background:white;border-radius:9px;cursor:pointer}}button:disabled{{opacity:.45;cursor:not-allowed}}
.actions{{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}}.actions button{{min-height:50px;padding:13px 22px;font-size:1rem;font-weight:750}}.actions button[aria-pressed="true"]{{background:#087083;color:#fff}}.actions .ignore[aria-pressed="true"]{{background:#6a4c4c;border-color:#6a4c4c}}
#pager{{display:flex;justify-content:center;align-items:center;gap:14px;margin:26px 0;flex-wrap:wrap}}#pager button{{min-width:140px}}#page-info{{font-weight:700}}#empty,#loading{{background:#fff;padding:28px;border-radius:16px}}.hidden{{display:none!important}}
table{{border-collapse:collapse;width:100%;font-size:.82rem}}td,th{{border-bottom:1px solid #d7e0e5;text-align:left;padding:8px;vertical-align:top;overflow-wrap:anywhere}}
.table-wrap{{overflow-x:auto}}.health{{margin-top:55px}}.health details{{margin-top:16px}}@media(max-width:760px){{.filters{{grid-template-columns:1fr 1fr}}.offer{{grid-template-columns:1fr}}.media{{border-right:0;border-bottom:1px solid #d7e0e5}}.photo,.photo img{{min-height:210px;max-height:300px}}}}@media(max-width:510px){{.filters{{grid-template-columns:1fr}}.actions button{{flex:1 1 100%}}}}
</style></head><body>
<header><h1>DomRadar</h1><p class="intro">Baza domów na sprzedaż w pobliżu wybranych miast Polski. Przeszukuj zapisane ogłoszenia, filtruj wyniki i otwieraj oferty u źródła.</p></header>
<div class="summary"><span><strong>{len(records)}</strong> ogłoszeń w bazie</span><span>Ostatni skan: <strong>{_escape(freshness)}</strong></span><span>Budżety: <strong>{budget_summary or 'do '+_escape(_number(max_price, ' zł'))}</strong></span></div>
<section class="filters" aria-label="Filtry ogłoszeń">
<label>Szukaj<input id="query" type="search" placeholder="Miejscowość, tytuł, opis"></label>
<label>Miasto<select id="city"><option value="">Wszystkie</option>{options}</select></label>
<label>Portal<select id="source"><option value="">Wszystkie</option>{source_options}</select></label>
<label>Status<select id="status"><option value="eligible">Pasujące i do sprawdzenia</option><option value="match">Tylko pasujące</option><option value="review">Do sprawdzenia</option><option value="all">Wszystkie zapisane</option></select></label>
<label>Moja lista<select id="preference"><option value="active">Bez „Nie interesuje”</option><option value="watched">Obserwowane</option><option value="ignored">Nie interesuje</option></select></label>
<label>Cena do (zł)<input id="price" type="number" min="0" step="1000" value="{_escape(max_price if max_price is not None else '')}" placeholder="Bez limitu"></label>
</section>
<div class="sortbar"><strong id="count" aria-live="polite"></strong><label>Sortowanie <select id="sort"><option value="recent">Ostatnio widziane</option><option value="price">Najtańsze</option><option value="distance">Najbliżej miasta</option></select></label></div>
<p id="loading">Ładowanie ofert…</p><main id="offers"></main><p id="empty" class="hidden">Brak ogłoszeń spełniających te filtry. Zmień filtry lub wybierz „Wszystkie zapisane”.</p>
<nav id="pager" class="hidden" aria-label="Stronicowanie ofert"><button id="previous" type="button">← Poprzednia</button><span id="page-info" aria-live="polite"></span><button id="next" type="button">Następna →</button></nav>
<section class="health"><h2>Stan źródeł</h2><p class="meta">Wyniki mogą być niepełne: portal może ograniczyć dostęp lub nie pokazać wszystkich ofert w skonfigurowanym promieniu. Status „ok” potwierdza tylko wykonanie danej próby skanu.</p>
<details><summary>Historia skanów ({len(scans)})</summary><div class="table-wrap"><table><thead><tr><th>Czas</th><th>Źródło</th><th>Status</th><th>Odkryte/odczytane</th><th>Błędy</th></tr></thead><tbody>{scan_rows}</tbody></table></div></details></section>
<script>
const PAGE_SIZE=50;const API_URL={api_url_json};let items=[];let filtered=[];let page=1;
const storageKey='domradar-preferences-v1';let preferences={{}};
try{{preferences=JSON.parse(localStorage.getItem(storageKey)||'{{}}')||{{}}}}catch(_error){{preferences={{}}}}
const fields={{query:document.getElementById('query'),city:document.getElementById('city'),source:document.getElementById('source'),status:document.getElementById('status'),preference:document.getElementById('preference'),price:document.getElementById('price'),sort:document.getElementById('sort')}};
const root=document.getElementById('offers');const pager=document.getElementById('pager');
const htmlEscapes={{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}};
function escapeHtml(value){{return String(value??'').replace(/[&<>"']/g,char=>htmlEscapes[char])}}
function safeUrl(value){{try{{const url=new URL(String(value),location.href);return url.protocol==='https:'&&!url.username&&!url.password?url.href:''}}catch(_error){{return ''}}}}
function number(value,suffix=''){{return value===null||value===undefined?'brak danych':new Intl.NumberFormat('pl-PL',{{maximumFractionDigits:0}}).format(value)+suffix}}
function preference(item){{return preferences[item.key]||''}}
function galleryMarkup(item){{const photos=(Array.isArray(item.photos)?item.photos:[]).map(safeUrl).filter(Boolean);if(!photos.length)return '';const controls=photos.length>1?`<button class="gallery-prev" data-action="previous-photo" type="button" aria-label="Poprzednie zdjęcie">‹</button><span class="gallery-count" aria-live="polite">1 / ${{photos.length}}</span><button class="gallery-next" data-action="next-photo" type="button" aria-label="Następne zdjęcie">›</button>`:'';return `<div class="gallery" data-index="0"><a class="photo" href="${{escapeHtml(safeUrl(item.url))}}" target="_blank" rel="noopener noreferrer"><img src="${{escapeHtml(photos[0])}}" alt="Zdjęcie 1 z ${{photos.length}}: ${{escapeHtml(item.title)}}" loading="lazy" referrerpolicy="no-referrer"></a>${{controls}}</div>`}}
function mapMarkup(item){{const data=item.map||{{}};const embed=safeUrl(data.embed);const link=safeUrl(data.link);if(!embed||!link)return '';return `<div class="map"><div class="map-frame"><iframe data-src="${{escapeHtml(embed)}}" title="Mapa lokalizacji ogłoszenia (${{escapeHtml(data.accuracy)}})" loading="lazy" referrerpolicy="no-referrer"></iframe><span class="map-placeholder">Mapa lokalizacji</span></div><a href="${{escapeHtml(link)}}" target="_blank" rel="noopener noreferrer">Otwórz większą mapę · lokalizacja ${{escapeHtml(data.accuracy)}}</a></div>`}}
function cardMarkup(item){{const gallery=galleryMarkup(item);const map=mapMarkup(item);const state=preference(item);const media=gallery||map?`<div class="media">${{gallery}}${{map}}</div>`:'';return `<article class="offer${{media?' has-media':''}}" data-key="${{escapeHtml(item.key)}}">${{media}}<div class="offer-body"><div class="offer-top"><span class="badge ${{escapeHtml(item.status)}}">${{escapeHtml(item.label)}}</span><span class="source">${{escapeHtml(item.source)}}</span></div><h2><a href="${{escapeHtml(safeUrl(item.url))}}" target="_blank" rel="noopener noreferrer">${{escapeHtml(item.title)}}</a></h2><p class="price">${{escapeHtml(number(item.price,' zł'))}}</p><p>${{escapeHtml(item.location)}} · ${{escapeHtml(item.distance)}} · ${{escapeHtml(number(item.area_m2,' m²'))}}</p><p class="meta">Widziane: ${{escapeHtml(item.last_seen)}} · Lokalizacja: ${{escapeHtml(item.geo_accuracy)}}</p>${{item.note?`<p class="note">${{escapeHtml(item.note)}}</p>`:''}}${{item.analysis?`<p>${{escapeHtml(item.analysis)}}</p>`:''}}<div class="actions"><button class="watch" data-action="watch" type="button" aria-pressed="${{state==='watched'}}">${{state==='watched'?'Obserwowane ✓':'Obserwuj'}}</button><button class="ignore" data-action="ignore" type="button" aria-pressed="${{state==='ignored'}}">${{state==='ignored'?'Cofnij „Nie interesuje”':'Nie interesuje'}}</button></div><details><summary>Fragment opisu</summary><p class="description">${{escapeHtml(item.description)}}</p><p class="meta">Pierwszy raz w bazie: ${{escapeHtml(item.first_seen)}}</p></details></div></article>`}}
const mapObserver='IntersectionObserver' in window?new IntersectionObserver(entries=>entries.forEach(entry=>{{const frame=entry.target;const map=frame.closest('.map');if(entry.isIntersecting){{if(!frame.hasAttribute('src'))frame.src=frame.dataset.src;map.classList.add('is-loaded')}}else{{frame.removeAttribute('src');map.classList.remove('is-loaded')}}}}),{{rootMargin:'400px 0px'}}):null;
function observeMaps(){{if(mapObserver){{mapObserver.disconnect();root.querySelectorAll('.map iframe[data-src]').forEach(frame=>mapObserver.observe(frame))}}else root.querySelectorAll('.map iframe[data-src]').forEach(frame=>frame.src=frame.dataset.src)}}
function renderPage(scrollY=null){{const pages=Math.max(1,Math.ceil(filtered.length/PAGE_SIZE));page=Math.min(Math.max(1,page),pages);const start=(page-1)*PAGE_SIZE;root.innerHTML=filtered.slice(start,start+PAGE_SIZE).map(cardMarkup).join('');observeMaps();document.getElementById('empty').classList.toggle('hidden',filtered.length!==0);pager.classList.toggle('hidden',filtered.length<=PAGE_SIZE);document.getElementById('previous').disabled=page<=1;document.getElementById('next').disabled=page>=pages;document.getElementById('page-info').textContent=`Strona ${{page}} z ${{pages}}`;document.getElementById('count').textContent=`Znaleziono: ${{filtered.length}} · pokazano ${{filtered.length?start+1:0}}–${{Math.min(start+PAGE_SIZE,filtered.length)}}`;if(scrollY!==null)requestAnimationFrame(()=>window.scrollTo(0,scrollY))}}
function update(resetPage=true,scrollY=null){{const q=fields.query.value.trim().toLocaleLowerCase('pl');const city=fields.city.value;const source=fields.source.value;const status=fields.status.value;const list=fields.preference.value;const max=fields.price.value===''?Infinity:Number(fields.price.value);filtered=items.filter(item=>{{const personal=preference(item);return (!q||item.searchText.includes(q))&&(!city||item.city===city)&&(!source||item.source===source)&&(status==='all'||item.status===status||(status==='eligible'&&item.status!=='rejected'))&&(list==='active'?personal!=='ignored':personal===list)&&(item.price===null?max===Infinity:Number(item.price)<=max)}});const value=fields.sort.value;filtered.sort((a,b)=>value==='price'?((a.price??Infinity)-(b.price??Infinity)):value==='distance'?((a.distance_km??Infinity)-(b.distance_km??Infinity)):(b.seen-a.seen));if(resetPage)page=1;renderPage(scrollY)}}
function save(item,state){{const scrollY=window.scrollY;if(state)preferences[item.key]=state;else delete preferences[item.key];try{{localStorage.setItem(storageKey,JSON.stringify(preferences))}}catch(_error){{}}update(false,scrollY)}}
root.addEventListener('click',event=>{{const button=event.target.closest('button[data-action]');if(!button)return;const article=button.closest('.offer');const item=items.find(candidate=>candidate.key===article?.dataset.key);if(!item)return;const action=button.dataset.action;if(action==='watch'||action==='ignore'){{const target=action==='watch'?'watched':'ignored';save(item,preference(item)===target?'':target);return}}const photos=item.photos.map(safeUrl).filter(Boolean);const gallery=button.closest('.gallery');let index=Number(gallery.dataset.index||0);index=(index+(action==='next-photo'?1:-1)+photos.length)%photos.length;gallery.dataset.index=String(index);const image=gallery.querySelector('img');image.src=photos[index];image.alt=`Zdjęcie ${{index+1}} z ${{photos.length}}: ${{item.title}}`;gallery.querySelector('.gallery-count').textContent=`${{index+1}} / ${{photos.length}}`}});
root.addEventListener('error',event=>{{if(!event.target.matches('.gallery img'))return;const gallery=event.target.closest('.gallery');const media=gallery.parentElement;const offer=event.target.closest('.offer');gallery.remove();if(!media.children.length)offer.classList.remove('has-media')}},true);
Object.values(fields).forEach(field=>field.addEventListener('input',()=>{{if(field===fields.city){{const option=field.selectedOptions[0];fields.price.value=option?.dataset.priceMax||'{_escape(max_price if max_price is not None else '')}'}}update(true)}}));
document.getElementById('previous').addEventListener('click',()=>{{page--;renderPage();document.querySelector('.sortbar').scrollIntoView({{behavior:'smooth'}})}});document.getElementById('next').addEventListener('click',()=>{{page++;renderPage();document.querySelector('.sortbar').scrollIntoView({{behavior:'smooth'}})}});
fetch(API_URL,{{cache:'no-cache'}}).then(response=>{{if(!response.ok)throw new Error(`HTTP ${{response.status}}`);return response.json()}}).then(data=>{{items=Array.isArray(data.items)?data.items:[];items.forEach(item=>item.searchText=[item.title,item.location,item.description,item.source].join(' ').toLocaleLowerCase('pl'));document.getElementById('loading').classList.add('hidden');update(true)}}).catch(error=>{{document.getElementById('loading').textContent='Nie udało się załadować ofert: '+error.message}});
</script></body></html>'''
    dest.parent.mkdir(parents=True, exist_ok=True)
    api_dest=dest.parent/api_relative
    api_dest.parent.mkdir(parents=True,exist_ok=True)
    api_tmp=api_dest.with_suffix('.tmp')
    api_tmp.write_text(json.dumps({'version':1,'count':len(records),'items':records},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    api_tmp.replace(api_dest)
    tmp = dest.with_suffix('.tmp')
    tmp.write_text(document, encoding='utf-8')
    tmp.replace(dest)
