"""Peloton race importer: public organiser HTML to a validated, static JSON feed.

No paid or third-party cycling API. Fetches publicly accessible HTML only.
Usage: python scraper.py --config races.json --output data/latest.json
       python scraper.py --config races.json --output /tmp/test.json --force
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

import requests
from bs4 import BeautifulSoup

UTC = dt.timezone.utc
NAME_RE = re.compile(r"^\s*(\d{1,3})\s*[-.:]?\s+(.{4,100}?)\s*$", re.U)
YEAR_NEAR_LIST = re.compile(
    r"\b(20\d\d)\s*(?:start\s*list|starters?|riders?\s*list|liste\s+des\s+coureurs\s+partants|partants|participants)\b"
    r"|\b(?:start\s*list|starters?|liste\s+des\s+coureurs\s+partants|partants)\s*(?:for\s*)?(20\d\d)\b",
    re.I,
)
BAD_TEAM_WORDS = (
    "start list", "starters", "riders", "classement", "rankings",
    "classification", "follow us", "latest news", "race schedule",
    "stage ", "paris roubaix", "paris-roubaix", "coureurs partants", "contact", "subscribe",
)
DATE_ISO = re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)")
DATE_SLASH = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(20\d{2})(?!\d)")
KNOWN_FIELDS = {"bib", "bibNumber", "number", "riderNumber", "startNumber"}


def utc_now() -> dt.datetime:
    return dt.datetime.now(UTC).replace(microsecond=0)


def iso(instant: dt.datetime) -> str:
    return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_utc(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo else result.replace(tzinfo=UTC)
    except ValueError:
        return None


def normalize(text: str) -> str:
    return " ".join(str(text).split()).strip()


def norm_key(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", normalize(text))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def plausible_name(name: str) -> bool:
    name = normalize(name)
    return (
        5 <= len(name) <= 95 and bool(re.search(r"[A-Za-zÀ-ÿ]", name))
        and len(name.split()) >= 2 and not any(x in name.lower() for x in ("http", "sign up", "cookie", "register"))
    )


def parse_rider(text: str, team: str) -> dict[str, Any] | None:
    m = NAME_RE.match(normalize(text))
    if not m or not team:
        return None
    bib, name = int(m.group(1)), normalize(m.group(2))
    if bib == 0 or not plausible_name(name):
        return None
    return {"bib": bib, "name": name, "team": normalize(team)}


def is_team_heading(heading: str) -> bool:
    heading = normalize(heading)
    return (
        5 <= len(heading) <= 85
        and not re.search(r"\b20\d{2}\b", heading)
        and not any(word in heading.lower() for word in BAD_TEAM_WORDS)
        and len(heading.split()) <= 10
        and any(c.isalpha() for c in heading)
    )


def find_roster_year(soup: BeautifulSoup) -> int | None:
    """Fail closed if a roster's own title doesn't establish its edition.

    Homepage race dates and current season banners never count as evidence.
    """
    evidence = []
    for node in soup.select("h1,h2,h3,h4,title,[aria-label]"):
        for value in (node.get_text(" ", strip=True), node.get("aria-label", "")):
            if len(value) > 180:
                continue
            match = YEAR_NEAR_LIST.search(value)
            if match:
                evidence.append(int(match.group(1) or match.group(2)))
    # Some organisers place the heading in a <div> or <strong>; only exact,
    # short strings containing the key phrase are accepted.
    if not evidence:
        for s in soup.stripped_strings:
            if len(s) > 100:
                continue
            match = YEAR_NEAR_LIST.search(s)
            if match:
                evidence.append(int(match.group(1) or match.group(2)))
    if not evidence or len(set(evidence)) != 1:
        return None
    return evidence[0]


def parse_semantic_list(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """ASO-style h3 team headings followed by HTML list items (CSS-independent)."""
    output: list[dict[str, Any]] = []
    for heading in soup.find_all(re.compile("^h[2-5]$")):
        team = normalize(heading.get_text(" ", strip=True))
        if not is_team_heading(team):
            continue
        candidates = []
        visited = 0
        for sibling in heading.next_elements:
            visited += 1
            if visited > 2500:
                break
            if getattr(sibling, "name", "") in ("h1", "h2", "h3", "h4", "h5"):
                break
            if getattr(sibling, "name", "") != "li":
                continue
            # A single li can have nested spans; combine text into one rider.
            rider = parse_rider(sibling.get_text(" ", strip=True), team)
            if rider:
                candidates.append(rider)
        # Require multiple entries: avoids arbitrary page headings + single links.
        if len(candidates) >= 2:
            output.extend(candidates)
    return output


def parse_tables(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """For lists rendered as standard tables with bib, name and team columns."""
    riders = []
    for table in soup.select("table"):
        rows = table.select("tr")
        if not rows:
            continue
        head = [norm_key(x.get_text(" ", strip=True)) for x in rows[0].select("th,td")]
        try:
            bib_i = next(i for i, x in enumerate(head) if x in ("bib", "no.", "number", "dossard", "n°", "nr"))
            name_i = next(i for i, x in enumerate(head) if any(z in x for z in ("rider", "name", "coureur", "nom")))
            team_i = next(i for i, x in enumerate(head) if any(z in x for z in ("team", "equipe", "squadra")))
        except StopIteration:
            continue
        for row in rows[1:]:
            cols = [normalize(x.get_text(" ", strip=True)) for x in row.select("td,th")]
            if max(bib_i, name_i, team_i) >= len(cols):
                continue
            rider = parse_rider(f"{cols[bib_i]} {cols[name_i]}", cols[team_i])
            if rider:
                riders.append(rider)
    return riders


def parse_json_records(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Recognise embedded rider JSON when available, without private endpoints."""
    riders = []
    def walk(obj: Any, depth: int = 0) -> None:
        if depth > 14:
            return
        if isinstance(obj, dict):
            lower = {norm_key(k): k for k in obj}
            bib = next((obj[key] for key in KNOWN_FIELDS if key in obj), None)
            name = obj.get("name") or obj.get("fullName") or obj.get("riderName")
            if not name and (obj.get("firstName") and obj.get("lastName")):
                name = f'{obj["firstName"]} {obj["lastName"]}'
            if isinstance(name, dict):
                name = name.get("name")
            team = obj.get("teamName") or obj.get("team_name") or obj.get("team")
            if isinstance(team, dict):
                team = team.get("name")
            if (bib is not None and isinstance(name, str) and isinstance(team, str)):
                rider = parse_rider(f"{bib} {name}", team)
                if rider:
                    riders.append(rider)
            for val in obj.values():
                walk(val, depth + 1)
        elif isinstance(obj, list):
            for val in obj[:600]:
                walk(val, depth + 1)
    for script in soup.select('script[type="application/json"],script[type="application/ld+json"],script#__NEXT_DATA__'):
        payload = script.string or script.get_text()
        if not payload or len(payload) > 4_000_000:
            continue
        try:
            walk(json.loads(payload))
        except (ValueError, RecursionError):
            continue
    return riders


