"""Diagnostic only: discover the historical 2026 Slovenia Men Elite start-list markup."""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SOURCES = {
    "uec_official": "https://www.uec.ch/en/event/281/2026-uec-road-european-championships",
    "domestique_startlist": "https://www.domestiquecycling.com/en/cycling-races/europe-rr-men/2026/startlist/",
    "cyclingstartlist": "https://cyclingstartlist.com/event/EuropeanChampionshipsRoadRaceMen",
}
OUT = Path("data/test-europeans-2026-diagnostics.json")
HEADERS = {"User-Agent": "PelotonLeaguePublicPageReader/1.0 (+personal noncommercial cycling league)"}
PATTERN = re.compile(r"start\s*list|starting\s*list|men.{0,8}elite|elite.{0,8}men|road race", re.I)

def analyze(name, url):
    obj = {"source": name, "url": url}
    try:
        r = requests.get(url, timeout=(10, 25), headers=HEADERS)
        obj.update(http_status=r.status_code, content_type=r.headers.get("Content-Type", ""),
                   final_url=r.url, bytes=len(r.content), hash=hashlib.sha256(r.content).hexdigest()[:16])
        if r.status_code != 200 or "html" not in obj["content_type"].lower() or len(r.content) > 4_000_000:
            return obj
        soup = BeautifulSoup(r.text, "html.parser")
        obj["title"] = soup.title.get_text(" ", strip=True)[:200] if soup.title else ""
        obj["headings"] = [{"tag":tag.name, "text":tag.get_text(" ", strip=True)[:160]}
                           for tag in soup.select("h1,h2,h3,h4,h5,h6")[:35]]
        anchors = []
        for a in soup.select("a[href]"):
            text = a.get_text(" ", strip=True)
            href = urljoin(r.url, a.get("href", ""))
            row = a.find_parent("tr")
            context = row.get_text(" ", strip=True) if row else a.parent.get_text(" ", strip=True) if a.parent else ""
            if PATTERN.search(text + " " + context + " " + href):
                anchors.append({"text": text[:100], "href": href[:320], "context": context[:200]})
        obj["startlist_link_candidates"] = anchors[:90]
        obj["link_count"] = len(soup.select("a[href]"))
        obj["tables"] = len(soup.select("table"))
        obj["table_heading_samples"] = [x.get_text(" ", strip=True)[:150]
            for x in soup.select("table tr")[:4]]
        obj["bib_row_samples"] = [x.get_text(" ", strip=True)[:130] for x in soup.select("tr,li") 
            if re.match(r"^\s*(1|2|3|4|5|17|18|19|20|72)\s+",x.get_text(" ",strip=True))][:20]
        obj["text_startlist_mentions"] = len(re.findall(r"start\s*list",soup.get_text(" ",strip=True),re.I))
        obj["year_mentions"] = len(re.findall(r"(?<!\d)2026(?!\d)",soup.get_text(" ",strip=True)))
    except Exception as e:
        obj["error"] = type(e).__name__ + ": " + str(e)[:180]
    return obj

data = {"checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "sources": [analyze(n,u) for n,u in SOURCES.items()]}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
for s in data["sources"]:
    print(s["source"], s.get("http_status"), s.get("title","")[:80],len(s.get("startlist_link_candidates",[])),s.get("error",""))
