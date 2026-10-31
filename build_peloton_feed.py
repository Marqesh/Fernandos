"""Build one read-only Peloton Site feed from the existing GitHub scrapers.

Inputs:
  - races_2027_targets.json: exact 30 league races and confirmed dates
  - data/watch-2027.json: organiser availability, edition-validated rosters
  - data/latest.json: verified ASO race dates/stages and its rosters

This module NEVER infers 2027 dates from historical races or copies 2026
starters. No local Site data or user information is accessed or written.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ALIASES = {
    'figueira-champions-classic': ['Volta a Figueira', 'Volta a Figueira Champions Classic'],
    'uae-tour': ['UAE Tour'],
    'volta-ao-algarve': ['Volta ao Algarve'],
    'omloop-het-nieuwsblad': ['Omloop', 'Omloop Het Nieuwsblad'],
    'kuurne-brussel-kuurne': ['Kurne Brussels Kurne', 'Kuurne Brussels Kuurne'],
    'strade-bianche': ['Strade Bianche'],
    'paris-nice': ['Paris Nice'],
    'tirreno-adriatico': ['Tirreno Adriatico'],
    'milano-sanremo': ['Milano Sanremo', 'Milan San Remo'],
    'volta-a-catalunya': ['Volta Catalunia', 'Volta a Catalunya'],
    'e3-saxo-classic': ['E3 Saxo Classic'],
    'ronde-van-vlaanderen': ['Ronde Van Vlanderen', 'Tour of Flanders'],
    'itzulia-basque-country': ['Itzulia Basque Country', 'Tour of the Basque Country'],
    'paris-roubaix': ['Paris Roubaix'],
    'amstel-gold-race': ['Ametel Gold Race', 'Amstel Gold Race'],
    'la-fleche-wallonne': ['Fleche Wallonie', 'La Fleche Wallonne'],
    'liege-bastogne-liege': ['Liege Bastogne Liege'],
    'tour-de-romandie': ['Volta Romandia', 'Tour de Romandie'],
    'giro-ditalia': ['Giro d Italia', 'Giro dItalia'],
    'tour-auvergne-rhone-alpes': ['Criterium Dauphine', 'Criterium du Dauphine',
                                  'Tour Auvergne Rhone Alpes'],
    'tour-de-suisse': ['Tour de Suisse'],
    'tour-de-france': ['Tour de France'],
    'clasica-san-sebastian': ['Classica San Sebastian', 'Clasica San Sebastian'],
    'tour-de-pologne': ['Tour de Pologne'],
    'la-vuelta': ['La Vuelta', 'Vuelta a Espana'],
    'gp-montreal': ['Grand Prix Cycliste de Montreal', 'GP Montreal'],
    'worlds-men-elite-itt': ['Worlds TT ME', 'World Championships Time Trial Men Elite'],
    'worlds-men-elite-rr': ['Worlds Road Race', 'World Championships Men Elite Road Race'],
    'european-championships-me-rr': ['European Championships', 'European Championships ME Road Race'],
    'il-lombardia': ['Il Lombardia', 'Giro di Lombardia'],
}

SOURCE_STATUS_TEXT = {
    'older_edition': 'The organiser still shows an older edition; no 2027 riders imported',
    'page_not_available': 'The configured page is unavailable; no 2027 riders imported',
    'awaiting_2027_startlist': 'The 2027 start list has not been verified',
    'event_page_pending': 'The organiser has not provided a verified 2027 event start-list page',
    'source_error': 'The organiser could not be reached at the last check',
    'source_restricted': 'The organiser restricts automated access',
    'parser_needed': 'A 2027 source was found, but its roster format needs validation',
    'validation_failed': 'The downloaded list did not pass race/edition validation',
    'last_verified_snapshot': 'Previously verified information is cached',
    'confirmed_2027': 'An official 2027 rider list has been verified',
}


def _load_json(path: Path) -> dict:
    with path.open(encoding='utf-8') as f:
        content = json.load(f)
    if not isinstance(content, dict):
        raise ValueError(f'Expected a JSON object at {path}')
    return content


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _safe_website(url: str | None, year: int) -> str | None:
    """Do not link the future event to an explicitly 2026-only page."""
    if not isinstance(url, str) or not url.startswith('https://'):
        return None
    u = urlparse(url)
    if not u.hostname or u.username or u.password:
        return None
    if re.search(r'(?<!\d)20\d{2}(?!\d)', (u.path or '') + '?' + (u.query or '')):
        years = {int(y) for y in re.findall(r'(?<!\d)(20\d{2})(?!\d)', u.path + '?' + u.query)}
        if years and year not in years:
            return f'https://{u.hostname}/'
    return url


def _valid_riders(roster: dict, year: int) -> bool:
    if not isinstance(roster, dict):
        return False
    if roster.get('status') != 'published' or roster.get('edition_year') != year:
        return False
    riders = roster.get('riders')
    if not isinstance(riders, list) or len(riders) < 10:
        return False
    names = []
    for r in riders:
        if not isinstance(r, dict) or not isinstance(r.get('name'), str) or not r['name'].strip():
            return False
        if not isinstance(r.get('team'), str) or not r['team'].strip():
            return False
        names.append(r['name'].casefold().strip())
    return len(names) == len(set(names))


def _validated_stage_data(prod: dict, year: int) -> tuple[list, list, str]:
    if prod.get('year') != year or prod.get('stage_status') not in ('published', 'stale'):
        return [], [], 'not_published'
    stages = prod.get('stages') or []
    if not isinstance(stages, list) or not stages:
        return [], [], 'not_published'
    race_days = []
    numbers = []
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get('date'), str):
            return [], [], 'not_published'
        if not stage['date'].startswith(str(year) + '-'):
            return [], [], 'not_published'
        if stage.get('kind') == 'stage':
            race_days.append(stage['date'])
            numbers.append(stage.get('number'))
        elif stage.get('kind') != 'rest':
            return [], [], 'not_published'
    if numbers != list(range(1, len(numbers) + 1)):
        return [], [], 'not_published'
    if prod.get('type') == 'grand_tour' and len(numbers) != 21:
        return [], [], 'not_published'
    return stages, race_days, prod['stage_status']


def build_feed(targets: dict, watch: dict, production: dict) -> dict:
    year = targets.get('season')
    if year != 2027 or watch.get('year') != 2027:
        raise ValueError('Site feed currently supports only the 2027 edition')
    catalog = targets.get('races')
    if not isinstance(catalog, list) or len(catalog) != 30:
        raise ValueError('The configured league calendar must contain exactly 30 races')
    watch_records = watch.get('races') or []
    prod_records = production.get('races') or []
    if not isinstance(watch_records, list) or not isinstance(prod_records, list):
        raise ValueError('Invalid source feeds')
    watched = {r['id']: r for r in watch_records if isinstance(r, dict) and isinstance(r.get('id'), str)}
    official = {r['id']: r for r in prod_records if isinstance(r, dict) and isinstance(r.get('id'), str)}
    if len(watched) != len(watch_records) or len(official) != len(prod_records):
        raise ValueError('Duplicate or missing IDs in upstream race feeds')
    output = []
    used_ids = set()
    for t in catalog:
        key, rid = t['key'], t['id']
        if rid in used_ids or t.get('year') != year or not rid.endswith('-2027'):
            raise ValueError(f'Invalid or repeated target race ID: {rid}')
        used_ids.add(rid)
        w, p = watched.get(rid, {}), official.get(rid, {})
        if w and w.get('year') != year:
            raise ValueError(f'Wrong-year watcher record: {rid}')
        if p and p.get('year') != year:
            raise ValueError(f'Wrong-year production record: {rid}')
        # The planning catalog owns future-year dates. The 2026 history is never referenced.
        date = t.get('start_date')
        date_status = t.get('date_status', 'unconfirmed')
        if date is not None and (not isinstance(date, str) or not date.startswith('2027-')):
            raise ValueError(f'Invalid 2027 date: {rid}')
        if p and date and p.get('start_date') and p['start_date'] != date:
            # Divergent official dates need manual review; never alter draft deadlines.
            date_status = 'change_requires_review'
        original_roster = None
        for candidate in (p.get('startlist'), w.get('startlist')):
            if _valid_riders(candidate or {}, year):
                original_roster = candidate
                break
        avail = w.get('availability', 'not_checked')
        if original_roster:
            roster = {**original_roster, 'count': len(original_roster['riders']), 'edition_year': year}
            availability = 'confirmed_2027'
        else:
            status = 'not_published'
            roster = {
                'status': status,
                'edition_year': None,
                'riders': [],
                'count': 0,
                'checked_at': (w.get('startlist') or {}).get('checked_at') or
                              (p.get('startlist') or {}).get('checked_at'),
                'warning': SOURCE_STATUS_TEXT.get(avail, '2027 start list not verified'),
            }
            availability = avail
        stages, race_days, stage_status = _validated_stage_data(p, year)
        if not race_days and date and t.get('type') == 'one_day':
            race_days = [date]
        url = _safe_website(t.get('website') or w.get('website') or p.get('website'), year)
        aliases = list(dict.fromkeys([t['name'], *ALIASES.get(key, [])]))
        output.append({
            'id': rid,
            'key': key,
            'name': t['name'],
            'aliases': aliases,
            'year': year,
            'type': t['type'],
            'organiser_family': t.get('organiser_family'),
            'website': url,
            'start_date': date,
            'end_date': t.get('end_date'),
            'date_status': date_status,
            'race_days': race_days,
            'startlist': roster,
            'startlist_availability': availability,
            'startlist_source': roster.get('source_url') if original_roster else None,
            'stages': stages,
            'stage_status': stage_status,
            'watch_checked_at': (w.get('startlist') or {}).get('checked_at'),
            'production_checked_at': (p.get('startlist') or {}).get('checked_at'),
            'import_mode': 'read_only',
        })
    if len(ALIASES) != len(output) or set(ALIASES) != {x['key'] for x in output}:
        raise ValueError('Race aliases must cover all 30 targets without extra keys')
    return {
        'schema_version': 1,
        'feed_revision': 2,
        'season': year,
        'generated_at': _now(),
        'import_mode': 'read_only',
        'source_generated_at': {
            'production': production.get('generated_at'),
            'watchlist': watch.get('generated_at'),
        },
        'summary': {
            'configured_races': len(output),
            'verified_startlists': sum(r['startlist']['status'] == 'published' for r in output),
            'verified_dates': sum(bool(r['start_date']) and r['date_status'] == 'date_verified' for r in output),
            'published_stage_schedules': sum(r['stage_status'] == 'published' for r in output),
        },
        'races': output,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--targets', default='races_2027_targets.json')
    parser.add_argument('--watch', default='data/watch-2027.json')
    parser.add_argument('--production', default='data/latest.json')
    parser.add_argument('--output', default='data/peloton-feed.json')
    args = parser.parse_args()
    feed = build_feed(_load_json(Path(args.targets)), _load_json(Path(args.watch)),
                      _load_json(Path(args.production)))
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(feed, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Peloton read-only feed: {feed['summary']['configured_races']} races, "
          f"{feed['summary']['verified_startlists']} verified startlists, "
          f"{feed['summary']['verified_dates']} confirmed dates")


if __name__ == '__main__':
    main()
