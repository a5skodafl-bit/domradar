from __future__ import annotations
import hashlib
import html
import json
import logging
import os
import smtplib
import sqlite3
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit,urljoin,parse_qsl,urlencode,urlunsplit
from .core import Listing, assess, canonical
from .parsers import DOMAINS, allowed, search_links, parse_detail

LOG=logging.getLogger('domradar')


class Client:
    def __init__(self, delay=2, timeout=20): self.delay=delay;self.timeout=timeout;self.last={}
    def get(self,url,source):
        if not allowed(url,source):raise ValueError('URL poza domeną portalu: '+url)
        wait=self.delay-(time.monotonic()-self.last.get(source,0))
        if wait>0:time.sleep(wait)
        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,req,fp,code,msg,headers,newurl):
                if not allowed(newurl,source):raise ValueError('Przekierowanie poza portal: '+newurl)
                return super().redirect_request(req,fp,code,msg,headers,newurl)
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'DomRadar/0.1 (personal real-estate monitor)','Accept-Language':'pl-PL,pl;q=0.9'})
            with urllib.request.build_opener(Redirect()).open(req,timeout=self.timeout) as r:
                if not allowed(r.url,source):raise ValueError('Przekierowanie poza portal')
                raw=r.read(12_000_001)
                if len(raw)>12_000_000:raise ValueError('Strona przekracza limit 12 MB')
                return raw.decode(r.headers.get_content_charset() or 'utf-8',errors='replace')
        finally:self.last[source]=time.monotonic()


def connect(path):
    db=sqlite3.connect(path)
    db.executescript('''
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS listings(key TEXT PRIMARY KEY,source TEXT,url TEXT,payload TEXT,assessment TEXT,first_seen REAL,last_seen REAL);
    CREATE TABLE IF NOT EXISTS history(key TEXT,at REAL,price REAL,currency TEXT);
    CREATE TABLE IF NOT EXISTS scans(at REAL,source TEXT,search_url TEXT,status TEXT,discovered INTEGER,parsed INTEGER,error TEXT);
    CREATE TABLE IF NOT EXISTS baseline(search_id TEXT PRIMARY KEY,at REAL);
    CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY,key TEXT,channel TEXT,body TEXT,created REAL,sent REAL,error TEXT, UNIQUE(key,channel));
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE IF NOT EXISTS observed(key TEXT PRIMARY KEY,eligible INTEGER);
    ''')
    return db


def channels(cfg):
    return [k for k in ['telegram','email'] if cfg.get('notifications',{}).get(k,{}).get('enabled')]


def load_config(path):
    c=json.loads(Path(path).read_text(encoding='utf-8'))
    def numeric(value,name,lo,hi):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not lo<=value<=hi:raise ValueError('Nieprawidłowy parametr: '+name)
    for name,lo,hi in [('price_min',0,1e12),('price_max',1,1e12),('radius_km',0.1,1000),('poll_minutes',5,10080),('digest_minutes',1,10080),('request_delay_seconds',1,60),('pages_per_search',1,100),('max_details_per_search',1,1000)]:numeric(c.get(name),name,lo,hi)
    for name in ['pages_per_search','max_details_per_search']:
        if not isinstance(c[name],int):raise ValueError(name+' musi być liczbą całkowitą')
    if c['price_max']<c['price_min']:raise ValueError('price_max < price_min')
    if not c.get('cities'):raise ValueError('Dodaj co najmniej jedno miasto')
    for city in c['cities']:
        if not city.get('name'):raise ValueError('Miasto musi mieć nazwę')
        numeric(city.get('lat'),'city.lat',-90,90);numeric(city.get('lon'),'city.lon',-180,180)
        numeric(city.get('radius_km',c['radius_km']),'city.radius_km',0.1,1000)
    if c.get('area_min',0)<0 or (c.get('area_max') is not None and c['area_max']<c.get('area_min',0)):raise ValueError('Nieprawidłowy zakres powierzchni')
    for s in c['sources']:
        if s['id'] not in DOMAINS:raise ValueError('Nieznany portal: '+s['id'])
        if s.get('enabled') and not s.get('search_urls'):raise ValueError('Brak search_urls: '+s['id'])
        for u in s.get('search_urls',[]):
            if not allowed(u,s['id']):raise ValueError('Nieprawidłowa domena search_url: '+u)
    return c


