from __future__ import annotations
import argparse
import json
import logging
import os
import time
from pathlib import Path
from .core import Listing
from .engine import load_config,connect,scan,deliver,report,store_listing


def main():
    p=argparse.ArgumentParser(description='DomRadar — monitoring domów na sprzedaż')
    p.add_argument('command',choices=['init','once','watch','report','demo','export','flush'])
    p.add_argument('--config',default='config.json');p.add_argument('--data',default='data');p.add_argument('--send',action='store_true',help='Zezwól na skonfigurowane powiadomienia; domyślnie tylko raport lokalny')
    args=p.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    if args.command=='init':
        dest=Path(args.config)
        if dest.exists():p.error('Plik konfiguracji już istnieje; nie nadpisuję go.')
        example=Path(__file__).parent.parent/'config.example.json'
        dest.write_text(example.read_text(encoding='utf-8'),encoding='utf-8')
        print('Utworzono '+str(dest)+'. Ustaw miasta, budżet i linki do wyszukiwań.');return
    cfg=load_config(args.config);root=Path(args.data);root.mkdir(parents=True,exist_ok=True)
    # Single-process lock avoids concurrent watchers sending duplicate notifications.
    import contextlib
    @contextlib.contextmanager
    def lock():
        file=(root/'monitor.lock').open('a+')
        try:
            if os.name=='nt':
                import msvcrt
                file.seek(0);file.write('0');file.flush();file.seek(0);msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
            yield
        finally:file.close()
    with lock():
        db=connect(root/('demo.sqlite3' if args.command=='demo' else 'domradar.sqlite3'))
        if args.command=='demo':
            demo_cfg=cfg|{'cities':[{'name':'Warszawa','lat':52.2297,'lon':21.0122}], 'price_min':0,'price_max':1000000,'radius_km':40,'area_min':0,'area_max':None}
            samples=[Listing('demo','https://example.org/dom-1','PRZYKŁAD — dom pod Warszawą',850000,'PLN',140,52.28,20.9,'Przykładowa lokalizacja','exact',0,'house','sale','Dom gotowy do zamieszkania. Możliwość zakupu na kredyt — deklaracja sprzedającego.'),Listing('demo','https://example.org/dom-2','PRZYKŁAD — dom z brakującą lokalizacją',700000,'PLN',100,property_type='house',transaction='sale',description='Dom do remontu. Tylko gotówka.')]
            for x in samples:store_listing(db,x,demo_cfg,False)
            report(db,root/'demo.html',config=demo_cfg);print((root/'demo.html').resolve());return
        if args.command=='report':report(db,root/'raport.html',cfg.get('include_analysis',False),cfg);print((root/'raport.html').resolve());return
        if args.command=='export':
            rows=[{'listing':json.loads(x),'assessment':json.loads(y)} for x,y in db.execute('SELECT payload,assessment FROM listings')]
            target=root/'oferty.json';target.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8');print(target.resolve());return
        if args.command=='flush':
            if not args.send:p.error('Wysyłanie wymaga --send')
            deliver(db,cfg,force=True);report(db,root/'raport.html',cfg.get('include_analysis',False),cfg);return
        if not any(s.get('enabled') for s in cfg['sources']):p.error('Włącz co najmniej jeden portal (enabled: true) i ustaw search_urls w config.json.')
        try:
            while True:
                scan(db,cfg)
                if args.send:deliver(db,cfg)
                report(db,root/'raport.html',cfg.get('include_analysis',False),cfg)
                print('Raport: '+str((root/'raport.html').resolve()),flush=True)
                if args.command=='once':break
                deadline=time.monotonic()+cfg['poll_minutes']*60
                # Delivery timer independent of polling interval, so digests are not delayed until next scan.
                while time.monotonic()<deadline:
                    time.sleep(min(15,max(0,deadline-time.monotonic())))
                    if args.send:deliver(db,cfg)
        except KeyboardInterrupt:print('Monitoring zatrzymany; stan zachowany.')
        finally:db.close()

if __name__=='__main__':main()
