# PELOTON — Cyclocross 2026–27 isolated Site branch test

**Apply ONLY to a NEW preview/testing branch of the existing Peloton Site. Do not publish these changes to the current road-cycling production Site.**

GitHub repository: https://github.com/Marqesh/Fernandos/tree/feature/cyclocross-2026-27/cyclocross

Read-only feed: https://raw.githubusercontent.com/Marqesh/Fernandos/feature/cyclocross-2026-27/cyclocross/data/latest.json

Use the exported functions in `cyclocross/site_integration.js` (or implement their equivalent in the Site's existing frontend). **Do not recreate or migrate the Site database.**

## Show in the cyclocross preview

- Four Men Elite fixtures: Middelkerke 5 November, Zeddam European Championships 8 November, Niel 11 November and Ostrava World Cup 27 November 2026.
- Separate sport/season selector: `Cyclocross 2026–27 (TEST)`. Do not merge or overwrite the road race calendar.
- Race status, organiser source, category, checked timestamp and riders, with UCI ID and nationality, and bib only when published.
- Explicit statuses: `published` means validated final start list; `provisional` means organiser entry list only; `not_published` means pending; `stale` means previous validated list preserved due to failure.
- Do not allow a provisional list to silently overwrite a final one or automatically unlock the live draft. Support manual review/testing with provisional riders on the TEST branch only.
- Never scrape or infer results; never invent absent riders or bib numbers.
- The GitHub cyclocross source is updated at 07:17 and 19:17 UTC daily. The Site may refresh on load and every 30 minutes when open. Do not start another browser-side scraper.
- Preserve all existing authentication, users, league membership, standings, scoring, snake draft order, prediction features and private saved picks. A Site test branch should use an isolated test namespace for any new records.

Before publishing to a **branch preview**, verify that the Zeddam entry list shows 45 provisional Men Elite riders, no guessed bibs, and all three other races remain pending until validated. Do not publish to production.