def page_url(url,n):
    p=urlsplit(url);q=dict(parse_qsl(p.query));q['page']=str(n)
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(q),'') ) if n>1 else url


def body_for(listing,result,include_analysis=False):
    a=result['analysis'];near=result['nearest'];dist=f"{near['km']:.1f} km od {near['city']}" if near else 'brak lokalizacji'
    quote=lambda d:'; '.join(d['quotes']) or 'brak cytatu'
    base=(f"{listing.title}\n{listing.price:,.0f} {listing.currency} | {listing.area_m2 or '?'} m²\n{dist} (w linii prostej, dokładność: {listing.geo_accuracy})\n{listing.url}\nŹródło: {listing.source}; nowo wykryte, niekoniecznie nowo opublikowane.")
    if include_analysis:
        base+=(f"\nDopasowanie: {result['score']}/100 (reguły, nie wycena)\nStan: {a['condition']['status']}\nOpis: {quote(a['condition'])}\nKredyt: {a['credit']['status']}\nOpis: {quote(a['credit'])}")
    return base



def store_listing(db,listing,cfg,notify):
    listing.url=canonical(listing.url);result=assess(listing,cfg);now=time.time()
    old=db.execute('SELECT payload FROM listings WHERE key=?',(listing.key,)).fetchone()
    old_data=json.loads(old[0]) if old else None
    if not old_data or (old_data.get('price'),old_data.get('currency'))!=(listing.price,listing.currency):
        db.execute('INSERT INTO history VALUES(?,?,?,?)',(listing.key,now,listing.price,listing.currency))
    db.execute('INSERT INTO listings VALUES(?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,assessment=excluded.assessment,last_seen=excluded.last_seen',
               (listing.key,listing.source,listing.url,json.dumps(listing.dict(),ensure_ascii=False),json.dumps(result,ensure_ascii=False),now,now))
    if notify and result['status']=='match':
        for channel in channels(cfg):db.execute('INSERT OR IGNORE INTO outbox(key,channel,body,created) VALUES(?,?,?,?)',(listing.key,channel,body_for(listing,result,cfg.get("include_analysis",False)),now))
    db.commit()
    return result


def scan(db,cfg,client=None):
    client=client or Client(cfg['request_delay_seconds'])
    for source in cfg['sources']:
        if not source.get('enabled'):continue
        sid=source['id']
        for url in source['search_urls']:
            search_id=hashlib.sha256((sid+'|'+canonical(url)).encode()).hexdigest()
            is_initial=not db.execute('SELECT 1 FROM baseline WHERE search_id=?',(search_id,)).fetchone()
            # Discovery establishes the baseline; failed initial details stay ineligible for new-offer alerts.
            # Discovered keys remain retryable even when details fail.
            links=[];seen_pages=set();errors=[];parsed=0;truncated=False
            try:
                for n in range(1,cfg['pages_per_search']+1):
                    text=client.get(page_url(url,n),sid)
                    page_links,total=search_links(text,url,sid)
                    if tuple(page_links) in seen_pages:errors.append('Powtarzające się strony — paginacja mogła zostać zignorowana');break
                    seen_pages.add(tuple(page_links));links+=page_links
                    if not page_links or (total is not None and n>=total):break
                links=list(dict.fromkeys(links))
                if len(links)>cfg['max_details_per_search']:
                    truncated=True;errors.append('Limit szczegółów: '+str(len(links))+' odkrytych ofert. Zawęź wyszukiwanie lub zwiększ limit.')
                for link in links[:cfg['max_details_per_search']]:
                    key=hashlib.sha256(canonical(link).encode()).hexdigest()
                    db.execute('INSERT OR IGNORE INTO observed VALUES(?,?)',(key,int(not is_initial or cfg.get('notify_initial',False))))
                    db.commit()
                    eligible=db.execute('SELECT eligible FROM observed WHERE key=?',(key,)).fetchone()[0]
                    try:
                        detail=client.get(link,sid);listing=parse_detail(detail,link,sid)
                        notify=bool(eligible)
                        result=store_listing(db,listing,cfg,notify);parsed+=1
                        LOG.info('%s %s %s',sid,result['status'],link)
                    except Exception as e:
                        errors.append(link+': '+str(e));LOG.warning('%s: %s',sid,e)
                if not truncated:
                    db.execute('INSERT OR IGNORE INTO baseline VALUES(?,?)',(search_id,time.time()))
            except Exception as e:errors.append(str(e));LOG.warning('%s: %s',sid,e)
            status='error' if errors and not parsed else 'partial' if errors else 'ok'
            db.execute('INSERT INTO scans VALUES(?,?,?,?,?,?,?)',(time.time(),sid,url,status,len(links),parsed,'\n'.join(errors)))
            db.commit()


