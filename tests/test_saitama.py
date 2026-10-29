import datetime as dt
import json
from pathlib import Path
from scraper import choose_roster, validate_roster, run, scrape_race
ROOT=Path(__file__).parent.parent
SOURCE=(ROOT/'tests/fixtures/saitama_2026_sample.html').read_text(encoding='utf-8')
RACE=json.loads((ROOT/'test_races.json').read_text(encoding='utf-8'))['races'][0]
NOW=dt.datetime(2026,10,29,10,0,tzinfo=dt.timezone.utc)
def test_saitama_bilingual():
    p=choose_roster(SOURCE, adapter='saitama')
    assert p['edition_year']==2026 and len(p['riders'])==9
    assert p['riders'][0]['name']=='Haoyu SU' and p['riders'][3]['name']=='Brandon MCNULTY'
    assert p['riders'][3]['bib'] is None
    assert validate_roster(p,RACE)==(True,'OK')
def test_saitama_redesign():
    page=SOURCE.replace('<h4>','<h5>').replace('</h4>','</h5>').replace('<section>','<section class="redesign">')
    assert len(choose_roster(page,adapter='saitama')['riders'])==9
def test_saitama_year_rejected():
    for page in [SOURCE.replace('2026 ツール','ツール'),SOURCE.replace('2026 ツール','2025 ツール')]:
        assert not validate_roster(choose_roster(page,adapter='saitama'),RACE)[0]
def test_saitama_test_feed_isolated(tmp_path):
    cfg=tmp_path/'config.json'
    cfg.write_text(json.dumps({'races':[RACE]}),encoding='utf-8')
    out=tmp_path/'test.json'
    feed=run(cfg,out,now=NOW,force=True,getter=lambda u:SOURCE)
    roster=feed['races'][0]['startlist']
    assert roster['status']=='published' and roster['completeness']=='provisional'
    assert len(roster['riders'])==9 and len(feed['races'])==1
def test_saitama_preserve_on_failure():
    old={'startlist':{'status':'published','edition_year':2026,'riders':choose_roster(SOURCE,adapter='saitama')['riders']}}
    def fail(url):
        raise ConnectionError('blocked')
    output=scrape_race(RACE,old,now=NOW,getter=fail,force=True)
    assert output['startlist']['status']=='stale' and len(output['startlist']['riders'])==9
