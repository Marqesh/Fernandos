"""Cyclocross Men Elite startlists only. Independent of Peloton road feeds."""
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import fitz, requests
from bs4 import BeautifulSoup

HEADERS={'User-Agent':'PelotonCyclocrossLeague/0.1 (public noncommercial startlist reader)'}
LIST=re.compile(r'(?i)start\s*list|entry\s*list|startlijst|file_participants|deelnemerslijst|participants')
RESULT=re.compile(r'(?i)result|uitslag|ranking|classification|classement')
MEN=re.compile(r'(?i)men\s*(?:elite|senior)|elite\s*men|mannen\s*elite|heren\s*elite|men\s*elite\s*/\s*u23')
ROW=re.compile(r'^(\d{1,3})\s+(.+?)\s+(1\d{10})\s+([A-Z]{3})\s+(.+?)(?:\s+\d{1,4})?$')
NAME=re.compile(r"^[^\W\d_][\w'’ .-]{3,89}$")

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def norm(v): return ' '.join(str(v or '').replace('\xa0',' ').split())
def trusted(url,base):
 a,b=urlparse(url),urlparse(base)
 return a.scheme==b.scheme=='https' and bool(a.hostname) and a.hostname.removeprefix('www.')==b.hostname.removeprefix('www.')

def discover(html,base,race):
 soup=BeautifulSoup(html,'html.parser'); out=[];seen=set()
 for a in soup.select('a[href]'):
  url=urljoin(base,a.get('href',''))
  if not trusted(url,base) or url in seen:continue
  label=norm(a.get_text(' ',strip=True))
  tr=a.find_parent('tr')
  context=norm(tr.get_text(' ',strip=True)) if tr else label
  if RESULT.search(label+' '+url) or not LIST.search(context+' '+url):continue
  if race['series'].startswith('UEC'):
   if not re.search(r'(?i)men\s+elite',context) or re.search(r'(?i)women|junior|under\s*23|\bu23\b',context):continue
  if urlparse(url).path.lower().endswith('.pdf') or LIST.search(url):
   out.append({'url':url,'label':context,'provisional':bool(re.search(r'(?i)entry\s*list',label))});seen.add(url)
 return out[:5]

def category_year(pdf,race,category_hint=''):
 text=norm(' '.join(page.get_text('text',sort=True) for page in pdf))
 header=text[:1500]
 eventdate=race['start_date']
 dm=eventdate[8:]+'/'+eventdate[5:7]+'/'+eventdate[:4]
 dot=eventdate[8:]+'.'+eventdate[5:7]+'.'+eventdate[:4]
 correct_date=eventdate in text or dm in text or dot in text
 # November Middelkerke vs the February 2026 Middelkerke MUST be different events.
 if (str(race['year']) not in header and not correct_date) or (race['series']=='Superprestige' and not correct_date):
  return False,'wrong_or_unverified_date'
 if not (MEN.search(header) or (MEN.search(category_hint) and not re.search(r'(?i)women|junior|under\s*23',category_hint))):return False,'wrong_category'
 if race['series'].startswith('UEC') and not (correct_date or 'zeddam' in text.lower()):
  return False,'wrong_uec_event'
 if RESULT.search(header[:220]) and not LIST.search(header[:220]):return False,'results_rejected'
 return True,'ok'

def pdf_lines(pdf):
 for page in pdf:
  mid=page.rect.width/2
  for rect in (fitz.Rect(0,0,mid,page.rect.height),fitz.Rect(mid,0,page.rect.width,page.rect.height)):
   yield from (norm(line) for line in page.get_text('text',clip=rect,sort=True).splitlines())

