/**
 * Example adapter for the existing Peloton Site.
 * No API key. The URL is a plain public JSON file hosted by GitHub.
 *
 * IMPORTANT: This does not modify the site's private database or draft picks.
 * Use with the actual Site data models; names/IDs may differ.
 */
export async function loadOfficialRaceData(publicJsonUrl) {
  if (!/^https:\/\//.test(publicJsonUrl)) {
    throw new Error('Use a public HTTPS JSON feed URL');
  }
  const response = await fetch(publicJsonUrl, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Official data feed returned HTTP ${response.status}`);
  const feed = await response.json();
  if (feed.schema_version !== 1 || !Array.isArray(feed.races)) {
    throw new Error('Unsupported Peloton race feed');
  }
  return feed;
}

// Normalise accents and separators for fallback matching, without touching IDs.
function key(s) {
  return String(s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').toLowerCase();
}

/**
 * Preview the external data against races already registered in the Site.
 * Do not alter scoring, membership, authentication or existing draft picks.
 */
export function previewRaceData(existingRaces, feed) {
  return existingRaces.map(race => {
    const match = feed.races.find(x => x.id === race.id) || feed.races.find(
      x => x.year === (race.year || Number(String(race.start_date || race.date).slice(0, 4)))
        && key(x.name) === key(race.name)
    );
    if (!match) return { race, external: null, status: 'unmatched' };
    const list = match.startlist || {};
    const accepted = list.status === 'published' && list.edition_year === match.year
      && Array.isArray(list.riders) && list.riders.length > 0;
    const alreadyPickedNames = new Set((race.draft_picks || []).map(p => key(p.rider_name)));
    const newNames = new Set((list.riders || []).map(r => key(r.name)));
    const affectedPicks = [...alreadyPickedNames].filter(name => !newNames.has(name));
    return {
      race,
      external: match,
      startlistReady: accepted,
      importedRiders: accepted ? list.riders : [],
      stagesReady: match.stage_status === 'published',
      stageDates: match.stage_status === 'published' ? match.race_days : [],
      affectedPicks: accepted ? affectedPicks : [],
      status: list.status || 'unknown'
    };
  });
}