# Peloton race data — free, no cycling API

A self-checking, **unattended** importer from public organiser pages to a public static JSON file. Intended for the existing **Peloton · Cycling League** Site.

**Status: working offline prototype; live organiser HTTP access and ChatGPT Site integration still need to be verified on your GitHub account.** No Site was modified or deployed from this package.

## What it currently includes

- **Paris–Roubaix 2027:** known official date: 11 April 2027; organiser riders page `paris-roubaix.fr/en/riders`. This page currently shows **2026** starters, so they are **rejected** for the 2027 league.
- **Tour de France 2027:** 2–25 July 2027; scraper reads the official `letour.fr/en/overall-route` table, including 21 stages and 3 rest days; the 2027 rider list is not yet assumed to be available.
- A **disabled 2026 Paris–Roubaix historical test** for experimentation. It will **not** be published to the 2027 Site feed unless explicitly enabled.
- Three independent roster extraction strategies: embedded JSON, semantic HTML list, semantic HTML table. The year must be stated on the *roster* page, not inferred from the homepage.
- Validates rider counts, teams, bibs, duplicates, edition, sudden drops in roster size, stage dates and stage numbers; failed fetches keep the last accepted roster/schedule.
- Scheduled runner via GitHub Actions and static JSON feed, with no cycling API key or continuously running server. A health check fails the GitHub workflow if a race starts within 48 hours and no valid start list is available (enable GitHub Actions failure-email notifications).

## First-time setup (Windows — no coding experience required)

1. Download and **extract** `Peloton_Race_Scraper.zip`.
2. Create a **free GitHub account** if needed and install **GitHub Desktop** (`desktop.github.com`).
3. In GitHub Desktop choose **File → Add Local Repository**, select the extracted folder. If asked, select **Create a Repository Here**. Commit the files and click **Publish Repository**. Make it **Public** (the code and organiser race data only; never store league passwords or secrets here).
4. On GitHub open your repository → **Settings → Actions → General**. Under **Workflow permissions**, enable **Read and write permissions** if your account allows this; save.
5. Open the **Actions** tab → **Peloton - Update official race data** → **Run workflow**. Select `force = true` for the first diagnostic run. Watch the logs for `published`, `not_published` or `unavailable`.
6. When it finishes, open the file `data/latest.json` in the repository. It should have a real `generated_at` timestamp and race statuses. Inspect `stages` for Tour de France. A `source unavailable` status means GitHub could not access the organiser; the 2027 startlist should remain empty while not published.
7. Build the public JSON address using **your GitHub username and repository**:

   `https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPOSITORY/main/data/latest.json`

   Open that URL in your browser and check it displays JSON. No API key is needed.
8. Open your **existing Peloton Site editor**. Copy `SITE_EDITOR_PROMPT.txt`, replace the placeholder with your real raw JSON URL, and ask the editor to implement the integration. Preview first, and publish only when working.

Afterward the scheduled GitHub workflow runs at **07:23 and 19:23 UTC** daily. The Python scheduler actually checks individual race sites weekly when they are more than 14 days away, daily 3–14 days out, and every 12 hours in the last 48 hours. The GitHub Actions workflow writes an updated JSON file back to the repository. GitHub's scheduled jobs are not guaranteed to start exactly on time and can be automatically disabled in inactive public repositories.

## Running locally (optional)

In the extracted folder, open PowerShell / Windows Terminal:

```powershell
py -m pip install -r requirements.txt
py -m pytest -q
py scraper.py --force
```

First check real HTTP requests on GitHub rather than assuming that a page reachable in a browser is reachable from GitHub's data centre.

## Adding races

Edit `races.json`: add **one entry per race edition**, each with a stable `id`, actual `year`, `start_date` (ISO format), `type` (`one_day` or `grand_tour`), `website`, `startlist_urls`, `date_format` (`dmy` or `mdy`), and `enabled: true`. For official stage tables add `stage_urls` and `expected_stages`. Only add organisers for which the publicly accessible page actually supplies information in a supported structure. **This starter version is tested for ASO-like structures; RCS and Flanders Classics need their own verified fixtures/adapters.**

Do not use URLs for last year's race results as a substitute for current starters. A new edition without an explicitly year-labelled start list stays pending.

## Failsafe behaviour

- Previous validated list exists and fetch fails → `stale` with saved riders.
- Page explicitly says 2026 while requested edition is 2027 → `not_published`, no wrong-year riders.
- No known roster year, no riders, no earlier snapshot → `not_published`.
- Invalid/abnormal extracted data → rejected, previous snapshot remains.
- Source response 403/blocked → do not bypass; record an error and try only configured publicly accessible organiser alternatives.
- A moved race date discovered on the organiser homepage is **flagged for review**, never silently used to move a draft deadline.

Published means *validated source edition*, **not** a guarantee of final/confirmed starters. A late change may still happen.

## Limitations

- No live organiser HTTP requests could be executed in this creation environment, so **all parser tests use offline HTML fixtures modelled on official pages**. GitHub's first real run is required to determine if its IP addresses are allowed and the current HTML still matches.
- No browser/JavaScript rendering fallback in this initial lightweight version. JavaScript-only pages or complete redesigns may require a new adapter.
- The existing ChatGPT Site's internal code/database is not accessible here; the separate static feed works independently but the **Site editor must integrate it**.
- Cross-origin fetches are subject to the Site's policies; if raw GitHub URLs are blocked from the Site, a different permitted static hosting or backend ingestion mechanism is needed.
- Public GitHub repositories expose the scraper config and public organiser data. Do not upload private league user data.
- Respect organiser website terms and access limits. Do not defeat CAPTCHA or authentication. The no-API approach does not grant redistribution rights if a source restricts them.

## Project map

| File | Purpose |
|---|---|
| `scraper.py` | HTTP downloader, roster/stage parser, validation, data caching |
| `races.json` | Race edition configuration (2026 history disabled) |
| `.github/workflows/update-races.yml` | Automatic free schedule and JSON updates |
| `data/latest.json` | Public Site-consumable JSON (initial placeholder) |
| `site_integration.js` | Example Site-side read/preview helper |
| `monitor.py` | Warn about urgent missing startlists/stage schedules via workflow failure |
| `SITE_EDITOR_PROMPT.txt` | Paste into existing Peloton Site editor |
| `tests/fixtures/` | Mock HTML including 2027 date + wrong-year roster and 21-stage route |
| `tests/test_scraper.py` | Automated regression tests |