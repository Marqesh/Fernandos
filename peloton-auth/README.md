# Peloton independent account integration

Target: existing ChatGPT Site, NOT a replacement. Preview in a test branch; do not publish until migrated and tested.

## Why
The public GitHub repo currently stores cycling scrapers and public race feeds, **not the Site application source or its private records**. The included SQL and JavaScript provide a portable identity layer but cannot directly modify the private Site from GitHub.

## Setup (admin)
1. Create a Supabase project at https://supabase.com/dashboard. Protect admin access with MFA.
2. In Supabase SQL Editor run `peloton-auth/schema.sql`. Inspect the SQL first. It does not create or change league picks.
3. Under Authentication settings disable public sign-ups (invite-only), configure allowed site URLs/redirects, email confirmation, password recovery, and a production email SMTP provider before onboarding users.
4. In Authentication > Users invite the five players. Once an account exists, inspect its auth UUID and insert a matching profile into `peloton_profiles`, then associate its **real existing** player identifier to road and/or cyclocross using `peloton_player_links`. Do not guess existing IDs. Use a controlled, audited admin workflow for future invitations.
5. Make yourself admin by setting the admin role on your **verified** profile in trusted SQL/admin tooling only; do not permit client role editing.
6. Expose only `SUPABASE_URL` and the **public publishable/anon key** in the browser environment. NEVER expose service-role/secret keys in the frontend or a public GitHub repo.
7. Install/import `@supabase/supabase-js` in the Site code and call `createClient(url, publicKey)`, then `createPelotonAuth(client)` from `peloton-auth/client.mjs`.
8. Replace the existing local user selector/login with a login form using `auth.signIn(email,password)`. On reload use `auth.restoreSession()`; on sign-out use `auth.signOut()`. Provide `auth.requestPasswordReset(email, redirectTo)` for the forgotten-password flow. Handle auth errors with generic messages and do not log passwords.
9. Link `member.playerIds.road` and `member.playerIds.cyclocross` to the existing local league player records. Do not create another player or reset old records.
10. Gate pages and buttons by session and profile. **Critical:** do not treat client checks as security. Protect every draft submission, Top 10 reveal, membership lookup, and admin action in the authoritative backend using validated identity and authorization. If currently persisted only in browser storage or private Site-managed data, design a deliberate server-side data migration before enabling multi-device play.

## League business rules
- One account = one player identity (possibly linked to both disciplines).
- Players can only submit or change their own permitted draft picks / private predictions.
- Administrator can manage races, deadlines, members and results; backend confirms admin role.
- Public scoreboard may be shared if intended. Private predictions and unrevealed Top 10 must be unreadable by other players until the reveal policy allows them.
- Preserve snake-draft order and saved choices across the migration.
- Do not change scraper/GitHub public feed; no player information may enter that repository's `data/` feed.
- Road and cyclocross use the same login, but maintain isolated competitions and season/race records.

## Site editor prompt (paste into the existing editor)
Implement portable Supabase authentication for the existing Peloton Site. Follow the README and identity module in:
https://github.com/Marqesh/Fernandos/tree/feature/peloton-independent-auth/peloton-auth

Preserve the existing player records, admin settings, picks, 1-day race snake draft, Velogames, Grand Tour secret Top 10, results, race feeds, 2027 road season and 2026-27 cyclocross. Do not replace or wipe private Site storage. Add sign in/out, remembered login, password recovery, invitation-only member accounts and two-discipline profile links. The signed-in account must map to the existing player record. **Do not claim accounts are independently secure until the authoritative draft and prediction writes are protected by server-side identity checks.** If this Site environment cannot call Supabase or export/migrate its private data, report the blocker instead of silently substituting browser localStorage. Do not deploy without administrator review.

## Acceptance tests
- Two accounts on separate browsers, each consistently logs in as their own EXISTING player.
- A refresh/new device keeps the correct identity.
- A user cannot spoof another player ID or impersonate an admin by modifying browser state, requests or local storage.
- Two devices see a committed pick; race deadlines and snake order enforced in backend; concurrent selection of the same rider cannot both succeed.
- Secret Top 10 inaccessible to other members before reveal.
- Road and cyclocross share identity but do not contaminate each other's picks or results.
- Account disabled/removed -> no longer authorized (including an already logged-in session).
- Existing picks, standings and administrator controls still function.
- Login/logout/password-reset/expired-session flows work.
- Existing public race scraper and GitHub workflows continue unchanged.

## Status
This branch is a **foundation**, not a deployed login. No live Supabase project or credentials have been configured. The private Site source and current user datastore are not accessible in this repository. Further integration and data authorization work is essential.
