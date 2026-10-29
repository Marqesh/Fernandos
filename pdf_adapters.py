"""Layout-aware START-LIST-ONLY PDF adapters for named organisers.

Reads only public start-list PDFs. Rejects results, other event categories,
unknown bibs and wrong-edition documents.
"""
from __future__ import annotations

import re
import unicodedata

EUROPEAN_NATIONS = {
    'Albania', 'Andorra', 'Armenia', 'Austria', 'Azerbaijan', 'Belgium',
    'Bosnia and Herzegovina', 'Bulgaria', 'Croatia', 'Cyprus', 'Czech Republic',
    'Czechia', 'Denmark', 'Estonia', 'Finland', 'France', 'Georgia', 'Germany',
    'Great Britain', 'Greece', 'Hungary', 'Iceland', 'Ireland', 'Israel', 'Italy',
    'Kosovo', 'Latvia', 'Lithuania', 'Luxembourg', 'Malta', 'Moldova', 'Monaco',
    'Montenegro', 'Netherlands', 'North Macedonia', 'Norway', 'Poland',
    'Portugal', 'Romania', 'Russia', 'Serbia', 'Slovakia', 'Slovenia', 'Spain',
    'Sweden', 'Switzerland', 'Turkey', 'Turkiye', 'Ukraine', 'United Kingdom',
}
NATION_MAP = {
    unicodedata.normalize('NFKD', country).encode('ascii', 'ignore').decode().casefold(): country
    for country in EUROPEAN_NATIONS
}
SWISS_TEAM_RE = re.compile(r"^([A-Z0-9]{3})\s+(.{5,90}?)\s+([A-Z]{3})$")
SWISS_RIDER_RE = re.compile(r"^(\d{1,3})\s+(?:\*\s*)?(.+?)\s+(1\d{10})$")
UEC_RIDER_RE = re.compile(r"^(\d{1,3})\s+(.{4,80})$")
NAME_CHARS = re.compile(r"^[A-Za-zÀ-ÿ .,'’()\-]+$")
INVALID_NAME = re.compile(
    r"\b(?:sport director|ranking|results?|finish|time|points|start list|riders|starters|page of|classification)\b",
    re.I
)

def normalized(s: str) -> str:
    return ' '.join(s.replace('\u00a0', ' ').split())

def is_name(s: str) -> bool:
    s = normalized(s)
    return (
        4 <= len(s) <= 80
        and len(s.split()) >= 2
        and bool(NAME_CHARS.fullmatch(s))
        and not INVALID_NAME.search(s)
    )

def visual_column_lines(document, *, tolerance: float = 3.0):
    """Group PDF words by side and by y coordinate to separate two columns."""
    columns = []
    for page in document:
        split = page.rect.width / 2
        words = page.get_text('words')
        for left, right in ((0, split), (split, page.rect.width + 1)):
            subset = [w for w in words if left <= (w[0] + w[2]) / 2 < right]
            subset.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
            rows = []
            for word in subset:
                y = (word[1] + word[3]) / 2
                if rows and abs(y - rows[-1]['anchor']) <= tolerance:
                    rows[-1]['words'].append(word)
                else:
                    rows.append({'anchor': y, 'words': [word]})
            columns.append([
                normalized(' '.join(w[4] for w in sorted(row['words'], key=lambda a: a[0])))
                for row in rows
            ])
    return columns

def parse_uec_men_elite_rr(document):
    """UEC PDF: separate national-team headings and bib/name in two columns."""
    fulltext = ' '.join(page.get_text('text') for page in document)
    if not re.search(r'(?i)\bmen\s+elite\s+road\s+race\s*,?\s*start\s*list', normalized(fulltext)):
        return [], {'reason': 'uec_wrong_event_or_not_startlist', 'recognized_nations': 0}
    found, countries = [], set()
    for column in visual_column_lines(document):
        nation = None
        for text in column:
            key = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().casefold()
            if key in NATION_MAP:
                nation = NATION_MAP[key]
                countries.add(nation)
                continue
            m = UEC_RIDER_RE.fullmatch(text)
            if not m or nation is None:
                continue
            bib, name = int(m[1]), normalized(m[2])
            if 1 <= bib <= 300 and is_name(name):
                found.append({'bib': bib, 'name': name, 'team': nation})
    return found, {'recognized_nations': len(countries), 'strategy': 'uec_visual_columns'}

def parse_tds_startlist(document):
    """Tour de Suisse PDF: team-code headings, bib/name and eleven-digit UCI ID."""
    first = normalized(document[0].get_text('text')) if len(document) else ''
    if not re.search(r'(?i)\btour de suisse\b', first) or not re.search(r'(?i)\bstarters?\s+list\b', first):
        return [], {'reason': 'tds_wrong_document_or_not_starters_list', 'team_count': 0}
    strategies = {
        'tds_full_text': [
            normalized(t) for page in document
            for t in page.get_text('text', sort=False).splitlines()
        ],
        'tds_visual_columns': [v for col in visual_column_lines(document) for v in col],
    }
    variants = {}
    for method, lines in strategies.items():
        team, riders, teams = None, [], set()
        for line in lines:
            m = SWISS_TEAM_RE.fullmatch(line)
            if m and m[3].isalpha() and m[2].upper() == m[2]:
                team = normalized(m[2])
                teams.add(team)
                continue
            rider = SWISS_RIDER_RE.fullmatch(line)
            if rider and team:
                bib, name = int(rider[1]), normalized(rider[2])
                if 1 <= bib <= 300 and is_name(name):
                    riders.append({'bib': bib, 'name': name, 'team': team})
        variants[method] = (riders, len(teams))
    method = max(variants, key=lambda k: (len(variants[k][0]), variants[k][1]))
    return variants[method][0], {
        'strategy': method, 'team_count': variants[method][1],
        'variant_counts': {k: len(v[0]) for k, v in variants.items()}
    }