def parse_pdf(blob,race,provisional=False,category_hint=''):
 if not blob.startswith(b'%PDF') or len(blob)>12_000_000:return [],'unsupported_pdf',{}
 with fitz.open(stream=blob,filetype='pdf') as pdf:
  ok,reason=category_year(pdf,race,category_hint)
  if not ok:return [],reason,{'pages':len(pdf),'header':norm(' '.join(page.get_text('text') for page in pdf))[:420]}
  # UEC Zeddam entry PDF: left column lists full names, right column has
  # matching UCI ID and nation. Bib numbers are not published in this document.
  if race['series'].startswith('UEC') and provisional:
   entries=[]
   for page in pdf:
    mid=page.rect.width/2
    left=[norm(x) for x in page.get_text('text',clip=fitz.Rect(0,0,mid,page.rect.height),sort=True).splitlines()]
    right=[norm(x) for x in page.get_text('text',clip=fitz.Rect(mid,0,page.rect.width,page.rect.height),sort=True).splitlines()]
    def is_rider_name(x):
     parts=x.split()
     return 2<=len(parts)<=8 and parts[0].isupper() and parts[-1].istitle() and bool(NAME.fullmatch(x)) and not re.search(r'\d',x)
    names=[x for x in left if is_rider_name(x)]
    identities=[]
    for x in right:
     m=re.fullmatch(r'(1\d{10})\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .-]{2,40})',x)
     if m:identities.append((m[1],m[2]))
    if len(names)!=len(identities):
     return [],'uec_columns_misaligned',{'names':len(names),'ids':len(identities),'name_samples':names[:5],'id_samples':identities[:5]}
    entries.extend({'bib':None,'name':name,'uci_id':uid,'nationality':nation,'team':nation} for name,(uid,nation) in zip(names,identities))
   if len(entries)>=race['min_riders'] and len({x['uci_id'] for x in entries})==len(entries):
    return entries,'provisional',{'parsed':len(entries),'method':'uec_parallel_columns'}
   return [],'parser_needed',{'parsed':len(entries),'method':'uec_parallel_columns'}
  # Prefer complete visual rows for narrow, one-page Superprestige tables.
  # Splitting such a page in half separates bib/name/ID from team and yields 0.
  full_rows=[norm(line) for page in pdf for line in page.get_text('text',sort=True).splitlines()]
  found=[]
  for line in full_rows:
   m=ROW.fullmatch(line)
   if m and NAME.fullmatch(norm(m[2])) and len(m[2].split())>=2:
    found.append({'bib':int(m[1]),'name':norm(m[2]),'uci_id':m[3],
                  'nationality':m[4],'team':norm(m[5])})
  # The fallback below is for different PDF layouts.
  lines=list(pdf_lines(pdf))

  for line in lines:
   m=ROW.fullmatch(line)
   if m and NAME.fullmatch(norm(m[2])) and len(m[2].split())>=2:
    found.append({'bib':int(m[1]),'name':norm(m[2]),'uci_id':m[3],'nationality':m[4],'team':norm(m[5])})
  # Many official startlists have vertically stacked columns.
  for i in range(len(lines)-4):
   if re.fullmatch(r'\d{1,3}',lines[i]) and re.fullmatch(r'1\d{10}',lines[i+2]) and re.fullmatch(r'[A-Z]{3}',lines[i+3]) and NAME.fullmatch(lines[i+1]) and len(lines[i+1].split())>=2:
    found.append({'bib':int(lines[i]),'name':lines[i+1],'uci_id':lines[i+2],'nationality':lines[i+3],'team':lines[i+4]})
  unique={}
  for r in found:
   if r['uci_id'] in unique and r!=unique[r['uci_id']]:return [],'conflicting_riders',{}
   unique[r['uci_id']]=r
  riders=list(unique.values())
  if len(riders)<race['min_riders']:return [],'parser_needed',{'parsed':len(riders),'samples':lines[:180]}
  return riders,('provisional' if provisional else 'published'),{'pages':len(pdf),'parsed':len(riders)}

def parse_html(html,race):
 soup=BeautifulSoup(html,'html.parser')
 title=norm((soup.title.get_text(' ',strip=True) if soup.title else '')+' '+' '.join(x.get_text(' ',strip=True) for x in soup.select('h1,h2')[:3]))
 if str(race['year']) not in title or not MEN.search(title):return [],'unverified_html_year_or_category'
 if race['series']=='Superprestige' and race['name'].split()[-1].lower() not in title.lower():return [],'wrong_event'
 riders=[];seen=set()
 for table in soup.select('table'):
  trs=table.select('tr')
  if not trs:continue
  head=[norm(t.get_text(' ',strip=True)).lower() for t in trs[0].find_all(['th','td'],recursive=False)]
  def ix(*labels):return next((i for i,h in enumerate(head) if h in labels),None)
  n=ix('name','naam','rider','rider name','coureur');bib=ix('bib','nr','no','number');tm=ix('team','club','ploeg');uid=ix('uci id','uci-id')
  if n is None:continue
  for tr in trs[1:]:
   cells=[norm(c.get_text(' ',strip=True)) for c in tr.find_all(['td','th'],recursive=False)]
   if n>=len(cells):continue
   name=cells[n]
   if not NAME.fullmatch(name) or len(name.split())<2:continue
   number=cells[bib] if bib is not None and bib<len(cells) else ''
   key=(name.casefold(),number)
   if key in seen:continue
   seen.add(key)
   riders.append({'bib':int(number) if number.isdigit() else None,'name':name,'team':cells[tm] if tm is not None and tm<len(cells) else None,'uci_id':cells[uid] if uid is not None and uid<len(cells) else None})
 return riders,('published' if len(riders)>=race['min_riders'] else 'parser_needed')

