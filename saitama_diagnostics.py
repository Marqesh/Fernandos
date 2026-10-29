"""Live Saitama page diagnostics. Does not bypass access restrictions."""
import json
import datetime as dt
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from scraper import parse_saitama_teams
URL='https://saitama-criterium.jp/crtm2026/team/team-cyclist-fa/'
OUT=Path('data/test-saitama-diagnostics.json')
result={'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source_url':URL}
try:
    r=requests.get(URL,timeout=(10,25),headers={'User-Agent':'PelotonLeaguePublicPageReader/1.0 (+personal noncommercial cycling league)'})
    result.update(http_status=r.status_code,content_type=r.headers.get('Content-Type'),final_host=urlparse(r.url).hostname)
    if r.ok and 'html' in r.headers.get('Content-Type','').lower() and len(r.content)<4000000:
        soup=BeautifulSoup(r.text,'html.parser')
        result['page_title']=soup.title.get_text(' ',strip=True) if soup.title else None
        result['heading_samples']=[{'tag':h.name,'text':h.get_text(' ',strip=True)[:140]} for h in soup.select('h1,h2,h3,h4,h5,h6')[:65]]
        p=parse_saitama_teams(r.text)
        result.update(parsed_year=p['edition_year'],parsed_rider_count=len(p['riders']),parsed_rider_examples=p['riders'][:5])
except requests.RequestException as e:
    result['request_error']=type(e).__name__
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Live diagnostics saved:',result.get('http_status'),result.get('parsed_rider_count'))
