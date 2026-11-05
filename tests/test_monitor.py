import copy
import json
import tempfile
import unittest
from pathlib import Path
from domradar.core import Listing, assess, distance, analyze_text, canonical
from domradar.parsers import parse_detail, search_links, allowed, unflatten_nuxt
from domradar.engine import connect, store_listing, deliver, scan, report, load_config, reassess_all

ROOT=Path(__file__).resolve().parents[1]

def config():
    c=load_config(ROOT/'config.example.json')
    c.update(price_max=1000000,area_min=0,allow_approximate_geo=False)
    c['notifications']['telegram']['enabled']=True
    return c

def listing(**kw):
    d=dict(source='otodom',url='https://www.otodom.pl/pl/oferta/dom-IDabc',title='Dom na sprzedaż',price=850000,currency='PLN',area_m2=130,lat=52.25,lon=21.02,geo_accuracy='exact',property_type='house',transaction='sale',description='Dom do remontu. Tylko gotówka.')
    return Listing(**(d|kw))

def schema(**kw):
    d={'@type':'RealEstateListing','url':'https://lento.pl/dom,123456.html','name':'Dom na sprzedaż','description':'Dom do remontu. Możliwość zakupu na kredyt.','image':'https://img.example.org/dom.jpg','mainEntity':{'@type':'House','floorSize':{'value':130,'unitCode':'MTK'},'geo':{'latitude':52.25,'longitude':21.02}},'offers':{'price':850000,'priceCurrency':'PLN','businessFunction':'https://schema.org/SellAction'}}
    d.update(kw)
    return '<script type="application/ld+json">'+json.dumps(d)+'</script>'

class CoreTests(unittest.TestCase):
    def test_distance(self):
        self.assertAlmostEqual(distance(52.2297,21.0122,50.0647,19.945),252.0,delta=2)
    def test_city_union(self):
        c=config();c['cities'].append({'name':'Kraków','lat':50.0647,'lon':19.945})
        r=assess(listing(lat=50.06,lon=19.94),c)
        self.assertEqual(r['status'],'match');self.assertEqual(r['nearest']['city'],'Kraków')
    def test_over_budget(self):self.assertEqual(assess(listing(price=1100000),config())['status'],'rejected')
    def test_city_specific_budgets(self):
        c=config();c['price_max']=700000;c['cities'][0]['price_max']=700000
        c['cities'].append({'name':'Kraków','lat':50.0647,'lon':19.945,'radius_km':40,'price_max':500000})
        self.assertEqual(assess(listing(price=650000),c)['status'],'match')
        self.assertEqual(assess(listing(price=650000,lat=50.0647,lon=19.945),c)['status'],'rejected')
    def test_garden_plot_rejected_and_other_risks_require_review(self):
        self.assertEqual(assess(listing(description='Dom na działce ROD.'),config())['status'],'rejected')
        self.assertEqual(assess(listing(description='Dom całoroczny na działce R. O. D.'),config())['status'],'rejected')
        self.assertEqual(assess(listing(description='Dom na działce rekreacyjnej.'),config())['status'],'review')
        self.assertEqual(assess(listing(description='Syndyk sprzedaje udział 1/24 w nieruchomości.'),config())['status'],'review')
        self.assertEqual(assess(listing(description='Sprzedaż gotowych domów mobilnych.'),config())['status'],'review')
    def test_unknown_currency(self):self.assertEqual(assess(listing(currency=''),config())['status'],'review')
    def test_missing_geo(self):self.assertEqual(assess(listing(lat=None),config())['status'],'review')
    def test_unknown_geo_default(self):self.assertEqual(assess(listing(geo_accuracy='unknown'),config())['status'],'review')
    def test_accept_approximate_explicitly(self):
        c=config();c['allow_approximate_geo']=True
        self.assertEqual(assess(listing(geo_accuracy='unknown'),c)['status'],'match')
    def test_approximate_boundary(self):
        c=config();c['allow_approximate_geo']=True;c['radius_km']=1;c['cities'][0]['radius_km']=1
        self.assertEqual(assess(listing(lat=52.235,lon=21.0122,geo_accuracy='approximate',geo_radius_m=1000),c)['status'],'review')
    def test_rent_excluded(self):self.assertEqual(assess(listing(transaction='rent'),config())['status'],'rejected')
    def test_credit_not_inferred(self):self.assertEqual(analyze_text(listing(description='Pełna własność, księga wieczysta.'))['credit']['status'],'brak danych')
    def test_credit_conflict(self):self.assertEqual(analyze_text(listing(description='Możliwość zakupu na kredyt. Tylko gotówka.'))['credit']['status'],'sprzeczne deklaracje')
    def test_tracking(self):self.assertEqual(canonical('https://olx.pl/d/oferta/x?utm_source=xx#top'),'https://olx.pl/d/oferta/x')

