import io
import json
from pathlib import Path

import fitz
import pytest
from bs4 import BeautifulSoup

from startlists_2026 import (
    document_year, evaluate, extract_team_tables, find_link_candidates,
    is_trusted_url, parse_html_roster, parse_pdf_roster, scrape_one,
)

ROOT=Path(__file__).resolve().parents[1]
CAL=json.loads((ROOT/'races_2026.json').read_text(encoding='utf-8'))['races']
PLANNED=json.loads((ROOT/'races_2027_targets.json').read_text(encoding='utf-8'))['races']


def test_user_calendar_has_thirty_dates_in_correct_offset():
    assert len(CAL)==30
    assert [r['id'] for r in CAL]==[r['key']+'-2026' for r in CAL]
    assert len(set(r['key'] for r in CAL))==30
    assert [r['start_date'] for r in CAL[:4]]==['2026-02-14','2026-02-16','2026-02-18','2026-02-28']
    assert CAL[-1]['start_date']=='2026-10-10'
    assert CAL[27]['start_date']=='2026-09-27' and CAL[27]['key']=='worlds-men-elite-rr'
    assert CAL[28]['start_date']=='2026-10-04' and CAL[28]['key']=='european-championships-me-rr'


def test_2027_unknowns_never_inherit_2026_dates():
    assert len(PLANNED)==30
    assert len({r['key'] for r in PLANNED})==30
    assert len([r for r in PLANNED if r['enabled']])==2
    assert [r['key'] for r in PLANNED if r['enabled']]==['paris-roubaix','tour-de-france']
    assert all(r['start_date'] is None for r in PLANNED if not r['enabled'])
    assert all(not r['startlist_sources'] for r in PLANNED if not r['enabled'])


def test_all_sources_are_official_https_and_unique():
    for race in CAL:
        assert len(race['startlist_sources'])>=1
        assert race['year']==2026
        assert all(s['url'].startswith('https://') for s in race['startlist_sources'])
        assert all(is_trusted_url(s['url'],race['website']) for s in race['startlist_sources'])


def test_asoline_title_year_found():
    html='<html><title>Paris Nice</title><body><h1>2026 Start list</h1><h3>Team X</h3></body></html>'
    assert document_year(html,'https://www.paris-nice.fr/en/riders')==2026


def test_wrong_edition_not_accepted():
    html='<html><title>2027 Start List</title><h1>2027 Start list</h1></html>'
    assert document_year(html,'https://www.paris-nice.fr/en/riders')==2027
    assert evaluate([{'bib':1,'name':'Peter PRIMOZ','team':'Slovenia'}],2027,'fixture',CAL[6])[0] is False


def test_results_page_not_accepted_even_with_riders_url():
    html='<html><title>2026 Results and Rankings</title><h1>2026 Start list</h1></html>'
    assert document_year(html,'https://www.paris-nice.fr/en/riders') is None


def test_only_same_organiser_documents_followed():
    html='<html><title>2026 Teams</title><a href="https://bad.example/startlist/2026">Start list</a>' \
         '<a href="/teams-2026">Teams 2026</a><a href="/results">Results</a></html>'
    links=find_link_candidates(html,'https://itzulia.eus/en/',CAL[12])
    assert links==['https://itzulia.eus/teams-2026']


def build_heading_table(num_teams=12):
    parts=['<html><title>Teams 2026 · Itzulia</title><h1>Teams 2026</h1>']
    for t in range(num_teams):
        parts.append(f'<h3>Team Cycling {t}</h3><table><tr><th>Dorsal</th><th>País</th><th>Corredor</th></tr>')
        for i in range(7):parts.append(f'<tr><td>{t*10+i+1}</td><td>🇪🇸</td><td>RIDER NAME {t}{i}</td></tr>')
        parts.append('</table>')
    return ''.join(parts)+'</html>'


def test_heading_table_extraction_and_validation():
    race=CAL[12]
    html=build_heading_table()
    riders,year,method=parse_html_roster(html,'https://itzulia.eus/en/teams-2026/',race)
    assert (len(riders),year,method)==(84,2026,'heading_table')
    assert evaluate(riders,year,method,race)==(True,'OK')


def test_team_count_sanity_check():
    race=CAL[12]
    riders,year,method=parse_html_roster(build_heading_table(2),'https://itzulia.eus/en/teams-2026/',race)
    assert not evaluate(riders,year,method,race)[0]


def test_uec_document_selector_only_matches_mens_elite_rr():
    html='''<h1>2026 UEC Road European Championships</h1><table>
    <tr><td>Road Race Women Elite</td><td><a href="/women.pdf">Start list</a></td></tr>
    <tr><td>ITT Men Elite</td><td><a href="/itt.pdf">Start list</a></td></tr>
    <tr><td>Road Race Men Elite</td><td><a href="/resources/2026/me.pdf">Start list</a></td><td><a href="/res.pdf">Results</a></td></tr>
    <tr><td>Road Race Men Junior</td><td><a href="/jun.pdf">Start list</a></td></tr></table>'''
    race=CAL[28]
    assert find_link_candidates(html,race['website'],race)==['https://www.uec.ch/resources/2026/me.pdf']


def test_uci_requires_specific_subevent_document():
    html='<a href="/2026-entry-list.pdf">2026 Entry List (all events)</a>'
    for race in (CAL[26],CAL[27]):
        assert find_link_candidates(html,race['website'],race)==[]


def test_pdf_reader_can_extract_national_teams():
    pdf=fitz.open()
    page=pdf.new_page(width=595,height=842)
    lines=['2026 UEC ROAD EUROPEAN CHAMPIONSHIPS', 'START LIST - Men Elite Road Race']
    for team,code in enumerate(('BEL','FRA','SLO','DEN','ITA','ESP','NED','SUI','GER','AUT','POR','CZE')):
        lines.append(f'{code} NATIONAL TEAM')
        for j in range(7):lines.append(f'{team*10+j+1} NAME SURNAME')
    page.insert_text((50,45),'\n'.join(lines),fontsize=7, lineheight=1.1)
    data=pdf.tobytes()
    riders,year,method,diag=parse_pdf_roster(data,CAL[28],'https://www.uec.ch/startlist.pdf')
    assert year==2026
    assert len(riders)>=50
    assert diag['pages']==1


class MockResponse:
    def __init__(self,text,status_code=200,url='https://www.paris-nice.fr/en/riders'):
        self.content=text.encode('utf-8')
        self.status_code=status_code
        self.url=url
        self.headers={'Content-Type':'text/html'}
    def raise_for_status(self):
        if self.status_code!=200:raise ValueError('HTTP error')

class MockSession:
    def __init__(self,html):self.html=html
    def get(self,url,headers,timeout,allow_redirects):return MockResponse(self.html,url=url)


def test_keep_old_roster_when_current_source_is_invalid():
    r=CAL[6]
    old={'startlist':{'status':'published','riders':[{'bib':5,'name':'JOHN DOE','team':'TEAM'}]}}
    rec,diagnostics=scrape_one(r,MockSession('<html><title>Results 2026</title></html>'),old,delay=0)
    assert rec['startlist']['status']=='stale'
    assert rec['startlist']['riders']==old['startlist']['riders']
    assert diagnostics


def test_no_previous_data_means_unavailable_not_fake_riders():
    r=CAL[6]
    rec,diagnostics=scrape_one(r,MockSession('<html><title>Results 2026</title></html>'),None,delay=0)
    assert rec['startlist']['status']=='unavailable'
    assert rec['startlist']['riders']==[]