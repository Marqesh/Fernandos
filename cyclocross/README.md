# Cyclocross trial for Peloton (2026-27)

This directory is isolated on branch `feature/cyclocross-2026-27`. It does not alter road cycling race data, leagues, user accounts, picks or results.

**Scope:** 26 Men Elite race fixtures spanning **5 November 2026 through 31 January 2027**: 7 Superprestige rounds, 12 UCI Cyclo-cross World Cups, 5 X²O Badkamers Trofee races, the UEC European Championships, and the 2027 UCI World Championships in Ostend. Original test fixtures and verified riders remain untouched.

**Calendar verification:** World Cup: https://www.ucicyclocrossworldcup.com/en/news/discover-the-calendar-of-the-2026-2027-uci-cyclo-cross-world-cup ; Superprestige: https://www.superprestigecyclocross.be/en/news/discover-the-calendar-for-the-2026-2027-telenet-superprestige ; X²O: https://x2otrofee.be/ ; Worlds: https://www.ostend2027.com/en . 

**Active checking window:** fetch source pages from 21 days before a race through 3 days after. Outside that window, carry forward only previously validated same-edition data; otherwise show `not_published`. This avoids wasteful checks of future/unpublished pages and preserves a historical roster.

**Source policy:** only public organiser pages and directly linked, same-host official entry/startlist documents. No ProCyclingStats, no FirstCycling scraping, no paid API, no automated bypass of access restrictions. Do not scrape results.

**Strict validation:** edition/date, Men Elite category, bib and UCI ID where supplied, and minimum rider count. Do not reuse Superprestige Middelkerke's **7 February 2026** PDF for the **5 November 2026** event. Official UEC Zeddam *Entry lists* are provisional, not confirmed starters.

**Output:** `cyclocross/data/latest.json` and `cyclocross/data/diagnostics.json`. States: `not_published`, `provisional`, `published`, `stale`. Missing lists do not indicate scraping code failure.

The **scheduled job is on the default branch**, checking out and updating the CX feature branch. The normal Peloton road GitHub workflows remain unchanged. The new Site branch should consume only:

`https://raw.githubusercontent.com/Marqesh/Fernandos/feature/cyclocross-2026-27/cyclocross/data/latest.json`

Do not deploy before verifying race identity, category and sufficient rider counts.

**Important:** Additional organiser pages are discovery candidates, not guaranteed start-list URLs. A valid date in the calendar does not mean start-list extraction has been verified for that organiser. Source URLs may be amended as official entry lists are published. The World Championships start date refers specifically to the Men Elite competition on 31 January, not the three-day event opening on 29 January.