class ParserTests(unittest.TestCase):
    def test_json_ld_nested(self):
        x=parse_detail(schema(),'https://lento.pl/dom,123456.html','lento')
        self.assertEqual((x.area_m2,x.price,x.property_type,x.transaction),(130,850000,'house','sale'))
        self.assertEqual(x.lat,52.25)
        self.assertEqual(x.image_url,'https://img.example.org/dom.jpg')
    def test_multiple_images(self):
        x=parse_detail(schema(image=['https://img.example.org/one.jpg',{'large':'https://img.example.org/two.jpg'}]),'https://lento.pl/dom,123456.html','lento')
        self.assertEqual(x.image_urls,['https://img.example.org/one.jpg','https://img.example.org/two.jpg'])
        self.assertEqual(x.image_url,x.image_urls[0])
    def test_related_ad_not_taken(self):
        text=schema()+'<script type="application/ld+json">'+json.dumps({'@type':'Product','url':'https://lento.pl/inny,987654.html','name':'Inny dom','offers':{'price':1},'geo':{'latitude':1,'longitude':1}})+'</script>'
        x=parse_detail(text,'https://lento.pl/dom,123456.html','lento');self.assertEqual(x.price,850000)
    def test_dom_not_flat(self):
        x=parse_detail(schema(url='https://lento.pl/lokal,123456.html',name='Mieszkanie na sprzedaż',mainEntity={'@type':'Apartment'}),'https://lento.pl/lokal,123456.html','lento');self.assertEqual(x.property_type,'flat')
    def test_missing_layout_errors(self):
        with self.assertRaises(ValueError):search_links('<h1>Captcha</h1>','https://www.otodom.pl/','otodom')
    def test_allowed_domain(self):
        self.assertFalse(allowed('https://olx.pl.attacker.example/d/oferta/x','olx'));self.assertFalse(allowed('https://localhost/','olx'));self.assertTrue(allowed('https://www.olx.pl/d/oferta/x','olx'))
    def test_search_no(self):
        links,_=search_links('<a href="https://warszawa.nieruchomosci-online.pl/dom/12345678.html">Dom</a>','https://www.nieruchomosci-online.pl/','nieruchomosci-online');self.assertEqual(len(links),1)
    def test_nuxt(self):self.assertEqual(unflatten_nuxt([['ShallowReactive',1],{'area':2,'location':3},130,{'map':4},{'latitude':5,'longitude':6},52.2,21.0])['location']['map']['latitude'],52.2)
    def test_otodom_geo_scoped(self):
        d={'props':{'pageProps':{'ad':{'title':'Dom na sprzedaż','estate':'HOUSE','transaction':'SELL','totalPrice':{'value':850000,'currency':'PLN'},'areaInSquareMeters':130,'location':{'coordinates':{'latitude':52.25,'longitude':21.02},'mapDetails':{'radius':500}},'description':'Dom'}}},'recommendation':{'latitude':1,'longitude':1}}
        x=parse_detail('<script id="__NEXT_DATA__">'+json.dumps(d)+'</script>','https://www.otodom.pl/pl/oferta/dom-IDabc','otodom')
        self.assertEqual(x.lat,52.25);self.assertEqual(x.geo_radius_m,500)
    def test_otodom_current_shape(self):
        d={'props':{'pageProps':{'ad':{'title':'Dom na sprzedaż','adCategory':{'name':'HOUSE','type':'SELL'},'target':{'Price':299000,'Area':'70'},'characteristics':[{'key':'price','value':'299000','currency':'PLN'},{'key':'m','value':'70'}],'images':[{'medium':'https://img.example.org/otodom.jpg'}],'location':{'coordinates':{'latitude':52.25,'longitude':21.02}},'description':'Dom','createdAt':'2026-11-04'}}}}
        x=parse_detail('<script id="__NEXT_DATA__">'+json.dumps(d)+'</script>','https://www.otodom.pl/pl/oferta/dom-IDnew','otodom')
        self.assertEqual((x.price,x.currency,x.area_m2,x.property_type,x.transaction),(299000,'PLN',70,'house','sale'))
        self.assertEqual(x.image_url,'https://img.example.org/otodom.jpg')
    def test_olx_surface_not_plot(self):
        d={'ad':{'id':'123','map':{'lat':52.25,'lon':21.02,'radius':1},'params':[{'key':'m','normalizedValue':'140'},{'key':'area','normalizedValue':'4900'}]}}
        product={'@type':'Product','sku':'123','name':'Siedlisko 4900 m², dom','url':'https://olx.pl/d/oferta/x','category':'https://www.olx.pl/nieruchomosci/domy/sprzedaz/','offers':{'price':850000,'priceCurrency':'PLN'}}
        text='<script type="application/ld+json">'+json.dumps(product)+'</script><script id="olx-init-config">window.__PRERENDERED_STATE__ = '+json.dumps(json.dumps(d))+';</script>'
        x=parse_detail(text,product['url'],'olx');self.assertEqual(x.area_m2,140);self.assertEqual(x.geo_radius_m,1000);self.assertEqual(x.lat,52.25)

