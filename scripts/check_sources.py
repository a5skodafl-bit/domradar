"""Read-only smoke check: one search page and one listing per enabled source."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from domradar.engine import load_config,Client
from domradar.parsers import search_links,parse_detail
cfg=load_config(sys.argv[1] if len(sys.argv)>1 else 'config.json')
client=Client(cfg['request_delay_seconds']);rows=[]
for source in cfg['sources']:
    if not source.get('enabled'):continue
    row={'source':source['id']}
    try:
        url=source['search_urls'][0];links,_=search_links(client.get(url,source['id']),url,source['id']);row['links']=len(links)
        if links:
            x=parse_detail(client.get(links[0],source['id']),links[0],source['id']);row.update(price=x.price,currency=x.currency,area=x.area_m2,geo=x.lat is not None and x.lon is not None,url=x.url,property_type=x.property_type,transaction=x.transaction)
        row['status']='sample parsed' if links else 'empty search'
    except Exception as e:row.update(status='error',error=str(e))
    rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
if not rows:raise SystemExit('Brak włączonych portali w konfiguracji.')
Path('source-check.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
