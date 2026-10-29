"""Watch all 30 2027 edition startlists without importing previous-year riders."""
import argparse
import json
from pathlib import Path
from startlists_2026 import scrape_one, make_session, utcnow, is_trusted_url

def build_watchlist(history, targets):
    prior = {r['key']: r for r in history}
    output = []
    for target in targets:
        old = prior[target['key']]
        race = {
            'id': old['key'] + '-2027', 'key': old['key'], 'year': 2027,
            'name': target.get('name', old['name']), 'type': target.get('type', old['type']),
            'start_date': target.get('start_date'), 'website': target.get('website') or old['website'],
            'organiser_family': old['organiser_family'], 'min_riders': old.get('min_riders', 55),
            'min_teams': old.get('min_teams', 8), 'startlist_sources': [],
        }
        for key in ('document_match','national_teams','roster_adapter'):
            if key in old: race[key] = old[key]
        candidates = target.get('startlist_sources', [])
        if old['organiser_family'] not in ('uci','uec') and not candidates:
            for src in old['startlist_sources']:
                url = src['url']
                if '2026' in url: url = url.replace('2026','2027')
                if is_trusted_url(url, old['website']):
                    candidates.append({'url':url, 'verification':'unverified_2027_candidate'})
        race['startlist_sources'] = candidates[:3]
        output.append(race)
    return output

def classify(record,attempts):
    if record['startlist']['status']=='published':return 'confirmed_2027'
    if record['startlist']['status']=='stale':return 'last_verified_snapshot'
    if not attempts:return 'event_page_pending'
    if any(a.get('edition_year')==2026 for a in attempts):return 'older_edition'
    if any(a.get('format')=='pdf' and a.get('edition_year')==2027 and not a.get('extracted_count') for a in attempts):return 'parser_needed'
    if any(a.get('edition_year')==2027 and a.get('extracted_count',0)>0 for a in attempts):return 'validation_failed'
    reasons=' '.join(str(a.get('reason','')) for a in attempts).lower()
    if '403' in reasons or '429' in reasons:return 'source_restricted'
    if '404' in reasons:return 'page_not_available'
    if 'ssl' in reasons or 'connection' in reasons or 'timeout' in reasons:return 'source_error'
    return 'awaiting_2027_startlist'

def run(config,targets,output,diagnostics,delay=1.0):
    history=json.loads(Path(config).read_text(encoding='utf-8'))['races']
    planned=json.loads(Path(targets).read_text(encoding='utf-8'))['races']
    watch=build_watchlist(history,planned)
    if len(watch)!=30:raise ValueError('Expected 30 configured races')
    prev={}
    if Path(output).exists():
        try:prev={r['id']:r for r in json.loads(Path(output).read_text())['races']}
        except (KeyError,ValueError,TypeError):pass
    rows,errors=[],[]
    with make_session() as session:
        for race in watch:
            rec,attempts=scrape_one(race,session,prev.get(race['id']),delay)
            status=classify(rec,attempts)
            rec['availability']=status
            # 2026 and unavailable source pages must not appear as 2027 published rosters.
            if status in ('older_edition','event_page_pending','awaiting_2027_startlist','page_not_available'):
                if rec['startlist']['status']=='unavailable':rec['startlist']['status']='not_published'
            rows.append(rec)
            errors.append({'race_id':race['id'],'availability':status,'attempts':attempts})
            print(race['id'],status,rec['startlist'].get('count',0),flush=True)
    for path,value in ((output,{'year':2027,'generated_at':utcnow(),'races':rows}),
                       (diagnostics,{'year':2027,'generated_at':utcnow(),'races':errors})):
        p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return rows

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--config',default='races_2026.json')
    p.add_argument('--targets',default='races_2027_targets.json')
    p.add_argument('--output',default='data/watch-2027.json')
    p.add_argument('--diagnostics',default='data/watch-2027-diagnostics.json')
    p.add_argument('--delay',type=float,default=1.0)
    a=p.parse_args();run(a.config,a.targets,a.output,a.diagnostics,a.delay)
