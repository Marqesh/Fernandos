import copy
import datetime as dt
import json
from pathlib import Path

from scraper import (choose_roster, parse_page_date, scrape_race, validate_roster,
                     source_status_after_failure, run, next_interval_hours)

FIXTURE = Path(__file__).parent / "fixtures"
CONFIG = Path(__file__).parent.parent / "races.json"
RACE_2027 = json.loads(CONFIG.read_text(encoding="utf-8"))["races"][0]
RACE_2026 = next(x for x in json.loads(CONFIG.read_text(encoding="utf-8"))["races"] if x["year"] == 2026)
NOW = dt.datetime(2026, 10, 28, 18, 0, tzinfo=dt.timezone.utc)


def fixture(name):
    return (FIXTURE / name).read_text(encoding="utf-8")


def get_html(url):
    return "<html><body><h1>04/11/2027</h1></body></html>" if url.endswith("/en") else fixture("aso_2026.html")


def test_extract_known_aso_semantic_fixture():
    r = choose_roster(fixture("aso_2026.html"))
    assert r["edition_year"] == 2026
    assert r["method"] == "semantic_html"
    assert len(r["riders"]) == 21
    assert r["riders"][0] == {"bib": 1, "name": "MATHIEU VAN DER POEL", "team": "ALPECIN-PREMIER TECH"}
    assert r["riders"][12]["name"] == "ANTÓNIO TOMAS MORGADO"
    assert validate_roster(r, RACE_2026)[0]


def test_layout_css_changes_not_a_problem():
    r = choose_roster(fixture("aso_redesign.html"))
    assert r["edition_year"] == 2026
    assert len(r["riders"]) == 14
    assert r["method"] == "semantic_html"
    assert validate_roster(r, RACE_2026)[0]


def test_wrong_edition_rejected_even_if_homepage_says_2027():
    race = copy.deepcopy(RACE_2027)
    out = scrape_race(race, None, getter=get_html, now=NOW, force=True)
    assert out["start_date"] == "2027-04-11"
    assert out["date_status"] == "confirmed_by_official_page"
    assert out["startlist"]["status"] == "not_published"
    assert out["startlist"]["source_edition_year"] == 2026
    assert out["startlist"]["riders"] == []


def test_unknown_edition_rejected_without_guessing():
    page = fixture("aso_2026.html").replace("2026 Start list", "Start list").replace("Starters list Paris-Roubaix 2026", "Paris Roubaix")
    r = choose_roster(page)
    assert r["edition_year"] is None
    assert validate_roster(r, RACE_2026)[0] is False


def test_existing_roster_preserved_when_website_fails():
    old = {"id": "paris-roubaix-2027", "startlist": {
        "status": "published", "edition_year": 2027,
        "last_success_at": "2027-04-06T10:00:00Z", "riders": [
            {"bib": x, "name": f"Rider Name {x}", "team": "TEAM A"} for x in range(1, 11)]}}
    def fail(url):
        raise ConnectionError("organiser unavailable")
    out = scrape_race(RACE_2027, old, getter=fail, now=NOW, force=True)
    assert out["startlist"]["status"] == "stale"
    assert len(out["startlist"]["riders"]) == 10
    assert out["startlist"]["last_success_at"] == "2027-04-06T10:00:00Z"


def test_large_count_drop_rejected():
    prev = {"riders": [{"bib": x, "name": f"Rider Name {x}", "team": "A"} for x in range(100)]}
    r = choose_roster(fixture("aso_2026.html"))
    good, reason = validate_roster(r, RACE_2026, prev)
    assert not good and "shrank" in reason


def test_duplicates_invalid():
    r = choose_roster(fixture("aso_2026.html"))
    r["riders"][1]["bib"] = 1
    good, reason = validate_roster(r, RACE_2026)
    assert not good and "Repeated bib" in reason


def test_structured_json_fallback():
    rows = [{"bib": i, "name": f"Name Rider {i}", "team": "TEAM X" if i < 6 else "TEAM Y"} for i in range(1, 13)]
    html = "<h1>2026 Start list</h1><script type='application/json'>" + json.dumps({"riders": rows}) + "</script>"
    r = choose_roster(html)
    assert r["method"] == "embedded_json"
    assert len(r["riders"]) == 12
    assert validate_roster(r, RACE_2026)[0]


def test_table_fallback():
    table = "<h1>2026 Start list</h1><table><tr><th>Bib</th><th>Rider</th><th>Team</th></tr>"
    for n in range(1, 13):
        table += f"<tr><td>{n}</td><td>First Last {n}</td><td>TEAM X</td></tr>" if n < 6 else f"<tr><td>{n}</td><td>First Last {n}</td><td>TEAM Y</td></tr>"
    r = choose_roster(table + "</table>")
    assert r["method"] == "html_table" and len(r["riders"]) == 12
    assert validate_roster(r, RACE_2026)[0]


