import json
from pathlib import Path
import fitz
from cx_scraper import discover, parse_pdf, parse_html, trusted, inspect

RACES=json.loads((Path(__file__).resolve().parents[1]/'races.json').read_text())['races']

def make_pdf(text):
 pdf=fitz.open()
 page=pdf.new_page()
 page.insert_text((50,50),text,fontsize=8,lineheight=1.3)
 return pdf.tobytes()

def test_calendar_pinned():
 assert len(RACES)==26
 assert len({r['id'] for r in RACES})==26
 assert RACES==sorted(RACES,key=lambda r:(r['start_date'],r['id']))
 assert RACES[0]['start_date']=='2026-11-05'
 assert RACES[-1]['start_date']=='2027-01-31'
 assert {r['category'] for r in RACES}=={'Men Elite'}
 assert {r['year'] for r in RACES}=={2026,2027}
 assert all(r['year']==int(r['start_date'][:4]) for r in RACES)
 assert all(r['id'].startswith('cx-') and r['start_date'][:4] in r['id'] for r in RACES)
 assert sum(r['series']=='UCI Cyclo-cross World Cup' for r in RACES)==12
 assert sum(r['series']=='Superprestige' for r in RACES)==7
 assert sum(r['series']=='X²O Badkamers Trofee' for r in RACES)==5
 assert sum(r['series'].endswith('Championships') for r in RACES)==2
 assert RACES[0]['source_urls'][0].endswith('444.pdf?t=1793894883')

def test_uec_selects_me_entry_list_exclusively():
 html='<table><tr><td>Women Elite</td><td><a href="/w.pdf">Entry list Women Elite</a></td></tr><tr><td>Men U23</td><td><a href="/u.pdf">Entry list Men U23</a></td></tr><tr><td>Men Elite</td><td><a href="/m.pdf">Entry list Men Elite</a></td><td><a href="/results.pdf">Results</a></td></tr></table>'
 links=discover(html,RACES[1]['website'],RACES[1])
 assert [x['url'].split('/')[-1] for x in links]==['m.pdf']
 assert links[0]['provisional']

def test_offhost_or_result_urls_not_followed():
 html='<a href="https://other.test/startlist.pdf">Start list</a><a href="/results.pdf">Results Start list</a>'
 assert discover(html,RACES[0]['website'],RACES[0])==[]
 assert not trusted('http://www.uec.ch/x','https://www.uec.ch/')

def test_old_february_middelkerke_pdf_is_not_november_event():
 pdf=make_pdf('NOORDZEECROSS MIDDELKERKE 07/02/2026\nSTARTLIST MEN ELITE/U23\n')
 riders,status,_=parse_pdf(pdf,RACES[0])
 assert not riders and status=='wrong_or_unverified_date'

def test_wrong_edition_pdf_rejected():
 pdf=make_pdf('NOORDZEECROSS MIDDELKERKE 05/11/2027\nSTARTLIST MEN ELITE/U23\n')
 riders,status,_=parse_pdf(pdf,RACES[0])
 assert not riders and status=='wrong_or_unverified_date'

def test_valid_html_riders_stay_in_correct_category():
 head='<html><head><title>Middelkerke Men Elite 2026</title></head><body><h1>2026 Men Elite Middelkerke start list</h1><table><tr><th>Bib</th><th>Name</th><th>Team</th></tr>'
 rows=''.join(f'<tr><td>{i}</td><td>Rider Sample{chr(65+i)}</td><td>Club Team</td></tr>' for i in range(10))
 parsed,status=parse_html(head+rows+'</table></body></html>',RACES[0])
 assert len(parsed)==10 and status=='published'

def test_no_false_list_and_preserve_previous():
 class Resp:
  headers={'Content-Type':'text/html'}
  content=b'<html><title>Middelkerke 2026</title></html>'
  url=RACES[0]['website']
  def raise_for_status(self):pass
 class Session:
  def get(self,*a,**kw):return Resp()
 entry,_=inspect(RACES[0],session=Session())
 assert entry['startlist']['status']=='not_published'
 prev={'startlist':{'status':'published','riders':[{'bib':1,'name':'Verified Rider'}],'edition_year':2026}}
 entry,_=inspect(RACES[0],prev,session=Session())
 assert entry['startlist']['status']=='stale'