def choose_roster(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    edition = find_roster_year(soup)
    strategies = {
        "embedded_json": parse_json_records(soup),
        "semantic_html": parse_semantic_list(soup),
        "html_table": parse_tables(soup),
    }
    # Pick the richest coherent independent extraction. Never combine methods
    # as doing so could produce duplicates from page variants.
    strategy, riders = max(strategies.items(), key=lambda x: len(x[1]))
    return {"edition_year": edition, "method": strategy, "riders": riders}


def validate_roster(extracted: dict[str, Any], race: dict[str, Any], prev: dict[str, Any] | None = None) -> tuple[bool, str]:
    if extracted["edition_year"] is None:
        return False, "Roster edition not explicitly identified"
    if extracted["edition_year"] != race["year"]:
        return False, f'Source contains {extracted["edition_year"]} riders, not {race["year"]}'
    riders = extracted["riders"]
    if len(riders) < int(race.get("min_riders", 10)):
        return False, f"Only {len(riders)} plausible riders (minimum {race.get('min_riders', 10)})"
    bibs = [r["bib"] for r in riders]
    if len(bibs) != len(set(bibs)):
        return False, "Repeated bib numbers in extracted riders"
    names = [norm_key(r["name"]) for r in riders]
    if len(names) != len(set(names)):
        return False, "Repeated rider names"
    if len(set(r["team"] for r in riders)) < 2:
        return False, "Could not identify multiple teams"
    old = (prev or {}).get("riders", [])
    if old and len(riders) < 0.7 * len(old):
        return False, f"Roster unexpectedly shrank from {len(old)} to {len(riders)}"
    return True, "OK"


def parse_page_date(html: str, year: int, date_format: str = "dmy", expected: str | None = None) -> str | None:
    """Only accept a single unambiguous race-date candidate near expected date.

    Does NOT assume that news publishing dates are event dates. Returns None if
    multiple plausible dates are present. This is conservative by design.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Remove footer, articles (news) and blog snippets to avoid unrelated dates.
    for node in soup.select("footer,article,script,style,.news,.news-list,.posts"):
        node.decompose()
    content = soup.get_text(" ", strip=True)
    candidates = set()
    for m in DATE_ISO.finditer(content):
        try:
            d = dt.date(int(m[1]), int(m[2]), int(m[3]))
            if d.year == year:
                candidates.add(d)
        except ValueError:
            continue
    for m in DATE_SLASH.finditer(content):
        a, b, y = map(int, m.groups())
        month, day = (a, b) if date_format == "mdy" else (b, a)
        try:
            d = dt.date(y, month, day)
            if d.year == year:
                candidates.add(d)
        except ValueError:
            continue
    if not candidates:
        return None
    if expected:
        expected_day = dt.date.fromisoformat(expected)
        candidates = {d for d in candidates if abs((d - expected_day).days) <= 21}
    return next(iter(candidates)).isoformat() if len(candidates) == 1 else None


def parse_stage_date(text: str, year: int, date_format: str = "dmy") -> str | None:
    """Extract the date from a route-table cell, with explicit locale."""
    match = DATE_SLASH.search(text)
    if match:
        a, b, y = map(int, match.groups())
        month, day = (a, b) if date_format == "mdy" else (b, a)
        try:
            d = dt.date(y, month, day)
            return d.isoformat() if d.year == year else None
        except ValueError:
            return None
    match = DATE_ISO.search(text)
    if match:
        try:
            d = dt.date(*map(int, match.groups()))
            return d.isoformat() if d.year == year else None
        except ValueError:
            return None
    return None


def parse_stage_schedule(html: str, year: int, date_format: str = "dmy") -> list[dict[str, Any]]:
    """Read a published organiser route table; no guessing missing/rest days.

    Designed for the ASO overall-route table, with loose header labels to
    tolerate CSS changes. The route is rejected if structural checks fail.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for table in soup.select("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headings = [norm_key(x.get_text(" ", strip=True)) for x in rows[0].find_all(["th", "td"], recursive=False)]
        try:
            stage_i = next(i for i, label in enumerate(headings) if "stage" in label or "etape" in label)
            date_i = next(i for i, label in enumerate(headings) if "date" in label or "jour" == label)
        except StopIteration:
            continue
        type_i = next((i for i, label in enumerate(headings) if "type" in label or "profile" in label), None)
        route_i = next((i for i, label in enumerate(headings) if "start" in label and "finish" in label or "depart" in label and "arrivee" in label), None)
        schedule = []
        for row in rows[1:]:
            cols = [normalize(x.get_text(" ", strip=True)) for x in row.find_all(["th", "td"], recursive=False)]
            if max(stage_i, date_i) >= len(cols):
                continue
            day = parse_stage_date(cols[date_i], year, date_format)
            if not day:
                continue
            stage_num = cols[stage_i]
            stage_type = cols[type_i] if type_i is not None and type_i < len(cols) else ""
            route = cols[route_i] if route_i is not None and route_i < len(cols) else ""
            if stage_num.isdigit():
                schedule.append({"kind": "stage", "number": int(stage_num),
                                 "date": day, "profile": stage_type, "route": route})
            elif "rest" in stage_type.casefold() or "repos" in stage_type.casefold() or "rest" in stage_num.casefold():
                schedule.append({"kind": "rest", "number": None, "date": day,
                                 "profile": "Rest Day", "route": route})
        if len(schedule) > len(candidates):
            candidates = schedule
    return candidates


def validate_stages(stages: list[dict[str, Any]], race: dict[str, Any]) -> tuple[bool, str]:
    expected = int(race.get("expected_stages", 2))
    numbered = [x["number"] for x in stages if x["kind"] == "stage"]
    dates = [x["date"] for x in stages]
    if len(numbered) < expected:
        return False, f"Only {len(numbered)} stages found, expected at least {expected}"
    if sorted(numbered) != list(range(1, len(numbered) + 1)):
        return False, "Missing or repeated stage numbers"
    if dates != sorted(set(dates)):
        return False, "Stage/rest dates are not unique and chronological"
    if any(dt.date.fromisoformat(d).year != race["year"] for d in dates):
        return False, "Some stage dates refer to the wrong edition"
    start = dt.date.fromisoformat(race["start_date"])
    if abs((dt.date.fromisoformat(dates[0]) - start).days) > 21:
        return False, "Stage schedule does not match configured race window"
    if (dt.date.fromisoformat(dates[-1]) - dt.date.fromisoformat(dates[0])).days > 35:
        return False, "Route span is implausibly long"
    return True, "OK"


def update_stage_schedule(race: dict[str, Any], result: dict[str, Any],
                          previous: dict[str, Any] | None,
                          getter: Callable[[str], str], checked: str) -> None:
    """Keep previously published days when official route pages are missing."""
    previous = previous or {}
    old_stages = previous.get("stages", [])
    if race.get("type") == "one_day":
        return
    if not race.get("stage_urls"):
        result["stages"] = old_stages
        result["stage_status"] = "unconfigured" if not old_stages else "stale"
        return
    problems = []
    for url in race["stage_urls"]:
        try:
            parsed = parse_stage_schedule(getter(url), race["year"], race.get("date_format", "dmy"))
            valid, why = validate_stages(parsed, race)
            if not valid:
                problems.append(f"{url}: {why}")
                continue
            if old_stages and len(parsed) < len(old_stages) * 0.7:
                problems.append(f"{url}: new schedule is unexpectedly shorter")
                continue
            result["stages"] = parsed
            result["race_days"] = [x["date"] for x in parsed if x["kind"] == "stage"]
            result["start_date"] = result["race_days"][0]
            result["end_date"] = result["race_days"][-1]
            result["stage_status"] = "published"
            result["stage_checked_at"] = checked
            result["stage_source_url"] = url
            if old_stages and old_stages != parsed:
                result["stage_changes_detected"] = True
            return
        except Exception as exc:
            problems.append(f"{url}: {type(exc).__name__}")
    result["stages"] = old_stages
    result["race_days"] = [x["date"] for x in old_stages if x.get("kind") == "stage"]
    result["stage_status"] = "stale" if old_stages else "unavailable"
    result["stage_warning"] = " | ".join(problems)[:300]
    if "end_date" in previous:
        result["end_date"] = previous["end_date"]


def fetch_html(url: str) -> str:
    # No attempts to bypass CAPTCHA, anti-bot protections or access controls.
    headers = {"User-Agent": "PelotonLeaguePublicPageReader/1.0 (+personal noncommercial cycling league)",
               "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}
    resp = requests.get(url, timeout=(10, 25), headers=headers, allow_redirects=True)
    resp.raise_for_status()
    if len(resp.content) > 4_000_000:
        raise ValueError("HTML page exceeds 4 MB limit")
    if "html" not in resp.headers.get("Content-Type", "text/html").lower():
        raise ValueError("The organiser returned non-HTML content")
    return resp.text


def next_interval_hours(start_date: str, now: dt.datetime) -> int | None:
    days_left = (dt.date.fromisoformat(start_date) - now.date()).days
    if days_left < -2:
        return None
    if days_left <= 2:
        return 12
    if days_left <= 14:
        return 24
    return 24 * 7


def source_status_after_failure(previous: dict[str, Any] | None, reason: str, checked: str,
                                published_year: int | None = None) -> dict[str, Any]:
    old = copy.deepcopy(previous or {})
    data = old.get("riders", [])
    if data:
        old["status"] = "stale"
    elif published_year is not None:
        old["status"] = "not_published"
    elif "edition" in reason.lower() or "only" in reason.lower():
        old["status"] = "not_published"
    else:
        old["status"] = "unavailable"
    old.setdefault("riders", [])
    old["checked_at"] = checked
    old["warning"] = reason[:350]
    if published_year is not None:
        old["source_edition_year"] = published_year
    return old


def scrape_race(race: dict[str, Any], previous: dict[str, Any] | None,
                getter: Callable[[str], str] = fetch_html,
                now: dt.datetime | None = None, force: bool = False) -> dict[str, Any]:
    now = now or utc_now()
    checked = iso(now)
    result: dict[str, Any] = {
        "id": race["id"], "name": race["name"], "year": race["year"],
        "type": race["type"], "organiser": race.get("organiser"),
        "start_date": race["start_date"], "race_days": [race["start_date"]] if race["type"] == "one_day" else [],
        "website": race["website"]
    }
    old_roster = (previous or {}).get("startlist", {})
    old_date = (previous or {}).get("start_date")
    if old_date and dt.date.fromisoformat(old_date).year == race["year"]:
        result["start_date"] = old_date
        if race["type"] == "one_day":
            result["race_days"] = [old_date]
    interval = next_interval_hours(result["start_date"], now)
    checked_before = parse_utc(old_roster.get("checked_at"))
    due = force or (interval is not None and (checked_before is None or
          (now - checked_before).total_seconds() >= interval * 3600))
    if not due:
        result["startlist"] = old_roster if old_roster else {"status": "not_published", "riders": []}
        if race.get("type") != "one_day":
            result["stages"] = (previous or {}).get("stages", [])
            result["stage_status"] = (previous or {}).get("stage_status", "not_checked")
            result["race_days"] = (previous or {}).get("race_days", [])
            result["end_date"] = (previous or {}).get("end_date")
        return result

    # Fetch official event page to gather a verified date candidate.
    try:
        homepage = getter(race["website"])
        candidate = parse_page_date(homepage, race["year"], race.get("date_format", "dmy"),
                                    expected=result["start_date"])
        result["date_source_checked_at"] = checked
        if candidate:
            result["date_candidate"] = candidate
            # A conflicting date must not silently move someone's draft deadline.
            if candidate == result["start_date"]:
                result["date_status"] = "confirmed_by_official_page"
            else:
                result["date_status"] = "change_requires_review"
        else:
            result["date_status"] = "retained_from_calendar"
    except Exception as exc:
        result["date_status"] = "retained_from_calendar"
        result["date_warning"] = f"Date page unavailable: {type(exc).__name__}"[:160]

    update_stage_schedule(race, result, previous, getter, checked)

    errors = []
    wrong_years = []
    for url in race.get("startlist_urls", []):
        try:
            page = getter(url)
            extracted = choose_roster(page)
            valid, reason = validate_roster(extracted, race, old_roster)
            if valid:
                result["startlist"] = {
                    "status": "published", "edition_year": race["year"],
                    "source_edition_year": race["year"], "method": extracted["method"],
                    "source_url": url, "checked_at": checked, "last_success_at": checked,
                    "riders": extracted["riders"], "count": len(extracted["riders"]),
                }
                old_riders = {norm_key(r["name"]) for r in old_roster.get("riders", [])}
                new_riders = {norm_key(r["name"]) for r in extracted["riders"]}
                if old_riders:
                    result["startlist"]["changes"] = {
                        "added": sorted(new_riders - old_riders),
                        "removed": sorted(old_riders - new_riders)
                    }
                return result
            errors.append(f"{url}: {reason}")
            if extracted["edition_year"] is not None and extracted["edition_year"] != race["year"]:
                wrong_years.append(extracted["edition_year"])
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:130]}")
        # Gentle delay between alternate official URLs; no brute forcing.
        if len(race.get("startlist_urls", [])) > 1:
            time.sleep(0.35)
    reason = " | ".join(errors)[:350] if errors else "No official start-list sources configured"
    published_year = wrong_years[0] if wrong_years else None
    result["startlist"] = source_status_after_failure(old_roster, reason, checked, published_year)
    return result


def run(config_file: str | Path, output_file: str | Path, now: dt.datetime | None = None,
        getter: Callable[[str], str] = fetch_html, force: bool = False) -> dict[str, Any]:
    now = now or utc_now()
    config = json.loads(Path(config_file).read_text(encoding="utf-8"))
    outfile = Path(output_file)
    try:
        previous_data = json.loads(outfile.read_text(encoding="utf-8"))
        if previous_data.get("schema_version") != 1:
            previous_data = {}
    except (FileNotFoundError, ValueError):
        previous_data = {}
    previous_by_id = {r["id"]: r for r in previous_data.get("races", [])}
    races = []
    for race in config["races"]:
        if race.get("enabled", True):
            races.append(scrape_race(race, previous_by_id.get(race["id"]), getter=getter,
                                     now=now, force=force))
    data = {"schema_version": 1, "generated_at": iso(now), "races": races}
    outfile.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write to prevent an interrupted update corrupting the feed.
    temp_path = outfile.with_name(outfile.name + ".tmp")
    temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp_path.replace(outfile)
    return data


def main() -> int:
    p = argparse.ArgumentParser(description="Peloton no-API official race scraper")
    p.add_argument("--config", default="races.json")
    p.add_argument("--output", default="data/latest.json")
    p.add_argument("--force", action="store_true", help="Ignore due-time interval; use for a first-run test")
    args = p.parse_args()
    data = run(args.config, args.output, force=args.force)
    for race in data["races"]:
        r = race["startlist"]
        print(f"{race['id']}: {r['status']} ({len(r.get('riders', []))} riders) "
              f"{r.get('warning', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())