def test_schedule_daily_and_weekly():
    assert next_interval_hours("2027-04-11", NOW) == 7 * 24
    assert next_interval_hours("2026-10-30", NOW) == 12
    assert next_interval_hours("2026-11-03", NOW) == 24
    assert next_interval_hours("2026-10-20", NOW) is None


def test_date_parser_no_cross_year_or_multiple_dates():
    assert parse_page_date("<p>04/11/2027</p><span>Winner 2026</span>", 2027, "mdy", "2027-04-11") == "2027-04-11"
    assert parse_page_date("<p>04/11/2027</p><p>04/12/2027</p>", 2027, "mdy", "2027-04-11") is None
    assert parse_page_date("<p>11/04/2027</p>", 2027, "dmy", "2027-04-11") == "2027-04-11"


def test_end_to_end_round_trip_and_persistence(tmp_path):
    output = tmp_path / "data.json"
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"races": [{**RACE_2026, "enabled": True}]}), encoding="utf-8")
    def getter(url):
        return fixture("aso_2026.html")
    d1 = run(config_path, output, now=dt.datetime(2026, 4, 12, tzinfo=dt.timezone.utc), getter=getter)
    assert len(d1["races"][0]["startlist"]["riders"]) == 21
    def fail(url):
        raise ConnectionError("network")
    d2 = run(config_path, output, now=dt.datetime(2026, 4, 13, tzinfo=dt.timezone.utc), getter=fail, force=True)
    assert d2["races"][0]["startlist"]["status"] == "stale"
    assert len(d2["races"][0]["startlist"]["riders"]) == 21
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 1


def test_tour_de_france_2027_route_21_stages_and_three_rest_days():
    from scraper import parse_stage_schedule, validate_stages
    tour = json.loads(CONFIG.read_text(encoding="utf-8"))["races"][1]
    stages = parse_stage_schedule(fixture("aso_tdf_route_2027.html"), 2027, "mdy")
    assert validate_stages(stages, tour) == (True, "OK")
    assert len([x for x in stages if x["kind"] == "stage"]) == 21
    assert len([x for x in stages if x["kind"] == "rest"]) == 3
    assert stages[0]["date"] == "2027-07-02"
    assert stages[-1]["date"] == "2027-07-25"
    assert stages[3]["kind"] == "rest"


def test_tour_stage_schedule_preserved_on_source_failure():
    tour = json.loads(CONFIG.read_text(encoding="utf-8"))["races"][1]
    stages = __import__("scraper").parse_stage_schedule(fixture("aso_tdf_route_2027.html"), 2027, "mdy")
    old = {"stages": stages, "stage_status": "published", "race_days": [x["date"] for x in stages if x["kind"] == "stage"],
           "end_date": "2027-07-25", "startlist": {"riders": [], "status": "not_published"}}
    def fail(url):
        raise ConnectionError("connection blocked")
    output = scrape_race(tour, old, getter=fail, now=NOW, force=True)
    assert output["stage_status"] == "stale"
    assert len(output["race_days"]) == 21
    assert output["stages"] == stages


def test_tour_stage_schedule_populates_race_days_even_without_roster():
    tour = json.loads(CONFIG.read_text(encoding="utf-8"))["races"][1]
    def getter(url):
        if url.endswith("overall-route"):
            return fixture("aso_tdf_route_2027.html")
        return "<html><body><h1>Tour de France 2027</h1><p>Starters will be announced</p></body></html>"
    output = scrape_race(tour, None, getter=getter, now=NOW, force=True)
    assert output["stage_status"] == "published"
    assert len(output["race_days"]) == 21
    assert output["startlist"]["status"] == "not_published"


def test_health_monitor_warns_only_when_race_is_urgent():
    from monitor import check_health
    feed = {"races": [
        {"id": "r1", "start_date": "2027-04-11", "type": "one_day", "year": 2027,
         "startlist": {"status": "not_published", "riders": []}},
    ]}
    assert not check_health(feed, dt.date(2027, 4, 1))
    problems = check_health(feed, dt.date(2027, 4, 10))
    assert len(problems) == 1 and "no published" in problems[0]
    feed["races"][0]["startlist"] = {"status": "published", "edition_year": 2027, "riders": [{"name": "Test Racer"}]}
    assert not check_health(feed, dt.date(2027, 4, 10))


def test_full_size_175_rider_roster_fixture():
    from scraper import choose_roster, validate_roster
    html = ['<h1>2026 Start list</h1>']
    for team_no in range(25):
        html.append(f'<h3>RACING TEAM {team_no + 1}</h3><ul>')
        for r in range(7):
            bib = team_no * 10 + r + 1
            html.append(f'<li>{bib} RIDER TEST {bib}</li>')
        html.append('</ul>')
    roster = choose_roster(''.join(html))
    assert len(roster['riders']) == 175
    assert validate_roster(roster, RACE_2026)[0]