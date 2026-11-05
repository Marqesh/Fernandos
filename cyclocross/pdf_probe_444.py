"""One-off read-only inspection of the supplied Superprestige PDF 444.

No assumptions about event/date/category. Never inject into the live CX feed.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
import fitz
import requests

URL="https://www.superprestigecyclocross.be/storage/programs/file_participants/444/444.pdf?t=1793894883"
OUT=Path("cyclocross/data/probe-444.json")
USER_AGENT="PelotonCyclocrossLeague/1.0 (public start-list PDF inspection)"
ROW=re.compile(r"^\s*(\d{1,3})\s+([^\d]{5,90}?)\s+(1\d{10})\s+([A-Z]{3})\s+(.{2,125}?)\s*(?:\d{1,4})?\s*$")
DATE_RE=re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]20\d{2}\b")
EVENT_RE=re.compile(r"\b(?:Middelkerke|Niel|Zeddam|Ostrava|Merksplas|Overijse|Ruddervoorde|Gullegem)\b",re.I)

def candidate_rows(page):
    plain = page.get_text("text",sort=True)
    lines=[" ".join(z.split()) for z in plain.splitlines() if z.strip()]
    direct = []
    for s in lines:
        m=ROW.fullmatch(s)
        if m:direct.append({"bib":int(m[1]),"name":m[2].strip(),"uci_id":m[3],"nationality":m[4],"team":m[5].strip()})
    # Row-by-row extraction using PDF visual coordinates. The PDF can scatter
    # cells across spans, so group by y at a small tolerance.
    words=page.get_text("words")
    words.sort(key=lambda w: ((w[1]+w[3])/2,w[0]))
    groups=[]
    for w in words:
        y=(w[1]+w[3])/2
        if groups and abs(y-groups[-1]["y"])<=2.7:
            groups[-1]["words"].append(w)
        else:
            groups.append({"y":y,"words":[w]})
    visual=[" ".join(w[4] for w in sorted(g["words"],key=lambda w:w[0])) for g in groups]
    visual_hits=[]
    for line in visual:
        m=ROW.fullmatch(" ".join(line.split()))
        if m:visual_hits.append({"bib":int(m[1]),"name":m[2].strip(),"uci_id":m[3],"nationality":m[4],"team":m[5].strip()})
    return direct,visual_hits,lines,visual

def main():
    result={"checked_at":dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_url":URL,"document_type":"unknown","publication":"not_verified"}
    try:
        r=requests.get(URL,headers={"User-Agent":USER_AGENT,"Accept":"application/pdf"},timeout=(10,30))
        result.update(http_status=r.status_code,content_type=r.headers.get("content-type"),bytes=len(r.content),final_url=r.url)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF") or len(r.content)>12_000_000:
            raise ValueError("Source is not a reasonably sized PDF")
        result["sha256"]=hashlib.sha256(r.content).hexdigest()
        with fitz.open(stream=r.content,filetype="pdf") as doc:
            first=" ".join(doc[0].get_text("text",sort=True).split()) if len(doc) else ""
            text="\n".join(page.get_text("text",sort=True) for page in doc)
            result.update(pages=len(doc),header=first[:850],date_mentions=sorted(set(DATE_RE.findall(text))),
                          event_mentions=sorted(set(EVENT_RE.findall(text))))
            result["heading_lines"]=text.splitlines()[:55]
            all_hits=[]
            result["pages_data"]=[]
            for i,page in enumerate(doc):
                direct,visual_hits,raw_lines,visual_lines=candidate_rows(page)
                hits=visual_hits if len(visual_hits)>=len(direct) else direct
                all_hits.extend(hits)
                result["pages_data"].append({"page":i+1,"direct_hits":len(direct),"visual_hits":len(visual_hits),
                    "first_visual_rows":visual_lines[:12],
                    "last_visual_rows":visual_lines[-5:]})
            by_id={x["uci_id"]:x for x in all_hits}
            result.update(parser_candidate_rows=len(all_hits),unique_uci_ids=len(by_id),
                          rider_examples=list(by_id.values())[:12])
            if len(by_id)>=8 and re.search(r"(?i)\bstartlist\b", first[:350]) and re.search(r"(?i)\bmen\s*elite\b",first[:350]):
                result["document_type"]="men_elite_startlist_candidate"
                result["candidate_riders"]=list(by_id.values())
            else:
                result["document_type"]="needs_category_or_layout_review"
                result["text_excerpt"]=text[:5000]
    except Exception as e:
        result["error"]=type(e).__name__+": "+str(e)[:240]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PDF inspection",result.get("http_status"),result.get("header","")[:160],
          "riders",result.get("unique_uci_ids",0),"error",result.get("error",""))
if __name__=="__main__":
    main()