def inspect(race,prev=None,session=None):
 session=session or requests.Session()
 old=(prev or {}).get('startlist') or {}
 attempts=[];chosen=None
 for source in race['source_urls']:
  if not trusted(source,race['website']):continue
  try:
   response=session.get(source,headers=HEADERS,timeout=(8,22),allow_redirects=True)
   if not trusted(response.url,race['website']):raise ValueError('Offsite redirect')
   response.raise_for_status()
   if len(response.content)>12_000_000:raise ValueError('Oversize source')
   choices=[]
   if response.content.startswith(b'%PDF'):choices=[{'url':response.url,'provisional':False,'data':response.content}]
   elif 'html' in response.headers.get('Content-Type','text/html').lower():
    html=response.content.decode('utf-8','replace')
    riders,status=parse_html(html,race)
    if status=='published':chosen=(riders,status,response.url);break
    choices=discover(html,response.url,race)
   else:raise ValueError('Unknown content type')
   if not choices:attempts.append({'url':response.url,'status':'no_list_visible'})
   for candidate in choices:
    url=candidate['url']
    try:
     if 'data' in candidate:blob=candidate['data']
     else:
      res=session.get(url,headers=HEADERS,timeout=(8,22),allow_redirects=True)
      if not trusted(res.url,race['website']):raise ValueError('Offsite redirect')
      res.raise_for_status();blob=res.content
     if blob.startswith(b'%PDF'):riders,status,meta=parse_pdf(blob,race,candidate['provisional'],candidate.get('label',''))
     else:
      riders,status=parse_html(blob.decode('utf-8','replace'),race);meta={'parsed':len(riders)}
      if status=='published' and candidate['provisional']:status='provisional'
     attempts.append({'url':url,'label':candidate.get('label',''),'status':status,'details':meta})
     if status in ('published','provisional'):
      chosen=(riders,status,url);break
    except (requests.RequestException,ValueError,fitz.FileDataError) as e:
     attempts.append({'url':url,'status':'error','error':str(e)[:150]})
   if chosen:break
  except (requests.RequestException,ValueError) as e:
   attempts.append({'url':source,'status':'error','error':str(e)[:150]})
 if chosen:
  riders,status,url=chosen
  if status=='provisional' and old.get('status')=='published' and old.get('riders'):
   roster={**old,'status':'stale','warning':'Prior final list preserved'}
  else:roster={'status':status,'edition_year':race['year'],'category':race['category'],'riders':riders,'count':len(riders),'source_url':url,'checked_at':now(),'completeness':'entry_list' if status=='provisional' else 'start_list'}
 elif old.get('status') in ('published','stale','provisional') and old.get('riders'):
  roster={**old,'status':'stale','checked_at':now(),'warning':'Source unavailable; last verified snapshot retained'}
 else:
  roster={'status':'not_published','riders':[],'count':0,'checked_at':now(),'warning':'No validated correct-date Men Elite start list'}
 return {'id':race['id'],'name':race['name'],'date':race['start_date'],'year':race['year'],'discipline':'cyclocross','category':race['category'],'series':race['series'],'website':race['website'],'startlist':roster},attempts

def run(config,output,diag):
 races=json.loads(config.read_text())['races'];prev={}
 if output.exists():
  try:prev={r['id']:r for r in json.loads(output.read_text()).get('races',[])}
  except (ValueError,KeyError):pass
 entries=[];report=[]
 with requests.Session() as session:
  for race in races:
   entry,attempts=inspect(race,prev.get(race['id']),session)
   entries.append(entry);report.append({'id':race['id'],'attempts':attempts})
   print(race['id'],entry['startlist']['status'],entry['startlist']['count'],flush=True)
 for path,payload in ((output,{'schema_version':1,'season':'2026-2027','discipline':'cyclocross','generated_at':now(),'races':entries}),(diag,{'generated_at':now(),'attempts':report})):
  path.parent.mkdir(parents=True,exist_ok=True)
  path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
 p=argparse.ArgumentParser()
 p.add_argument('--config',default='cyclocross/races.json')
 p.add_argument('--output',default='cyclocross/data/latest.json')
 p.add_argument('--diagnostics',default='cyclocross/data/diagnostics.json')
 a=p.parse_args();run(Path(a.config),Path(a.output),Path(a.diagnostics))
