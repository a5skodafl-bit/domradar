"""Independent implementation; no third-party source code is included."""
from __future__ import annotations
import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from .core import Listing, number, canonical, fold

DOMAINS = {'otodom':'otodom.pl','olx':'olx.pl','morizon':'morizon.pl','gratka':'gratka.pl','nieruchomosci-online':'nieruchomosci-online.pl','domiporta':'domiporta.pl','adresowo':'adresowo.pl','sprzedajemy':'sprzedajemy.pl','lento':'lento.pl','szybko':'szybko.pl'}
PATTERNS = {
 'otodom':r'/pl/oferta/', 'olx':r'/d/oferta/', 'morizon':r'/oferta/',
 'gratka':r'/nieruchomosci/.+/ob/\d+', 'nieruchomosci-online':r'/[^/]*\d{6,}\.html',
 'domiporta':r'/nieruchomosci/.+\d{6}', 'adresowo':r'/o/',
 'sprzedajemy':r'-nr\d+', 'lento':r',\d+\.html', 'szybko':r'/o/[^/]+/[^/]+/.+|/oferta/'
}


def allowed(url, source):
    p = urlsplit(url); host = (p.hostname or '').lower(); root = DOMAINS[source]
    return p.scheme == 'https' and (host == root or host.endswith('.'+root)) and not p.username and not p.password and p.port in {None,443}


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.scripts=[]; self.links=[]; self.meta={}; self.props={}; self.h1=[]; self.description=[]
        self._script=None; self._buf=[]; self._stack=[]; self._h1=0; self._desc=0
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=='script': self._script=a; self._buf=[]
        if tag=='a' and a.get('href'): self.links.append(a['href'])
        if tag=='meta':
            if a.get('property') or a.get('name'): self.meta[a.get('property') or a.get('name')]=a.get('content','')
            if a.get('itemprop'): self.props[a['itemprop']]=a.get('content','')
        if a.get('itemprop') and a.get('content'): self.props[a['itemprop']]=a['content']
        desc = a.get('itemprop')=='description' or a.get('data-cy')=='ad_description' or a.get('id') in {'description','offer-description','descriptionContainer'}
        if tag not in {'meta','link','img','input','br','hr','source','wbr','area','base','embed','param','track','col'}:
            self._stack.append((tag,desc))
            if desc:self._desc+=1
        if tag=='h1': self._h1+=1
    def handle_endtag(self, tag):
        if tag=='script' and self._script is not None:
            self.scripts.append((self._script,''.join(self._buf))); self._script=None
        if tag=='h1':self._h1=max(0,self._h1-1)
        for i in range(len(self._stack)-1,-1,-1):
            if self._stack[i][0]==tag:
                self._desc=max(0,self._desc-sum(d for _,d in self._stack[i:]));del self._stack[i:];break
    def handle_data(self, data):
        if self._script is not None: self._buf.append(data)
        elif self._h1:self.h1.append(data.strip())
        elif self._desc:self.description.append(data.strip())
    def json_scripts(self):
        for a,s in self.scripts:
            if a.get('id')=='__NEXT_DATA__' or a.get('type')=='application/ld+json':
                try:yield a,json.loads(s,strict=False)
                except (ValueError,TypeError):continue


