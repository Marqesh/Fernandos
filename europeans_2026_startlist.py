"""UEC 2026 Slovenia Men's Elite Road Race: START LIST ONLY.

Read the start-list PDF linked by the official UEC event page. No results are
requested or parsed. A failed extraction must not replace a previously verified
snapshot with an empty roster. This script is an isolated historical test.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import fitz
import requests
from bs4 import BeautifulSoup

EVENT_PAGE = "https://www.uec.ch/en/event/281/2026-uec-road-european-championships"
OUT = Path("data/test-europeans-2026-startlist.json")
DIAGNOSTICS = Path("data/test-europeans-2026-pdf-diagnostics.json")
USER_AGENT = "PelotonLeaguePublicPageReader/1.0 (+personal noncommercial cycling league)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"}
TEAM_RE = re.compile(r"^([A-Z]{3})\s+([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ\s'’.-]{2,55})$")
RIDER_RE = re.compile(r"^(\d{1,3})\s+(.{5,95})$")

class PdfRosterValidationError(ValueError):
    def __init__(self, message: str, diagnostics: dict):
        super().__init__(message)
        self.diagnostics = diagnostics


COUNTRY_CODES = set("""ALB AND ARM AIN AUT AZE BEL BIH BUL CRO CYP CZE DEN ESP EST FIN FRA GBR GEO GER GRE HUN IRL ISL ISR ITA KOS LAT LTU LUX MDA MKD MLT MON MNE NED NOR POL POR ROU RUS SLO SRB SUI SVK SWE TUR UKR UZB""".split())


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def official_pdf_link(html: str, page_url: str = EVENT_PAGE) -> str:
    """Select only the Men's Elite ROAD RACE Start list in the UEC event table."""
    soup = BeautifulSoup(html, "html.parser")
    titles = " ".join(h.get_text(" ", strip=True) for h in soup.select("h1"))
    if "2026" not in titles or "EUROPEAN CHAMPIONSHIPS" not in titles.upper():
        raise ValueError("UEC event page does not identify 2026 championships")
    links = []
    for row in soup.select("tr"):
        labels = " ".join(row.stripped_strings)
        if not re.search(r"\bRoad\s+Race\s+Men\s+Elite\b", labels, re.I):
            continue
        if re.search(r"\b(Women|Junior|U23|Time Trial|ITT)\b", labels, re.I):
            continue
        for a in row.select("a[href]"):
            if not re.search(r"\bStart\s*list\b", a.get_text(" ", strip=True), re.I):
                continue
            url = urljoin(page_url, a["href"])
            parsed = urlparse(url)
            if parsed.scheme == "https" and parsed.hostname in ("www.uec.ch", "uec.ch") and parsed.path.lower().endswith(".pdf"):
                links.append(url)
    if len(set(links)) != 1:
        raise ValueError(f"Expected one official Men's Elite Road Race startlist PDF, found {len(set(links))}")
    return links[0]


def y_grouped_lines(page: fitz.Page, left: float, right: float) -> list[str]:
    """Reconstitute rows from PDF word coordinates, in a single page column."""
    words = page.get_text("words")
    selected = [w for w in words if left <= (w[0] + w[2]) / 2 < right]
    selected.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    groups: list[dict] = []
    for w in selected:
        y = (w[1] + w[3]) / 2
        if groups and abs(y - groups[-1]["y"]) <= 3.0:
            groups[-1]["words"].append(w)
        else:
            groups.append({"y": y, "words": [w]})
    return [" ".join(w[4] for w in sorted(g["words"], key=lambda x: x[0])).strip() for g in groups]


def page_column_strategies(pdf: fitz.Document) -> dict[str, list[str]]:
    """Try coordinate grouping and PyMuPDF text reconstruction independently."""
    geometrical: list[str] = []
    clipped: list[str] = []
    full: list[str] = []
    for page in pdf:
        mid = page.rect.width / 2
        for left, right in ((0, mid), (mid, page.rect.width + 1)):
            geometrical.extend(y_grouped_lines(page, left, right))
            clip = fitz.Rect(left, 0, right, page.rect.height)
            clipped.extend(page.get_text("text", clip=clip, sort=True).splitlines())
        full.extend(page.get_text("text", sort=True).splitlines())
    return {"pdf_positioned_rows": geometrical, "pdf_column_text": clipped, "pdf_full_text": full}


def parse_country_and_riders(lines: list[str]) -> list[dict]:
    team = None
    riders = []
    for raw in lines:
        line = " ".join(raw.strip().split())
        match = TEAM_RE.fullmatch(line)
        if match and match[1] in COUNTRY_CODES:
            team = match[2].strip()
            continue
        candidate = RIDER_RE.fullmatch(line)
        if candidate and team:
            bib = int(candidate[1])
            name = candidate[2].strip()
            if (1 <= bib <= 300 and len(name.split()) >= 2
                    and re.search(r"[A-Za-zÀ-ÿ]", name) and not re.search(r"\d", name)
                    and not re.search(r"(?i)starters?|ranking|results?|finishers?|riders?\s+total|communique", name)):
                riders.append({"bib": bib, "name": name, "team": team})
    return riders