def send_telegram(text, settings):
    token=os.environ.get(settings.get('token_env','TELEGRAM_BOT_TOKEN'),'')
    chat=os.environ.get(settings.get('chat_id_env','TELEGRAM_CHAT_ID'),'')
    if not token or not chat:raise ValueError('Ustaw TELEGRAM_BOT_TOKEN i TELEGRAM_CHAT_ID')
    # One message per listing fits normal limits; oversized text is split by characters.
    for i in range(0,len(text),3500):
        data=json.dumps({'chat_id':chat,'text':text[i:i+3500],'link_preview_options':{'is_disabled':True}}).encode()
        req=urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',data=data,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=20) as r:response=json.load(r)
        except urllib.error.HTTPError as e:raise RuntimeError('Telegram HTTP '+str(e.code)) from None
        except urllib.error.URLError:raise RuntimeError('Telegram: błąd połączenia') from None
        if not response.get('ok'):raise RuntimeError('Telegram odrzucił wiadomość')


def send_email(text,settings):
    host=os.environ.get('SMTP_HOST','');user=os.environ.get('SMTP_USER','');password=os.environ.get('SMTP_PASSWORD','')
    sender=os.environ.get('SMTP_FROM',user);recipient=os.environ.get('SMTP_TO','')
    if not host or not sender or not recipient:raise ValueError('Ustaw SMTP_HOST, SMTP_FROM i SMTP_TO')
    msg=EmailMessage();msg['Subject']='DomRadar — nowe oferty domów';msg['From']=sender;msg['To']=recipient;msg.set_content(text)
    with smtplib.SMTP_SSL(host,int(os.environ.get('SMTP_PORT','465')),timeout=25) as smtp:
        if user:smtp.login(user,password)
        smtp.send_message(msg)


