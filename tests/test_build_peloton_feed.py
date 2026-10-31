import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_peloton_feed import ALIASES, build_feed


def inputs():
    targets = {'season': 2027, 'races': []}
    watch = {'year': 2027, 'generated_at': '2026-10-31T10:00:00Z', 'races': []}
    prod = {'schema_version': 1, 'generated_at': '2026-10-31T11:00:00Z', 'races': []}
    for key in ALIASES:
        rid = f'{key}-2027'
        is_roubaix = key == 'paris-roubaix'
        is_tour = key == 'tour-de-france'
        race_type = 'grand_tour' if is_tour else 'one_day'
        date = '2027-04-11' if is_roubaix else '2027-07-02' if is_tour else None
        targets['races'].append({
            'id': rid, 'key': key, 'name': key.replace('-', ' ').title(),
            'year': 2027, 'type': race_type, 'start_date': date,
            'date_status': 'date_verified' if date else 'awaiting_2027_organiser_confirmation',
            'website': f'https://example.org/{key}/', 'organiser_family':'test',
        })
        watch['races'].append({
            'id': rid, 'name': key.replace('-', ' ').title(), 'year':2027,
            'start_date':date,'website':f'https://example.org/{key}/',
            'availability':'awaiting_2027_startlist',
            'startlist': {'status':'not_published', 'riders':[], 'count':0,
                          'checked_at': '2026-10-31T10:00:00Z'},
        })
    stage_dates = [f'2027-07-{day:02d}' for day in range(2, 26)]
    stage_docs = []
    stage_no = 0
    for idx, date in enumerate(stage_dates):
        if idx in (3, 11, 18):
            stage_docs.append({'date':date, 'kind':'rest', 'number':None})
        else:
            stage_no += 1
            stage_docs.append({'date':date, 'kind':'stage', 'number':stage_no})
    assert stage_no == 21
    prod['races'] = [
        {'id':'paris-roubaix-2027','name':'Paris-Roubaix', 'year':2027,
         'start_date':'2027-04-11','type':'one_day',
         'startlist':{'status':'not_published', 'riders':[], 'warning':'Shows 2026, not 2027'}},
        {'id':'tour-de-france-2027','name':'Tour de France','year':2027,
         'start_date':'2027-07-02','type':'grand_tour','stage_status':'published',
         'stages':stage_docs,'startlist':{'status':'not_published', 'riders':[]}},
    ]
    return targets,watch,prod


def test_30_race_catalog_with_only_verified_dates():
    feed = build_feed(*inputs())
    assert feed['schema_version'] == 1
    assert feed['import_mode'] == 'read_only'
    assert len(feed['races']) == feed['summary']['configured_races'] == 30
    assert feed['summary']['verified_startlists'] == 0
    assert feed['summary']['verified_dates'] == 2
    assert feed['summary']['published_stage_schedules'] == 1
    assert len([r for r in feed['races'] if r['start_date'] is None]) == 28
    assert all(not r['startlist']['riders'] for r in feed['races'])
    assert len(feed['races'][0]['aliases']) >= 1


def test_tour_stages_rest_days_and_readonly_dates():
    feed = build_feed(*inputs())
    tour = next(x for x in feed['races'] if x['key']=='tour-de-france')
    assert len(tour['stages']) == 24
    assert len(tour['race_days']) == 21
    assert tour['stage_status'] == 'published'
    assert tour['start_date'] == '2027-07-02'


def test_2026_startlist_never_published():
    targets,watch,prod = inputs()
    watch['races'][0]['startlist'] = {
        'status':'published', 'edition_year':2026,
        'riders':[{'name':f'Rider {i}', 'team':'Team'} for i in range(40)],
    }
    feed = build_feed(targets,watch,prod)
    first = feed['races'][0]
    assert first['startlist']['status'] == 'not_published'
    assert first['startlist']['riders'] == []


def test_verified_2027_roster_is_display_only():
    targets,watch,prod=inputs()
    watch['races'][0]['startlist'] = {
        'status':'published', 'edition_year':2027,
        'riders':[{'bib':i+1,'name':f'Rider {i}', 'team':'Team'} for i in range(60)],
        'source_url':'https://example.org/startlist'
    }
    feed=build_feed(targets,watch,prod)
    assert feed['summary']['verified_startlists'] == 1
    assert feed['races'][0]['startlist']['status'] == 'published'
    assert feed['races'][0]['startlist']['count'] == 60
    assert feed['races'][0]['import_mode'] == 'read_only'


def test_duplicate_names_rejected():
    targets,watch,prod=inputs()
    watch['races'][0]['startlist'] = {
        'status':'published', 'edition_year':2027,
        'riders':[{'bib':i+1,'name':'Same Rider', 'team':'Team'} for i in range(60)],
    }
    assert build_feed(targets,watch,prod)['summary']['verified_startlists'] == 0


def test_wrong_year_watcher_hard_failure():
    t,w,p=inputs()
    w['races'][3]['year']=2026
    with pytest.raises(ValueError, match='Wrong-year'):
        build_feed(t,w,p)


def test_date_disagreement_requires_review():
    t,w,p=inputs()
    p['races'][0]['start_date']='2027-04-12'
    feed=build_feed(t,w,p)
    roubaix=next(x for x in feed['races'] if x['key']=='paris-roubaix')
    assert roubaix['date_status']=='change_requires_review'
    assert roubaix['start_date']=='2027-04-11'


def test_uec_2026_website_rewritten_to_generic_root():
    t,w,p=inputs()
    item=next(x for x in t['races'] if x['key']=='european-championships-me-rr')
    item['website']='https://www.uec.ch/en/event/281/2026-championships'
    feed=build_feed(t,w,p)
    race=next(x for x in feed['races'] if x['key']=='european-championships-me-rr')
    assert race['website']=='https://www.uec.ch/'


def test_production_stage_year_mismatch_rejected():
    t,w,p=inputs()
    p['races'][1]['stages'][0]['date']='2026-07-02'
    feed=build_feed(t,w,p)
    tour=next(x for x in feed['races'] if x['key']=='tour-de-france')
    assert tour['stages']==[]
    assert tour['stage_status']=='not_published'


def test_wrong_target_date_rejected():
    t,w,p=inputs()
    t['races'][3]['start_date']='2026-03-01'
    with pytest.raises(ValueError, match='Invalid 2027 date'):
        build_feed(t,w,p)


def test_important_aliases():
    assert 'Volta a Figueira' in ALIASES['figueira-champions-classic']
    assert 'Worlds TT ME' in ALIASES['worlds-men-elite-itt']
    assert 'Criterium du Dauphine' in ALIASES['tour-auvergne-rhone-alpes']
