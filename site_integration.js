/**
 * Peloton - read-only official cycling feed adapter.
 * This module contains no database writes, authentication, draft or scoring code.
 * The existing Peloton Site must call these functions from its OWN frontend.
 */

export const PELOTON_FEED_URL =
  'https://raw.githubusercontent.com/Marqesh/Fernandos/main/data/peloton-feed.json';

export async function loadOfficialRaceData(url = PELOTON_FEED_URL, fetchImpl = fetch) {
  if (url !== PELOTON_FEED_URL && !/^https:\/\//.test(url)) {
    throw new Error('The race feed must use HTTPS');
  }
  const response = await fetchImpl(url, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Official race feed HTTP ${response.status}`);
  const feed = await response.json();
  if (feed.schema_version !== 1 || feed.season !== 2027 ||
      !Array.isArray(feed.races) || feed.races.length !== 30) {
    throw new Error('Unexpected Peloton 2027 feed format');
  }
  const ids = new Set();
  for (const race of feed.races) {
    if (race.year !== 2027 || !race.id || ids.has(race.id)) {
      throw new Error('Invalid or duplicated race in official feed');
    }
    ids.add(race.id);
  }
  return feed;
}

export function normaliseRaceName(s) {
  return String(s || '')
    .normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').toLowerCase();
}

export function siteRaceYear(race) {
  const y = race.year || race.season || race.edition_year;
  if (y !== null && y !== undefined && y !== '') {
    const num = Number(y);
    if (Number.isInteger(num) && num > 1900) return num;
  }
  const date = race.start_date || race.date;
  const match = typeof date === 'string' ? date.match(/^(20\d\d)-/) : null;
  return match ? Number(match[1]) : null;
}

function verifiedRoster(officialRace) {
  const s = officialRace?.startlist || {};
  return s.status === 'published' && s.edition_year === officialRace.year &&
    officialRace.year === 2027 && Array.isArray(s.riders) && s.riders.length >= 10 &&
    s.riders.every(x => x && typeof x.name === 'string' && x.name.trim() &&
      typeof x.team === 'string' && x.team.trim());
}

function matchExternalRace(siteRace, feed) {
  const y = siteRaceYear(siteRace);
  if (y !== 2027) return null; // Fail closed rather than mix editions.
  const candidates = feed.races.filter(r => r.year === y);
  // Exact stable external ID or event key is preferable to matching names.
  const direct = candidates.find(r => [r.id, r.key].includes(siteRace.external_id) ||
    [r.id, r.key].includes(siteRace.id) || [r.id, r.key].includes(siteRace.key));
  if (direct) return direct;
  const names = [siteRace.name, siteRace.title, siteRace.race_name]
    .map(normaliseRaceName).filter(Boolean);
  if (!names.length) return null;
  const matching = candidates.filter(r => [r.name, ...(r.aliases || [])]
    .map(normaliseRaceName).some(a => names.includes(a)));
  // Ambiguous names must not silently select the wrong event.
  return matching.length === 1 ? matching[0] : null;
}

function sourceWarning(external) {
  if (!external) return 'No matching official 2027 event found';
  if (external.startlist?.status === 'published') return null;
  return external.startlist?.warning || '2027 start list not yet available';
}

/**
 * View model, not a mutation. No picks, deadlines or memberships are touched.
 * The Site remains authoritative for race deadlines, race types and scoring.
 */
export function previewRaceData(existingRaces, feed) {
  if (!Array.isArray(existingRaces)) throw new Error('Race list must be an array');
  return existingRaces.map(race => {
    const external = matchExternalRace(race, feed);
    if (!external) {
      return {
        race, external: null, matched: false, status: 'unmatched',
        importedRiders: [], startlistReady: false, stagesReady: false,
        stageDates: [], affectedPicks: [], warning: sourceWarning(null),
        feedGeneratedAt: feed.generated_at,
      };
    }
    const accepted = verifiedRoster(external);
    const importedRiders = accepted ? external.startlist.riders : [];
    const draftedNames = new Set((race.draft_picks || [])
      .map(p => normaliseRaceName(p.rider_name || p.rider?.name)).filter(Boolean));
    const availableNames = new Set(importedRiders.map(x => normaliseRaceName(x.name)));
    const affectedPicks = accepted ? [...draftedNames].filter(x => !availableNames.has(x)) : [];
    const publishedStages = external.stage_status === 'published' &&
      Array.isArray(external.stages) && external.stages.length > 0;
    return {
      race,
      external,
      matched: true,
      status: external.startlist?.status || 'not_published',
      startlistAvailability: external.startlist_availability,
      startlistReady: accepted,
      importedRiders,
      riderCount: importedRiders.length,
      stagesReady: publishedStages,
      stages: publishedStages ? external.stages : [],
      stageDates: publishedStages ? external.race_days : [],
      affectedPicks, // Display ONLY: never remove or invalidate a saved pick here.
      warning: sourceWarning(external),
      feedGeneratedAt: feed.generated_at,
      officialDate: external.start_date,
      dateStatus: external.date_status,
      officialSource: external.startlist_source || external.website,
    };
  });
}

/**
 * Optional utility for administrative status panels without requiring site data.
 * The Site can display statuses for the whole season even before races exist
 * in its local database. It MUST NOT auto-create race or draft records.
 */
export function seasonStatusRows(feed) {
  return feed.races.map(r => ({
    id: r.id, name: r.name, year: r.year, date: r.start_date,
    dateStatus: r.date_status, status: r.startlist?.status || 'not_published',
    availability: r.startlist_availability,
    riders: verifiedRoster(r) ? r.startlist.riders.length : 0,
    checkedAt: r.watch_checked_at || r.production_checked_at,
    source: r.startlist_source || r.website,
    warning: sourceWarning(r),
    stages: r.stage_status === 'published' ? r.stages.length : 0,
  }));
}