class EngineTests(unittest.TestCase):
    def setUp(self):self.db=connect(':memory:');self.cfg=config()
    def tearDown(self):self.db.close()
    def test_no_duplicate_alert(self):
        store_listing(self.db,listing(),self.cfg,True);store_listing(self.db,listing(),self.cfg,True)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
    def test_history(self):
        store_listing(self.db,listing(),self.cfg,False);store_listing(self.db,listing(price=800000),self.cfg,False)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM history').fetchone()[0],2)
    def test_reassess_historical_rows(self):
        store_listing(self.db,listing(description='Zwykły dom.'),self.cfg,False)
        payload=self.db.execute('SELECT payload FROM listings').fetchone()[0]
        data=json.loads(payload);data['description']='Dom na działce R. O. D.';data.pop('image_urls')
        self.db.execute('UPDATE listings SET payload=?',(json.dumps(data),));self.db.commit()
        reassess_all(self.db,self.cfg)
        assessment=json.loads(self.db.execute('SELECT assessment FROM listings').fetchone()[0])
        self.assertEqual(assessment['status'],'rejected')
    def test_delivery_retry(self):
        store_listing(self.db,listing(),self.cfg,True)
        def failure(*a):raise RuntimeError('offline')
        deliver(self.db,self.cfg,True,{'telegram':failure});self.assertIsNone(self.db.execute('SELECT sent FROM outbox').fetchone()[0])
        messages=[];deliver(self.db,self.cfg,True,{'telegram':lambda text,c:messages.append(text)})
        deliver(self.db,self.cfg,True,{'telegram':lambda text,c:messages.append(text)})
        self.assertEqual(len(messages),1)
    def test_channels_independent(self):
        self.cfg['notifications']['email']['enabled']=True;store_listing(self.db,listing(),self.cfg,True)
        def failure(*a):raise RuntimeError('offline')
        deliver(self.db,self.cfg,True,{'telegram':lambda *a:None,'email':failure})
        rows=dict(self.db.execute('SELECT channel,sent FROM outbox'));self.assertIsNotNone(rows['telegram']);self.assertIsNone(rows['email'])
    def test_baseline_then_new(self):
        cfg=self.cfg;cfg['allow_approximate_geo']=True;cfg['pages_per_search']=1;cfg['sources']=[{'id':'lento','enabled':True,'search_urls':['https://lento.pl/nieruchomosci/domy.html']}]
        class Fake:
            new=False
            def get(self,url,source):
                if 'nieruchomosci' in url:return '<a href="/dom,123456.html">dom</a>'+('<a href="/dom,234567.html">nowy</a>' if self.new else '')
                return schema(url=url)
        client=Fake();scan(self.db,cfg,client);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
        client.new=True;scan(self.db,cfg,client);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
    def test_failed_detail_baseline_not_false_new(self):
        cfg=self.cfg;cfg['allow_approximate_geo']=True;cfg['pages_per_search']=1;cfg['sources']=[{'id':'lento','enabled':True,'search_urls':['https://lento.pl/nieruchomosci/domy.html']}]
        class Fake:
            fail=True
            def get(self,url,source):
                if 'nieruchomosci' in url:return '<a href="/dom,123456.html">dom</a>'
                if self.fail:raise RuntimeError('503')
                return schema(url=url)
        client=Fake();scan(self.db,cfg,client);client.fail=False;scan(self.db,cfg,client)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM listings').fetchone()[0],1);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
    def test_html_escape(self):
        store_listing(self.db,listing(title='<script>alert(1)</script>',image_url='https://img.example.org/one.jpg',image_urls=['https://img.example.org/one.jpg','https://img.example.org/two.jpg']),self.cfg,False)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'report.html';report(self.db,p);text=p.read_text()
            self.assertIn('&lt;script&gt;',text);self.assertNotIn('<script>alert(1)</script>',text)
            self.assertIn('Nie interesuje',text);self.assertIn('Obserwuj',text)
            self.assertIn('domradar-preferences-v1',text);self.assertIn('data-key=',text)
            self.assertIn('const PAGE_SIZE=50',text);self.assertIn('gallery-next',text)
            self.assertIn('openstreetmap.org/export/embed.html',text)

if __name__=='__main__':unittest.main()