def walk(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values():yield from walk(v)
    elif isinstance(obj,list):
        for v in obj:yield from walk(v)


def clean(text):
    return re.sub(r'\s+',' ',unescape(re.sub(r'<[^>]*>',' ',str(text or '')))).strip()


def types(obj):
    v=obj.get('@type',[]);return [x.rsplit('/',1)[-1] for x in ([v] if isinstance(v,str) else v)]


def image_url(value, base):
    """Return one safe public image URL from JSON-LD or page metadata."""
    if isinstance(value,list):
        for item in value:
            result=image_url(item,base)
            if result:return result
        return ''
    if isinstance(value,dict):
        value=(value.get('contentUrl') or value.get('url') or value.get('@id') or
               value.get('large') or value.get('medium') or value.get('small') or value.get('thumbnail') or '')
    if not isinstance(value,str) or not value.strip():return ''
    result=urljoin(base,value.strip());parsed=urlsplit(result)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in {None,443}:return ''
    return result if len(result)<=3000 else ''


def classify(title, url, schema_types=()):
    f=fold(title+' '+url)
    house = bool(set(schema_types)&{'House','SingleFamilyResidence'}) or bool(re.search(r'\bdom\b|\bdomu\b|domy|sprzedaz-dom|sprzedam-dom|house',f))
    flat = bool(re.search(r'\bmieszkanie\b|mieszkania|sprzedaz-mieszkanie|\bkawalerka\b',f))
    rent=bool(re.search(r'wynajem|wynajm|do-wynajecia',f))
    sale=bool(re.search(r'sprzedaz|sprzedam|na-sprzedaz|na sprzedaz|for-sale',f))
    return ('house' if house and not flat else 'flat' if flat and not house else 'unknown', 'rent' if rent else 'sale' if sale else 'unknown')


def search_links(text, url, source):
    page=Page(text);links=[];total_pages=None;explicit_empty=False
    if source=='otodom':
        for a,data in page.json_scripts():
            if a.get('id')!='__NEXT_DATA__':continue
            for obj in walk(data):
                if isinstance(obj.get('searchAds'),dict):
                    search=obj['searchAds']; items=search.get('items')
                    if isinstance(items,list):
                        explicit_empty = len(items)==0
                        total_pages=(search.get('pagination') or {}).get('totalPages')
                        for item in items:
                            for ad in [item]+(item.get('relatedAds') or []):
                                if ad.get('slug'):links.append(urljoin(url,'/pl/oferta/'+ad['slug']))
    for href in page.links:
        u=canonical(urljoin(url,href))
        if allowed(u,source) and re.search(PATTERNS[source],urlsplit(u).path):links.append(u)
    links=list(dict.fromkeys(links))
    if not links and not explicit_empty:
        raise ValueError('Brak rozpoznanych ofert: blokada, zmiana HTML lub nieobsługiwany pusty wynik. Nie uznaję tego za poprawny skan.')
    return links,total_pages


def parse_otodom(page, url, source):
    for a,data in page.json_scripts():
        if a.get('id')!='__NEXT_DATA__':continue
        ad=((data.get('props') or {}).get('pageProps') or {}).get('ad')
        if not isinstance(ad,dict):continue
        target=ad.get('target') or {}; loc=ad.get('location') or {}
        characteristics={str(x.get('key')):x for x in ad.get('characteristics') or [] if isinstance(x,dict)}
        def t(k):
            v=target.get(k);return v[0] if isinstance(v,list) and v else v
        price=ad.get('totalPrice') or {};category=ad.get('adCategory') or {}
        estate=ad.get('estate') or category.get('name') or t('ProperType') or t('Type') or t('Estate')
        transaction=ad.get('transaction') or category.get('type') or t('OfferType') or t('Offer_type') or t('Transaction')
        kind,tx=classify(ad.get('title',''),url)
        if str(estate).upper() in {'HOUSE','HOUSES','DOM'}:kind='house'
        elif str(estate).upper() in {'FLAT','APARTMENT','MIESZKANIE'}:kind='flat'
        if str(transaction).upper() in {'SELL','SALE','SPRZEDAZ','SPRZEDAŻ'}:tx='sale'
        elif str(transaction).upper() in {'RENT','WYNAJEM'}:tx='rent'
        # Only location subtree, never map centres from unrelated ads/recommendations.
        geo=next((x for x in walk(loc) if number(x.get('latitude')) is not None and number(x.get('longitude')) is not None),{})
        radius=number(geo.get('radius') if 'radius' in geo else (loc.get('mapDetails') or {}).get('radius',loc.get('radius')))
        address=loc.get('address') or {}
        names=[v.get('name','') if isinstance(v,dict) else str(v or '') for v in address.values()]
        photo=image_url(ad.get('images') or ad.get('listingImages') or ad.get('image') or ad.get('photos'),url)
        price_attr=characteristics.get('price') or {}
        listing=Listing(source,url,clean(ad.get('title')),number(price.get('value') if isinstance(price,dict) else price) or number(t('Price')) or number(price_attr.get('value')),str(price.get('currency','') if isinstance(price,dict) else '') or str(price_attr.get('currency') or ''),number(ad.get('areaInSquareMeters')) or number(t('Area')) or number((characteristics.get('m') or {}).get('value')),number(geo.get('latitude')),number(geo.get('longitude')),', '.join(x for x in names if x),'approximate' if radius else 'unknown',radius,kind,tx,clean(ad.get('description')),str(ad.get('dateCreated') or ad.get('createdAt') or ''),str(t('Build_condition') or t('Construction_status') or ''),'Otodom __NEXT_DATA__.props.pageProps.ad',photo)
        # Currency must be explicitly stated, not inferred from country/domain.
        if not listing.currency:listing.currency=str(t('Currency') or '')
        return listing
    return None


def parse_detail(text, url, source):
    page=Page(text)
    if source=='otodom':
        result=parse_otodom(page,url,source)
        if result:return result
    objects=[]
    for a,data in page.json_scripts():
        if a.get('type')=='application/ld+json':objects.extend(walk(data))
    # Do not read prices/geo from related products or breadcrumb items.
    candidates=[o for o in objects if set(types(o)) & {'House','SingleFamilyResidence','Residence','Apartment','RealEstateListing','Product','Offer','Accommodation'}]
    primary=[o for o in candidates if canonical(urljoin(url,str(o.get('url') or o.get('@id') or url)))==canonical(url)]
    primary=primary or [o for o in candidates if not o.get('url') and not o.get('@id')]
    primary.sort(key=lambda o:0 if set(types(o)) & {'House','SingleFamilyResidence','Residence','Apartment','RealEstateListing','Product'} else 1)
    obj=primary[0] if primary else {}
    item=obj.get('itemOffered') or obj.get('mainEntity') or obj.get('about') or obj
    if isinstance(item,list):item=item[0] if item else obj
    if not isinstance(item,dict):item=obj
    offers=obj.get('offers') or item.get('offers') or (obj if 'Offer' in types(obj) else {})
    if isinstance(offers,list):offers=offers[0] if offers else {}
    if not isinstance(offers,dict):offers={}
    geo=item.get('geo') or obj.get('geo') or {}
    if not isinstance(geo,dict):geo={}
    addr=item.get('address') or obj.get('address') or {}
    title=clean(item.get('name') or obj.get('name') or ' '.join(page.h1) or page.meta.get('og:title',''))
    desc=clean(item.get('description') or obj.get('description') or ' '.join(page.description) or page.props.get('description') or page.meta.get('description',''))
    kind,tx=classify(title+' '+str(obj.get('category','')),url,types(item)+types(obj))
    business=str(offers.get('businessFunction') or obj.get('businessFunction') or '')
    if business.endswith(('Sell','SellAction')):tx='sale'
    elif business.endswith(('LeaseOut','RentAction')):tx='rent'
    currency=offers.get('priceCurrency') or obj.get('priceCurrency') or page.props.get('priceCurrency') or page.meta.get('product:price:currency','')
    price=number(offers.get('price'))
    if price is None:price=number(obj.get('price'))
    if price is None:price=number(page.props.get('price') or page.meta.get('product:price:amount'))
    area=number((item.get('floorSize') or {}).get('value')) if isinstance(item.get('floorSize'),dict) else number(item.get('floorSize'))
    location=', '.join(str(addr.get(k,'')) for k in ['addressLocality','streetAddress','addressRegion'] if addr.get(k)) if isinstance(addr,dict) else str(addr)
    lat=number(geo.get('latitude') or page.props.get('latitude'));lon=number(geo.get('longitude') or page.props.get('longitude'))
    if lat is not None and not (-90<=lat<=90):lat=None
    if lon is not None and not (-180<=lon<=180):lon=None
    if not title or (price is None and not desc):raise ValueError('Nie rozpoznano szczegółów oferty; możliwa blokada lub zmiana struktury.')
    photo=image_url(item.get('image') or obj.get('image') or page.meta.get('og:image') or page.meta.get('twitter:image'),url)
    result = Listing(source,url,title,price,str(currency),area,lat,lon,location,'unknown',None,kind,tx,desc,str(obj.get('datePosted') or obj.get('datePublished') or ''),'','JSON-LD / metadane HTML',photo)
    return enrich(result,page,text,objects)


def unflatten_nuxt(values):
    """Decode devalue's reference array without executing JavaScript."""
    memo={}
    def get(i):
        if not isinstance(i,int) or isinstance(i,bool):return i
        if i<0:return None
        if i>=len(values):return None
        if i in memo:return memo[i]
        v=values[i]
        if isinstance(v,dict):
            result={};memo[i]=result
            for k,ref in v.items():result[k]=get(ref)
            return result
        if isinstance(v,list):
            if v and isinstance(v[0],str) and v[0] in {'Reactive','ShallowReactive','Ref','ShallowRef'}:
                memo[i]=None;result=get(v[1]);memo[i]=result;return result
            result=[];memo[i]=result;result.extend(get(ref) for ref in v);return result
        memo[i]=v;return v
    return get(0)


def safe_walk(obj):
    seen=set()
    def visit(v):
        if isinstance(v,(dict,list)):
            if id(v) in seen:return
            seen.add(id(v))
        if isinstance(v,dict):
            yield v
            for x in v.values():yield from visit(x)
        elif isinstance(v,list):
            for x in v:yield from visit(x)
    yield from visit(obj)


def enrich(result,page,text,objects):
    """Portal-specific extraction; never use arbitrary first coordinates from a page."""
    source=result.source
    if source in {'morizon','gratka'}:
        for a,s in page.scripts:
            if a.get('id')!='__NUXT_DATA__':continue
            try:data=unflatten_nuxt(json.loads(s))
            except (ValueError,RecursionError):continue
            ad=next((o for o in safe_walk(data) if isinstance(o.get('url'),str) and canonical(urljoin(result.url,o['url']))==canonical(result.url) and 'area' in o and 'location' in o),None)
            if ad:
                result.area_m2=number(ad.get('area'))
                loc=ad.get('location') or {};mp=loc.get('map') or {}
                geo=next((x for x in safe_walk(mp) if 'latitude' in x and 'longitude' in x),{})
                result.lat=number(geo.get('latitude'));result.lon=number(geo.get('longitude'))
                result.location=', '.join(str(x) for x in [loc.get('location'),loc.get('street')] if isinstance(x,str))
                result.evidence+=' + Nuxt: rekord o zgodnym URL'
                break
    elif source=='olx':
        for a,s in page.scripts:
            if a.get('id')!='olx-init-config':continue
            try:
                match=re.search(r'window\.__PRERENDERED_STATE__\s*=\s*',s)
                if not match:continue
                value,_=json.JSONDecoder().raw_decode(s[match.end():].lstrip());data=json.loads(value) if isinstance(value,str) else value
                product=next((o for o in objects if 'Product' in types(o)),{})
                sku=str(product.get('sku',''))
                ad=next((o for o in safe_walk(data) if str(o.get('id',''))==sku and 'map' in o),{})
                mp=ad.get('map') or {}
                result.lat=number(mp.get('lat'));result.lon=number(mp.get('lon'))
                for param in ad.get('params') or []:
                    if param.get('key') == 'm':
                        result.area_m2=number(param.get('normalizedValue'))
                if mp.get('radius'):
                    # OLX map radius is expressed in kilometres.
                    result.geo_radius_m=(number(mp['radius']) or 0)*1000
                result.geo_accuracy='approximate' if result.geo_radius_m else 'unknown'
                result.evidence+=' + OLX init config: zgodny identyfikator'
            except (ValueError,TypeError):continue
    elif source=='adresowo':
        places=[o for o in objects if 'Place' in types(o) and o.get('geo')]
        if len(places)==1:
            place=places[0];geo=place['geo'];result.lat=number(geo.get('latitude'));result.lon=number(geo.get('longitude'))
            result.location=str((place.get('address') or {}).get('streetAddress') or '')
            result.description=clean(place.get('description') or result.description)
            match=re.search(r'([\d,.]+)\s*m[²2]',str(place.get('name','')))
            if match:result.area_m2=number(match[1])
            result.evidence+=' + jedyny Place w JSON-LD'
    elif source=='sprzedajemy':
        match=re.search(r'data-coordinates="([^"]+)"',text)
        if match:
            import ast
            try:
                mp=ast.literal_eval(unescape(match[1]));result.lat=number(mp.get('lat'));result.lon=number(mp.get('lng'))
            except (ValueError,SyntaxError):pass
        # Category breadcrumbs establish listing type, not occurrences of "mieszkania" in a house title.
        categories=[str(o.get('name','')) for o in objects if 'ListItem' in types(o)]
        for o in objects:
            if 'ListItem' in types(o) and isinstance(o.get('item'),dict):categories.append(str(o['item'].get('name','')))
        cat=' '.join(categories)
        kind,tx=classify(cat,'')
        if kind!='unknown':result.property_type=kind
        if tx!='unknown':result.transaction=tx
        match=re.search(r'powierzchnia\s+domu\s*(?:ok[.]?\s*)?([\d ,.]+)\s*m[²2]',fold(result.description))
        if match:result.area_m2=number(match[1])
    if result.transaction=='unknown':
        head=fold(result.description[:250])
        if re.search(r'na sprzedaz|sprzedam|do sprzedania',head):result.transaction='sale'
        elif re.search(r'do wynajecia|na wynajem|wynajme',head):result.transaction='rent'
    if source=='nieruchomosci-online':
        for a,script in page.scripts:
            match=re.search(r'\bvar\s+map\s*=\s*',script)
            if not match:continue
            try:
                mp,_=json.JSONDecoder().raw_decode(script[match.end():].lstrip())
                if 'latitude' in mp and 'longitude' in mp:
                    result.lat=number(mp['latitude']);result.lon=number(mp['longitude'])
                    result.geo_accuracy='exact' if mp.get('isInaccurateLocation')==0 else 'approximate'
            except (ValueError,TypeError):pass
    if source=='szybko' and result.area_m2 is None:
        match=re.search(r'Powierzchnia\s*<span[^>]*>\s*([\d,. ]+)\s*m',text,re.I)
        if match:result.area_m2=number(match[1])
    return result
