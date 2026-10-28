"""Deterministic, no-AI feed health checker for GitHub Actions failure alerts."""
import argparse
import datetime as dt
import json
from pathlib import Path


def check_health(feed: dict, today: dt.date | None = None) -> list[str]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    problems = []
    for race in feed.get("races", []):
        try:
            days = (dt.date.fromisoformat(race["start_date"]) - today).days
        except (KeyError, ValueError):
            problems.append(f"{race.get('id', 'unknown race')}: invalid start_date")
            continue
        if days < -2:
            continue
        roster = race.get("startlist", {})
        if roster.get("status") == "published" and roster.get("edition_year") != race.get("year"):
            problems.append(f"{race['id']}: published wrong-edition riders!")
        if 0 <= days <= 2 and not (roster.get("status") == "published" and roster.get("riders")):
            problems.append(f"{race['id']}: {days} day(s) before race but no published, verified startlist ({roster.get('status', 'unknown')})")
        if race.get("type") != "one_day" and 0 <= days <= 14 and not race.get("race_days"):
            problems.append(f"{race['id']}: no verified stage dates within 14 days of start")
    return problems


def main():
    arg = argparse.ArgumentParser()
    arg.add_argument("file", nargs="?", default="data/latest.json")
    args = arg.parse_args()
    feed = json.loads(Path(args.file).read_text(encoding="utf-8"))
    problems = check_health(feed)
    if problems:
        for problem in problems:
            print(f"::error::{problem}")
        raise SystemExit(1)
    print("No urgent race-data issues detected")


if __name__ == "__main__":
    main()