def parse_official_startlist_pdf(binary: bytes, *, expected_year=2026) -> tuple[list[dict], dict]:
    if not binary.startswith(b"%PDF") or len(binary) > 12_000_000:
        raise ValueError("Official start list is missing a valid PDF signature or exceeds 12 MB")
    with fitz.open(stream=binary, filetype="pdf") as document:
        all_text = " ".join(p.get_text("text") for p in document)
        if not re.search(r"START\s*LIST\s*[|: -]*\s*Men\s+Elite\s+Road\s+Race", all_text, re.I):
            raise ValueError("PDF is not explicitly labelled Men Elite Road Race START LIST")
        if str(expected_year) not in all_text:
            raise ValueError("PDF does not verify the expected edition year")
        methods = page_column_strategies(document)
        summary = {"pdf_pages": len(document), "pdf_bytes": len(binary),
                   "strategies": {}, "sample_lines": methods["pdf_positioned_rows"][:95]}
        candidates = {}
        for method, lines in methods.items():
            parsed = parse_country_and_riders(lines)
            candidates[method] = parsed
            summary["strategies"][method] = {
                "rider_count": len(parsed), "team_count": len({r["team"] for r in parsed}),
                "rider_examples": parsed[:5], "lines_count": len(lines),
            }
        method = max(candidates, key=lambda m: (len(candidates[m]),len({r["team"] for r in candidates[m]})))
        riders = candidates[method]
        summary["selected_method"] = method
        by_bib = {}
        for rider in riders:
            old = by_bib.get(rider["bib"])
            if old is not None and old != rider:
                raise PdfRosterValidationError(f"Conflicting rider names for bib {rider['bib']}", summary)
            by_bib[rider["bib"]] = rider
        unique = [by_bib[k] for k in sorted(by_bib)]
        teams = len({r["team"] for r in unique})
        if len(unique) < 70 or teams < 12:
            raise PdfRosterValidationError(f"Only {len(unique)} usable riders in {teams} national teams; PDF parsing rejected", summary)
        summary["validated_rider_count"] = len(unique)
        summary["validated_team_count"] = teams
        summary["missing_bibs_within_range"] = sorted(set(range(unique[0]["bib"], unique[-1]["bib"] + 1)) - set(by_bib))[:100]
        return unique, summary


def main() -> int:
    previous = {}
    try:
        previous = json.loads(OUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        pass
    diagnostics = {"checked_at": now_iso(), "event_source_page": EVENT_PAGE, "source_type": "official_startlist_pdf"}
    result = {"schema_version": 1, "event_id": "europe-road-men-elite-2026-test",
              "event": "2026 UEC European Championships Road Race Men Elite",
              "edition_year": 2026, "race_date": "2026-10-04", "source": EVENT_PAGE,
              "checked_at": now_iso(), "status": "unavailable", "riders": []}
    try:
        event_resp = requests.get(EVENT_PAGE, timeout=(10, 25), headers=HEADERS)
        diagnostics["uec_event_http_status"] = event_resp.status_code
        event_resp.raise_for_status()
        pdf_url = official_pdf_link(event_resp.text, EVENT_PAGE)
        diagnostics["selected_pdf_url"] = pdf_url
        pdf_resp = requests.get(pdf_url, timeout=(10, 30), headers=HEADERS)
        diagnostics["uec_pdf_http_status"] = pdf_resp.status_code
        diagnostics["uec_pdf_content_type"] = pdf_resp.headers.get("content-type")
        pdf_resp.raise_for_status()
        riders, info = parse_official_startlist_pdf(pdf_resp.content, expected_year=2026)
        diagnostics.update(info)
        result.update(status="published", source=pdf_url, source_page=EVENT_PAGE,
                      method="uec_official_pdf", rider_count=len(riders), riders=riders,
                      last_success_at=now_iso())
    except Exception as exc:
        reason = f"{type(exc).__name__}: {str(exc)[:220]}"
        if isinstance(exc, PdfRosterValidationError):
            diagnostics.update(exc.diagnostics)
        diagnostics["error"] = reason
        result["warning"] = reason
        old_riders = previous.get("riders", [])
        if previous.get("status") in ("published", "stale") and old_riders:
            result.update(status="stale", riders=old_riders, rider_count=len(old_riders),
                          last_success_at=previous.get("last_success_at"),
                          source=previous.get("source", EVENT_PAGE))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    DIAGNOSTICS.write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{result['status']} | {len(result['riders'])} riders | {result.get('warning','no error')}")
    return 0 if result["status"] == "published" else 1


if __name__ == "__main__":
    raise SystemExit(main())
