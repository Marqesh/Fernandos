"""Isolated 2026 Slovenia UEC Men Elite road race startlist importer. No results."""
import datetime as dt
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://www.domestiquecycling.com/en/cycling-races/europe-rr-men/2026/startlist/"
OUT = Path("data/test-europeans-2026-startlist.json")
COUNTRIES = {
 "Belgium","France","Slovenia","Denmark","Italy","Netherlands","Germany","Spain",
 "Portugal","Switzerland","United Kingdom","Great Britain","Austria","Poland",
 "Luxembourg","Czech Republic","Czechia","Slovakia","Norway","Sweden","Finland",
 "Hungary","Romania","Ireland","Ukraine","Lithuania","Latvia","Estonia","Serbia",
 "Croatia","Greece","Cyprus","Turkey","Türkiye","Israel","Azerbaijan","Albania",
 "Moldova","Bulgaria","Kosovo","Iceland","Montenegro","Bosnia and Herzegovina",
 "North Macedonia","Georgia","Armenia","Malta","Andorra","Monaco"
}
BIB = re.compile(r"^(\d{1,3})\s+(.+)$")
BAD = re.compile(r"\b(?:DNF|DNS|DSQ|result|rank|points|time gap)\b", re.I)

def extract(html):
    soup = BeautifulSoup(html,"html.parser")
    title = soup.title.get_text(" ",strip=True) if soup.title else ""
    if not ("2026" in title and ("europe" in title.lower() or "championship" in title.lower())
            and "startlist" in title.lower().replace(" ","")):
        raise ValueError("Source title does not identify 2026 European Championships startlist")
    # Preserve element boundaries: don't flatten country headings and bib text together.
    for e in soup.select("script,style,nav,footer,header"):
        e.decompose()
    # Work from the explicit Startlist section if the page provides one.
    text = soup.get_text("\n",strip=True)
    lines = [re.sub(r"\s+"," ",v).strip() for v in text.splitlines()]
    riders, team, pending = [], None, None
    for i,line in enumerate(lines):
        if line in COUNTRIES:
            team = line
            pending = None
            continue
        match = BIB.match(line)
        if team and match:
            bib,name=int(match.group(1)),match.group(2).strip()
            if 3<=len(name)<=85 and re.search(r"[A-Za-zÀ-ÿ]",name) and not BAD.search(name):
                riders.append({"bib":bib,"name":name,"team":team})
            continue
        # Some sites render the bib and rider name as adjacent separate elements.
        if team and line.isdecimal() and 1<=int(line)<=300:
            pending=int(line)
            continue
        if team and pending is not None and len(line.split())>=2 and 3<=len(line)<=85:
            if re.search(r"[A-Za-zÀ-ÿ]",line) and not BAD.search(line):
                riders.append({"bib":pending,"name":line,"team":team})
            pending=None
    clean = {}
    for item in riders:
        if item["bib"] in clean and clean[item["bib"]] != item:
            raise ValueError("Bib conflict in parsed data")
        clean[item["bib"]] = item
    final=[clean[k] for k in sorted(clean)]
    if len(final)<80 or len(set(r["team"] for r in final))<12:
        raise ValueError(f"Insufficient verified riders: {len(final)} in {len(set(r['team'] for r in final))} teams")
    return final

def main():
    result={"schema_version":1,"event_id":"europe-road-men-elite-2026-test",
      "event":"2026 UEC European Championships Road Race Men Elite",
      "edition_year":2026,"race_date":"2026-10-04","source":URL,
      "checked_at":dt.datetime.now(dt.timezone.utc).isoformat(),"status":"unavailable","riders":[]}
    try:
        resp=requests.get(URL,timeout=(10,30),
            headers={"User-Agent":"PelotonLeaguePublicPageReader/1.0 (+personal noncommercial cycling league)"})
        result["http_status"]=resp.status_code
        resp.raise_for_status()
        riders=extract(resp.text)
        result.update(status="published",rider_count=len(riders),riders=riders)
    except Exception as exc:
        result["warning"]=f"{type(exc).__name__}: {str(exc)[:230]}"
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(result["status"],len(result["riders"]),result.get("warning",""))
    if result["status"]!="published":
        raise SystemExit(1)

if __name__=="__main__":
    main()
