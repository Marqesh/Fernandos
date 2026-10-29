# Peloton — 30 race league; historical validation before 2027

## Configuration

- `races_2026.json`: the **30 actual 2026 league events and dates** supplied by the user. This includes Volta à Figueira (14 February), UAE Tour (16–22 February), and 28 following races. Sources are restricted to public organiser websites. Every source is labelled as verified roster page, verified teams page, verified PDF index, or unverified candidate. Only **successful live extraction** counts as working.
- `races_2027_targets.json`: the same 30 **event identities** for 2027. No 2026 date or start list is copied across years. Only Paris–Roubaix and Tour de France have independently known 2027 dates and are marked active in this planning file. Others have a null date, no 2027-specific startlist URL, and an inactive status.
- `races.json` and `data/latest.json`: existing live production, still **only the two 2027 races**. Production is deliberately not replaced by historical tests.
- `.github/workflows/validate-2026.yml`: complete historical tests for 2026. The separate `startlists_2026.py` runner writes `data/history-2026.json` and `data/history-2026-diagnostics.json`.

## Extractor strategy

1. Fetch only the public organiser URL configured for a race. Reject HTTP errors, redirects to other hosts, access challenges and unexpectedly large files.
2. For HTML, use the known ASO-style parser, then team-heading/table parser. Follow at most three **same-organiser** public links to rider lists or official entry-list PDFs. Do not fetch results, and don't confuse women's, U23 or junior entries with Men's Elite.
3. For PDFs, use PDF text extraction (PyMuPDF) with year/category checks, bib numbers, rider names, national teams where possible. Never use OCR or guess missing riders.
4. Validate matching edition, sufficient rider and team counts, duplicates, and data integrity. Keep last validated riders as `stale` if a subsequent check fails. Unusable information remains `unavailable` with diagnostics.
5. A year-specific organiser list can be tested after a race has happened, using `--force` to bypass the ordinary date-based schedule; never use that as proof that archives will be available forever.

## Next 2027 phase

2027 race dates must be verified from official organiser/UCI calendars; 2026 dates must **not** be rolled forward automatically. Only after verified dates and source adapters exist should entries be enabled in the production `races.json` feed. If a website already shows 2026, do not publish its riders under 2027.

## Known limitations

- Only the race identities and 2026 dates are fully populated now. Most site-specific extractors still need a live successful test. This scaffold makes the testing measurable; it does not claim 30/30 historical startlists are available.
- World Championships Men Elite TT and Road Race share an organiser hub. The correct subevent must be identified by an explicitly labelled entry-list document; an unfiltered entry list must never be accepted for both races.
- Official historical websites may have replaced last year's roster with the following edition; a historical test can report `unavailable` even when the race had starters.
- No race results, Velogames, private league data, authentication or draft picks are modified by this workflow.