def deliver(db,cfg,force=False,senders=None):
    senders=senders or {'telegram':send_telegram,'email':send_email}
    last=db.execute("SELECT value FROM meta WHERE key='last_digest'").fetchone()
    if not force and last and time.time()-float(last[0])<cfg['digest_minutes']*60:return
    for channel in channels(cfg):
        rows=db.execute('SELECT id,body FROM outbox WHERE channel=? AND sent IS NULL ORDER BY id',(channel,)).fetchall()
        # Email combines a whole batch; Telegram sends a separate listing message.
        batches=[rows] if channel=='email' and rows else [[r] for r in rows]
        for batch in batches:
            try:
                senders[channel]('\n\n---\n\n'.join(r[1] for r in batch),cfg['notifications'][channel])
                db.executemany('UPDATE outbox SET sent=?,error=NULL WHERE id=?',[(time.time(),r[0]) for r in batch])
            except Exception as e:
                db.executemany('UPDATE outbox SET error=? WHERE id=?',[(str(e),r[0]) for r in batch]);LOG.warning('Powiadomienie %s nie wysłane: %s',channel,e)
                db.commit();break
            db.commit()
    db.execute("INSERT INTO meta VALUES('last_digest',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(time.time()),));db.commit()


def report(db,path,include_analysis=False):
    rows=db.execute('SELECT payload,assessment,first_seen FROM listings ORDER BY first_seen DESC').fetchall()
    scans=db.execute('SELECT at,source,status,discovered,parsed,error FROM scans ORDER BY at DESC LIMIT 100').fetchall()
    e=lambda x:html.escape(str(x if x is not None else 'brak danych'),quote=True)
    cards=[]
    for payload,assessment,at in rows:
        p=json.loads(payload);r=json.loads(assessment);a=r['analysis']
        extra=(f"<p>Dopasowanie {e(r['score'])}/100 · Stan: {e(a['condition']['status'])} · Kredyt: {e(a['credit']['status'])}</p>" if include_analysis else '')
        cards.append(f'''<article data-status="{e(r['status'])}"><span class="tag">{e(r['status'])}</span><h2><a href="{e(p['url'])}" target="_blank" rel="noopener noreferrer">{e(p['title'])}</a></h2><p><b>{e(p['price'])} {e(p['currency'])}</b> · {e(p['area_m2'])} m² · {e(p['source'])}</p><p>{e(p['location'])}</p><p>{e('; '.join(str(x['km'])+' km od '+x['city'] for x in r['distances']))} · dokładność: {e(p['geo_accuracy'])}</p>{extra}<p class="warn">{e('; '.join(r['missing']+r['reasons']))}</p><details><summary>Opis i dowody</summary><p>{e(p['description'])}</p><pre>{e(json.dumps(r['analysis'],ensure_ascii=False,indent=2))}</pre></details></article>''')
    status=''.join(f'<tr><td>{e(time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(at)))}</td><td>{e(sid)}</td><td>{e(status)}</td><td>{found}/{parsed}</td><td>{e(error)}</td></tr>' for at,sid,status,found,parsed,error in scans)
    pending=db.execute('SELECT COUNT(*) FROM outbox WHERE sent IS NULL').fetchone()[0]
    doc='''<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>DomRadar</title><style>body{font:16px system-ui;background:#f1f5f9;color:#142e42;max-width:1100px;margin:32px auto;padding:0 20px}h1{font-size:40px}article{background:white;border-radius:16px;padding:24px;margin:16px 0;box-shadow:0 2px 8px #0001}h2{font-size:21px}a{color:#086b77}.tag{float:right;background:#e1eef2;padding:4px 10px;border-radius:9px}.warn{color:#934b17}button{padding:10px 18px;margin:4px;border:1px solid #086b77;border-radius:8px;background:white;cursor:pointer}table{border-collapse:collapse;font-size:13px;width:100%}td,th{padding:8px;border-bottom:1px solid #ccd5dc;text-align:left;overflow-wrap:anywhere}pre{white-space:pre-wrap}details{margin-top:16px}article[hidden]{display:none}</style><h1>DomRadar</h1><p>Domy na sprzedaż · cena · metraż · odległość w linii prostej · link do źródła.</p>'''
    doc+=f'<p>Oferty: {len(rows)} · oczekujące powiadomienia: {pending}</p><nav><button onclick="filterCards(\'match\')">Pasujące</button><button onclick="filterCards(\'review\')">Do sprawdzenia</button><button onclick="filterCards(\'rejected\')">Odrzucone</button><button onclick="filterCards(\'all\')">Wszystkie</button></nav>'+''.join(cards)
    doc+='<h2>Stan źródeł</h2><p>ok = skan bez wykrytych błędów; partial = wynik niepełny; error = brak poprawnie odczytanych ofert. Nie potwierdza kompletności całego portalu.</p><table><tr><th>Czas lokalny</th><th>Portal</th><th>Status</th><th>Odkryte/odczytane</th><th>Błędy</th></tr>'+status+'</table><script>function filterCards(s){document.querySelectorAll("article").forEach(x=>x.hidden=s!=="all"&&x.dataset.status!==s)}filterCards("match")</script></html>'
    dest=Path(path);dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_suffix('.tmp');tmp.write_text(doc,encoding='utf-8');tmp.replace(dest)
