# PELOTON — Cyclocross 2026–27 isolated Site branch test

**Apply ONLY to a NEW preview/testing branch of the existing Peloton Site. Do not publish these changes to the current road-cycling production Site.**

GitHub repository: https://github.com/Marqesh/Fernandos/tree/feature/cyclocross-2026-27/cyclocross

Read-only feed: https://raw.githubusercontent.com/Marqesh/Fernandos/feature/cyclocross-2026-27/cyclocross/data/latest.json

Use the exported functions in `cyclocross/site_integration.js` (or implement their equivalent in the Site's existing frontend). **Do not recreate or migrate the Site database.**

## Show in the cyclocross preview

- **26 Men Elite fixtures** from 5 November 2026 to 31 January 2027, across Superprestige, UCI World Cup, X²O Trofee, UEC Europeans and the **Ostend 2027 World Championships Men Elite**. Build the calendar dynamically from the GitHub feed rather than hardcoding four races. Group by month (November / December / January), sorting by actual ISO race date.
- Separate sport/season selector: `Cyclocross 2026–27 (TEST)`. Do not merge or overwrite the road race calendar.
- Race status, organiser source, category, checked timestamp and riders, with UCI ID and nationality, and bib only when published.
- Explicit statuses: `published` means validated final start list; `provisional` means organiser entry list only; `not_published` means pending; `stale` means previous validated list preserved due to failure.
- Do not allow a provisional list to silently overwrite a final one or automatically unlock the live draft. Support manual review/testing with provisional riders on the TEST branch only.
- Never scrape or infer results; never invent absent riders or bib numbers.
- The GitHub cyclocross source is updated at 07:17 and 19:17 UTC daily. The Site may refresh on load and every 30 minutes when open. Do not start another browser-side scraper.
- Preserve all existing authentication, users, league membership, standings, scoring, snake draft order, prediction features and private saved picks. A Site test branch should use an isolated test namespace for any new records.

Before publishing to a **branch preview**, verify the feed contains **26 races** and its last race is Ostend Men Elite on **31 January 2027**. Middelkerke should show 46 confirmed starters (from the official PDF), Zeddam 45 provisional riders (no invented bibs), and all others should stay pending until independently verified. Check 2027 races use `year: 2027`, not 2026. Do not publish to road-cycling production.


The daily background scraper checks source websites only in a monitoring window around each race (21 days before through 3 days after), while preserving previously verified historical rosters. Keep unknown rosters unavailable in the draft until a verified final list arrives.
