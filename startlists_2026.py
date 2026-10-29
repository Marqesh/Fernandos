"""Peloton: official organiser START-LIST importer, historical/production editions.

Single-source, limited-depth public HTML/PDF reader. No results, no API keys,
no CAPTCHA bypass, no inference of 2027 riders from 2026 sources.

CLI: python startlists_2026.py --config races_2026.json --output data/history-2026.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

import fitz
import requests
from bs4 import BeautifulSoup

from scraper import choose_roster, validate_roster, norm_key, normalize

AGENT = "PelotonLeaguePublicPageReader/2.0 (noncommercial cycling league; public pages only)"
USER_HEADERS = {"User-Agent": AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"}
HINT = re.compile(r"entry[ -]?list|start[ -]?list|starting[ -]?list|starters|partants|participants|coureurs|riders|deelnemers|startlijst|elenco[ -]?(?:iscritti|partenti)|liste[ -]?(?:depart|departants)|equipos|teams|squadre|pdf\s*startlist", re.I)
NOT_ROSTER = re.compile(r"result|ranking|classifica|uitslag|classement|podi[uo]m|finishers?|winners?|highlights|news|roadbook|technical guide|quota|bulletin", re.I)
WRONG_CATEGORY = re.compile(r"women|fem[mie]|donne|damen|junior|under.?23|\bu23\b", re.I)
BIB_LINE = re.compile(r"^\s*(\d{1,3})\s+([\wÀ-ÿ'’\-., ]{5,95})\s*$", re.U)
TEAM_CODE = re.compile(r"^([A-Z]{3})\s+([A-ZÀ-Ÿ][A-ZÀ-Ÿ&'’.\s-]{3,70})$")
PDF_STOP_WORDS = re.compile(r"(?i)\b(average|result|rank|speed|gap|stage|time|km|category|riders|starters|nationality|nation|date|finish|dns|dnf|dsq)\b")
ALLOWED_COUNTRY = set("ALB AND ARM AIN AUT AZE BEL BIH BUL CRO CYP CZE DEN ESP EST FIN FRA GBR GEO GER GRE HUN IRL ISL ISR ITA KOS LAT LTU LUX MDA MKD MLT MON MNE NED NOR POL POR ROU RUS SLO SRB SUI SVK SWE TUR UKR UZB".split())


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_trusted_url(url: str, base: str) -> bool:
    target, original = urlparse(url), urlparse(base)
    if target.scheme != "https" or original.scheme != "https":
        return False
    # Off-site URLs are not followed automatically; each external site requires approval.
    th, bh = (target.hostname or "").lower(), (original.hostname or "").lower()
    return th == bh or th.removeprefix("www.") == bh.removeprefix("www.")


def extract_team_tables(soup: BeautifulSoup) -> list[dict]:
    """Official organiser HTML: team header followed by Dorsal/Corredor table."""
    results = []
    for table in soup.select("table"):
        heads = [norm_key(x.get_text(" ", strip=True)) for x in table.select("tr")[:1] for x in x.find_all(["th", "td"], recursive=False)]
        bib_i = next((i for i, s in enumerate(heads) if s in ("bib", "no", "number", "dorsal", "startnr", "start number", "nº", "n°")), None)
        rider_i = next((i for i, s in enumerate(heads) if "corredor" in s or "rider" in s or s in ("name", "nombre", "nom", "coureur", "athlete")), None)
        if bib_i is None or rider_i is None:
            continue
        team_i = next((i for i, s in enumerate(heads) if "team" in s or "equipo" in s or "equipe" in s), None)
        team_node = table.find_previous(re.compile(r"^h[23456]$"))
        team = normalize(team_node.get_text(" ", strip=True)) if team_node else ""
        if not team or len(team) > 95 or re.search(r"(?i)teams|equipos|riders|race|startlist", team):
            team = ""
        for row in table.select("tr")[1:]:
            cols = [normalize(c.get_text(" ", strip=True)) for c in row.find_all(["td", "th"], recursive=False)]
            if max(bib_i, rider_i, (team_i if team_i is not None else 0)) >= len(cols):
                continue
            bib = cols[bib_i].strip()
            name = cols[rider_i].strip()
            group = cols[team_i].strip() if team_i is not None else team
            if not bib.isdecimal() or not group or not (5 <= len(name) <= 95) or not re.search(r"[A-Za-zÀ-ÿ]", name):
                continue
            if not (2 <= len(name.split()) <= 9) or re.search(r"\b(?:start|finish|points|stage|rank)\b", name, re.I):
                continue
            results.append({"bib": int(bib), "name": name, "team": group})
    return results


def parse_grouped_heading_list(soup: BeautifulSoup) -> list[dict]:
    """For simple organiser lists using headings to name teams and list items for riders."""
    out=[]
    for head in soup.find_all(re.compile(r"^h[2-5]$")):
        team=normalize(head.get_text(" ", strip=True))
        if not (4<=len(team)<=80) or re.search(r"(?i)\b(startlist|riders|latest|registration|copyright|participants|teams|results)\b",team):
            continue
        limit=0
        for node in head.next_elements:
            limit+=1
            if limit>900:break
            if getattr(node,"name",None) in ("h1","h2","h3","h4","h5"):break
            if getattr(node,"name",None) not in ("li","tr","p"):continue
            m=BIB_LINE.match(normalize(node.get_text(" ",strip=True)))
            if m and 1<=int(m[1])<=300 and len(m[2].split())>=2:
                out.append({"bib":int(m[1]),"name":normalize(m[2]),"team":team})
    return out


def document_year(html: str, url: str) -> int | None:
    soup=BeautifulSoup(html,"html.parser")
    from scraper import find_roster_year
    title=(soup.title.get_text(' ',strip=True) if soup.title else '')
    if NOT_ROSTER.search(title):return None
    exact=find_roster_year(soup)
    if exact:return exact
    # Safer when heading itself or URL explicitly identifies the edition AND list.
    page_title=soup.title.get_text(" ",strip=True) if soup.title else ""
    headings=" ".join(h.get_text(" ",strip=True)[:150] for h in soup.select("h1,h2,h3")[:5])
    strong=re.search(r"(?<!\d)(20\d{2})(?!\d)", page_title+" "+headings)
    context=page_title+" "+headings+" "+url
    page_headings=page_title+' '+headings
    # Never mistake archived results for an entry list, even when redirected.
    if NOT_ROSTER.search(page_title):return None
    if strong and HINT.search(page_headings):return int(strong[1])
    # Explicit year in URL must also have a roster/team heading in the HTML.
    path=urlparse(url).path
    year=re.search(r"(?<!\d)(20\d{2})(?!\d)",path)
    if year and HINT.search(path) and HINT.search(page_headings):return int(year[1])
    return None


def parse_html_roster(html: str,url: str,race: dict) -> tuple[list[dict],int | None,str]:
    soup=BeautifulSoup(html,"html.parser")
    possible=[]
    if race.get('roster_adapter')!='heading_table':
        generic=choose_roster(html)
        possible.append((generic.get('method','aso'),generic.get('riders',[])))
    possible.append(('heading_table',extract_team_tables(soup)))
    possible.append(('grouped_headings',parse_grouped_heading_list(soup)))
    method,riders=max(possible,key=lambda p:len(p[1]))
    return riders,document_year(html,url),method


def pdf_lines(document:fitz.Document) -> dict[str,list[str]]:
    by_column=[]
    by_text=[]
    for page in document:
        width=page.rect.width
        mid=width/2
        for rect in (fitz.Rect(0,0,mid,page.rect.height),fitz.Rect(mid,0,width,page.rect.height)):
            by_column.extend([normalize(l) for l in page.get_text('text',clip=rect,sort=True).splitlines()])
        by_text.extend([normalize(l) for l in page.get_text('text',sort=True).splitlines()])
    return {'pdf_columns':by_column,'pdf_text':by_text}


def pdf_riders(lines:list[str])->list[dict]:
    riders=[]
    team=None
    for line in lines:
        line=normalize(line)
        country=TEAM_CODE.fullmatch(line)
        if country and country[1] in ALLOWED_COUNTRY:
            team=country[2].strip()
            continue
        m=BIB_LINE.fullmatch(line)
        if m and team and 1<=int(m[1])<=300 and not PDF_STOP_WORDS.search(m[2]) and 2<=len(m[2].split())<=8:
            riders.append({'bib':int(m[1]),'name':normalize(m[2]),'team':team})
    return riders


def parse_pdf_roster(binary:bytes, race:dict, source_url:str)->tuple[list[dict],int|None,str,dict]:
    if not binary.startswith(b'%PDF') or len(binary)>14_000_000:
        raise ValueError('Source was not a valid, reasonably-sized PDF')
    with fitz.open(stream=binary,filetype='pdf') as doc:
        text=' '.join(p.get_text('text') for p in doc)
        years={int(y) for y in re.findall(r'(?<!\d)(20\d\d)(?!\d)',text)}
        # The document is edition-specific only if the configured year appears.
        year=race['year'] if race['year'] in years else None
        context=' '.join(text.split()[:1300]).lower()
        if race.get('national_teams') and not re.search(r'(?i)start\s*list|starting\s*list|entry\s*list',text):
            return [],year,'pdf_not_labelled_startlist',{'pages':len(doc),'year_candidates':sorted(years)}
        if race.get('document_match'):
            bits=race['document_match'].lower().split()
            # Championship documents require category in their first page or URL.
            prefix=' '.join(text.split()[:450]).lower()+ ' '+source_url.lower().replace('%20',' ')
            if race['organiser_family']=='uec' and not all(x in prefix for x in ('men','elite','road','race')):
                return [],year,'pdf_wrong_category',{'pages':len(doc),'year_candidates':sorted(years)}
            if race['organiser_family']=='uci' and not all(x in prefix for x in ('men','elite')):
                return [],year,'pdf_wrong_category',{'pages':len(doc),'year_candidates':sorted(years)}
        strategies=pdf_lines(doc)
        candidates={method:pdf_riders(lines) for method,lines in strategies.items()}
        method=max(candidates,key=lambda x:len(candidates[x]))
        return candidates[method],year,method,{'pages':len(doc),'year_candidates':sorted(years),'line_samples':strategies[method][:15], 'strategy_counts':{k:len(v) for k,v in candidates.items()}}


def find_link_candidates(html:str,base_url:str,race:dict)->list[str]:
    """At most three same-host public roster links; never results or other categories."""
    soup=BeautifulSoup(html,'html.parser')
    candidates=[]
    expected_sub=race.get('document_match','')
    for row in soup.select('tr'):
        if not expected_sub:continue
        label=' '.join(row.stripped_strings)
        if norm_key(expected_sub) not in norm_key(label):continue
        for a in row.select('a[href]'):
            label=normalize(a.get_text(' ',strip=True))
            href=urljoin(base_url,a.get('href',''))
            if not is_trusted_url(href,base_url):continue
            if HINT.search(label+' '+href) and not NOT_ROSTER.search(label+' '+href):
                candidates.append(href)
    if candidates:return list(dict.fromkeys(candidates))[:3]
    # Generic fallback only to directly linked rider/startlist pages; not external sites.
    for a in soup.select('a[href]'):
        text=normalize(a.get_text(' ',strip=True))[:100]
        href=urljoin(base_url,a.get('href',''))
        name=text+' '+href
        if not is_trusted_url(href,base_url):continue
        if not HINT.search(name) or NOT_ROSTER.search(name) or WRONG_CATEGORY.search(name):continue
        if race.get('organiser_family')=='uci':continue  # UCI combined entry lists need sub-event selection
        if race.get('organiser_family')=='uec':continue  # UEC only exact row matches above
        if re.search(r'(?i)\bteams\b|\bequipos\b',text) and not re.search(r'2026|2027',name):continue
        candidates.append(href)
    return list(dict.fromkeys(candidates))[:3]


def make_session() -> requests.Session:
    return requests.Session()


def fetch(session: requests.Session,url:str,base:str) -> tuple[bytes,str,str]:
    if not is_trusted_url(url,base):raise ValueError('Untrusted source hostname')
    response=session.get(url,headers=USER_HEADERS,timeout=(8,17),allow_redirects=True)
    if not is_trusted_url(response.url,base):raise ValueError('Source redirected outside approved organiser domain')
    response.raise_for_status()
    if len(response.content)>14_000_000:raise ValueError('Source exceeds 14 MB')
    kind='pdf' if response.content.startswith(b'%PDF') else ('html' if 'html' in response.headers.get('Content-Type','text/html').lower() else 'unsupported')
    if kind=='unsupported':raise ValueError('Unrecognised source type')
    return response.content,kind,response.url


def evaluate(extracted:list[dict],year:int|None,method:str,race:dict,previous:dict|None=None)->tuple[bool,str]:
    if year is None:return False,'Edition year unverified'
    if year!=race['year']:return False,f"Wrong edition {year}, expected {race['year']}"
    if len({norm_key(r['team']) for r in extracted}) < race.get('min_teams',8):
        return False, 'Insufficient distinct teams'
    e={'edition_year':year,'riders':extracted}
    return validate_roster(e,{'year':race['year'],'min_riders':race.get('min_riders',55),'allow_missing_bib':False},(previous or {}).get('startlist')) if extracted else (False,'No rider rows found')


def scrape_one(race:dict,session:requests.Session,previous:dict|None=None,delay:float=0.5)->tuple[dict,list[dict]]:
    checked=utcnow()
    record={key:race[key] for key in ('id','name','year','type','start_date')}
    for optional in ('end_date','website','key','organiser_family'):
        if optional in race:record[optional]=race[optional]
    attempts=[]
    best=None
    visited=set()
    for source in race.get('startlist_sources',[]):
        base=source['url']
        queue=[base]
        while queue and len(visited)<5:
            url=queue.pop(0)
            if url in visited:continue
            visited.add(url)
            diag={'url':url,'verification':source.get('verification','candidate'),'checked_at':checked}
            try:
                data,kind,final=fetch(session,url,base)
                diag['format']=kind
                diag['bytes']=len(data)
                diag['final_url']=final
                if kind=='html':
                    html=data.decode('utf-8',errors='replace')
                    soup=BeautifulSoup(html,'html.parser')
                    diag['title']=(soup.title.get_text(' ',strip=True)[:160] if soup.title else '')
                    riders,edition,method=parse_html_roster(html,final,race)
                    diag.update(method=method,edition_year=edition,extracted_count=len(riders))
                    if url==base and len(visited)<5:
                        queue.extend(x for x in find_link_candidates(html,final,race) if x not in visited)
                else:
                    riders,edition,method,pdf_meta=parse_pdf_roster(data,race,final)
                    diag.update(method=method,edition_year=edition,extracted_count=len(riders),pdf=pdf_meta)
                ok,why=evaluate(riders,edition,method,race,previous)
                diag['validation']='passed' if ok else 'rejected'
                diag['reason']=why
                if ok:
                    best={'status':'published','edition_year':race['year'],'source_url':final,'checked_at':checked,
                          'riders':riders,'count':len(riders),'method':method,'completeness':'archived_startlist_not_verified_final'}
                    attempts.append(diag)
                    break
            except (requests.RequestException,ValueError,fitz.FileDataError) as exc:
                diag.update(validation='error',reason=type(exc).__name__+': '+str(exc)[:150])
            attempts.append(diag)
            if delay:time.sleep(delay)
        if best:break
    if best:
        record['startlist']=best
    else:
        old=(previous or {}).get('startlist') or {}
        prior=old.get('riders') if old.get('status') in ('published','stale') else None
        record['startlist']={'status':'stale' if prior else 'unavailable','riders':prior or [],
                             'checked_at':checked,'warning':'No validated correct-edition 2026 start list found',
                             'count':len(prior) if prior else 0}
    return record,attempts


def run(config_path:Path,output_path:Path,report_path:Path,delay:float=0.5):
    config=json.loads(config_path.read_text(encoding='utf-8'))
    prior={}
    if output_path.exists():
        try:
            prior={x['id']:x for x in json.loads(output_path.read_text(encoding='utf-8')).get('races',[])}
        except (OSError,ValueError,KeyError):pass
    races=[]
    report=[]
    with make_session() as session:
        for i,race in enumerate(config['races'],1):
            if not race.get('enabled',True):continue
            record,attempts=scrape_one(race,session,prior.get(race['id']),delay)
            races.append(record)
            report.append({'race_id':race['id'],'status':record['startlist']['status'],
                           'riders':record['startlist']['count'],'attempts':attempts})
            print(f"[{i:02d}/{len(config['races']):02d}] {race['name']} {record['startlist']['status']} "
                  f"({record['startlist']['count']} riders); {len(attempts)} sources",flush=True)
    final={'schema_version':1,'season':config['season'],'generated_at':utcnow(),
           'scope':'historical_startlists_only','races':races}
    diagnostics={'season':config['season'],'generated_at':utcnow(),'races':report}
    for path,doc in ((output_path,final),(report_path,diagnostics)):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Validated',sum(r['startlist']['status']=='published' for r in races),'of',len(races),'races')
    return final


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config',default='races_2026.json')
    p.add_argument('--output',default='data/history-2026.json')
    p.add_argument('--report',default='data/history-2026-diagnostics.json')
    p.add_argument('--delay',type=float,default=.5)
    p.add_argument('--force',action='store_true',help='Historical run ignores normal date windows')
    args=p.parse_args()
    data=run(Path(args.config),Path(args.output),Path(args.report),args.delay)
    return 0 if len(data['races'])==len(json.loads(Path(args.config).read_text())['races']) else 1

if __name__=='__main__':
    raise SystemExit(main())