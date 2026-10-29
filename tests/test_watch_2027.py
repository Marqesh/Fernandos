"""Guards 2027 watchlist against copying historical start lists/dates."""
from watch_2027 import build_watchlist, classify


def test_historical_date_is_not_guessed_for_2027():
    historical = [{
        'key':'test-race','name':'Test Race','year':2026,'type':'one_day',
        'start_date':'2026-04-04','website':'https://example.org/',
        'organiser_family':'independent',
        'startlist_sources':[{'url':'https://example.org/teams-2026/'}]
    }]
    targets = [{
        'key':'test-race','name':'Test Race','type':'one_day','year':2027,
        'start_date':None,'startlist_sources':[],
    }]
    result = build_watchlist(historical, targets)
    assert result[0]['year']==2027 and result[0]['start_date'] is None
    assert result[0]['startlist_sources'][0]['url']=='https://example.org/teams-2027/'


def test_federation_2026_event_url_not_reused():
    for org in ('uec','uci'):
        history=[{
            'key':'championship','name':'Championship','year':2026,
            'type':'one_day','start_date':'2026-10-04',
            'organiser_family':org,'website':'https://www.uec.ch/',
            'startlist_sources':[{'url':'https://www.uec.ch/en/event/281/2026-championship'}],
        }]
        targets=[{'key':'championship','start_date':None,'startlist_sources':[]}]
        assert build_watchlist(history,targets)[0]['startlist_sources']==[]


def test_wrong_year_page_status_is_not_published():
    record={'startlist':{'status':'unavailable','riders':[]}}
    status=classify(record,[{'format':'html','edition_year':2026,'extracted_count':175}])
    assert status=='older_edition'


def test_2027_pdf_parser_error_has_separate_diagnostic():
    record={'startlist':{'status':'unavailable','riders':[]}}
    assert classify(record,[{'format':'pdf','edition_year':2027,'extracted_count':0}])=='parser_needed'
