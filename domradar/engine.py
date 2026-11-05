from __future__ import annotations
import hashlib
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
            if source == 'olx':
                # OLX rejects the standard urllib TLS fingerprint with HTTP 403.
                # Scrapling's HTTP fetcher impersonates Chrome without launching a browser.
                try:
                    from scrapling.fetchers import Fetcher
                except ImportError as exc:
                    raise RuntimeError('OLX wymaga zależności: pip install "scrapling[fetchers]"') from exc
                response=Fetcher.get(url,impersonate='chrome',stealthy_headers=True,timeout=self.timeout)
                final_url=str(response.url)
                if not allowed(final_url,source):raise ValueError('Przekierowanie poza portal')
                if int(response.status)>=400:raise RuntimeError('OLX HTTP '+str(response.status))
                raw=response.body
                if len(raw)>12_000_000:raise ValueError('Strona przekracza limit 12 MB')
                return raw.decode(getattr(response,'encoding',None) or 'utf-8',errors='replace')
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
        numeric(city.get('price_max',c['price_max']),'city.price_max',1,1e12)
        if city.get('price_max',c['price_max'])<c['price_min']:raise ValueError('city.price_max < price_min')
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


def outside_all_cities(result):
    return 'poza promieniem wszystkich miast' in result.get('reasons', [])


def delete_listing(db,key):
    db.execute('DELETE FROM history WHERE key=?',(key,))
    db.execute('DELETE FROM outbox WHERE key=?',(key,))
    db.execute('DELETE FROM listings WHERE key=?',(key,))



def store_listing(db,listing,cfg,notify):
    listing.url=canonical(listing.url);result=assess(listing,cfg);now=time.time()
    if outside_all_cities(result):
        delete_listing(db,listing.key);db.commit();return result
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


def reassess_all(db,cfg):
    """Apply current filters to historical rows without requiring a fresh portal hit."""
    updates=[];deletes=[]
    for key,payload in db.execute('SELECT key,payload FROM listings'):
        listing=Listing(**json.loads(payload))
        result=assess(listing,cfg)
        if outside_all_cities(result):deletes.append(key)
        else:updates.append((json.dumps(result,ensure_ascii=False),key))
    db.executemany('UPDATE listings SET assessment=? WHERE key=?',updates)
    for key in deletes:delete_listing(db,key)
    db.commit()
    return len(updates)+len(deletes)


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


def report(db, path, include_analysis=False, config=None):
    from .site import render
    return render(db, path, include_analysis, config)
