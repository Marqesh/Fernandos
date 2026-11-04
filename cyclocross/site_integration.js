/** Cyclocross-only read adapter. Never writes Peloton DB, picks, or scores. */
export const CX_FEED_URL =
  "https://raw.githubusercontent.com/Marqesh/Fernandos/feature/cyclocross-2026-27/cyclocross/data/latest.json";

export async function loadCyclocrossFeed(fetchImpl = fetch) {
  const response = await fetchImpl(CX_FEED_URL, { cache: "no-store" });
  if (!response.ok) throw new Error("Cyclocross feed unavailable: HTTP " + response.status);
  const data = await response.json();
  if (data.schema_version !== 1 || data.discipline !== "cyclocross"
      || data.season !== "2026-2027" || !Array.isArray(data.races)) {
    throw new Error("Invalid cyclocross feed");
  }
  const ids = new Set();
  for (const race of data.races) {
    if (!race.id.startsWith("cx-") || ids.has(race.id) || race.category !== "Men Elite"
        || race.year !== Number(race.date?.slice(0,4))) {
      throw new Error("Wrong cyclocross race/category/edition");
    }
    ids.add(race.id);
  }
  return data;
}

export function previewCyclocrossRaces(feed) {
  return feed.races.map(race => {
    const list = race.startlist || {};
    const correct = list.edition_year === race.year && list.category === race.category;
    const final = correct && list.status === "published";
    const provisional = correct && list.status === "provisional";
    return {
      id: race.id,
      name: race.name,
      date: race.date,
      category: race.category,
      series: race.series,
      state: final ? "ready" : provisional ? "provisional" :
        list.status === "stale" ? "stale" : "pending",
      // A provisional entry list is for preview; never unlock a draft automatically.
      draftEligible: final,
      riders: (final || provisional) && Array.isArray(list.riders) ? list.riders : [],
      source: list.source_url || race.website,
      warning: list.warning || null,
      checkedAt: list.checked_at || feed.generated_at,
    };
  });
}
