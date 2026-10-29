# Peloton season validation

Production: `races.json` -> `data/latest.json`, automatically scheduled twice daily.

Historical test: `races_2026.json` -> `data/history-2026.json`, manually triggered workflow.

**Isolation**: 2026 historical results never enter the 2027 site feed. The historical workflow uses `--force` because the normal scheduler correctly stops checking races more than two days after their scheduled date.

**Important:** a 2026 race may no longer have its archived start list on the official organiser's current `/riders` URL. A `not_published` or `unavailable` status is a failed archive retrieval, not proof that riders never started.

**Scope verification**: This repository currently has two confirmed races, Paris-Roubaix and Tour de France, for 2027. The full target calendar is stored in the league's external workbook, but the workbook's cells are not available via the current connection. Do not guess additional target race names, URLs, dates or editions.

**Future adapters:** Each organiser/race family should have an explicit year-validated 2026 historical fixture, a verified official organiser source, and a 2027 edition configuration. Never copy 2026 starters into 2027.
