# Cyclocross trial for Peloton (2026-27)

This directory is isolated on branch `feature/cyclocross-2026-27`. It does not alter road cycling race data, leagues, user accounts, picks or results.

**Scope:** four Men Elite races: Middelkerke (5 Nov), Zeddam European Championships (8 Nov), Niel (11 Nov), and World Cup Ostrava (27 Nov), all in 2026.

**Source policy:** only public organiser pages and directly linked, same-host official entry/startlist documents. No ProCyclingStats, no FirstCycling scraping, no paid API, no automated bypass of access restrictions. Do not scrape results.

**Strict validation:** edition/date, Men Elite category, bib and UCI ID where supplied, and minimum rider count. Do not reuse Superprestige Middelkerke's **7 February 2026** PDF for the **5 November 2026** event. Official UEC Zeddam *Entry lists* are provisional, not confirmed starters.

**Output:** `cyclocross/data/latest.json` and `cyclocross/data/diagnostics.json`. States: `not_published`, `provisional`, `published`, `stale`. Missing lists do not indicate scraping code failure.

The **scheduled job is on the default branch**, checking out and updating the CX feature branch. The normal Peloton road GitHub workflows remain unchanged. The new Site branch should consume only:

`https://raw.githubusercontent.com/Marqesh/Fernandos/feature/cyclocross-2026-27/cyclocross/data/latest.json`

Do not deploy before verifying race identity, category and sufficient rider counts.
