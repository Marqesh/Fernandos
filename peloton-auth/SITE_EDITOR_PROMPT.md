# Peloton Site editor: simple whitelist login

Update the **existing Peloton** Site, not a replacement. This is an invitation/approval-only login for a tiny friends league. Do not use Supabase, Firebase, registration forms, email verification, or an external account service.

Use the small Node + SQLite backend and frontend client in:
https://github.com/Marqesh/Fernandos/tree/feature/peloton-independent-auth/peloton-auth

UX:
- Login screen: username and password, sign in.
- Persist login via secure HttpOnly cookie, restore session on reload, logout button.
- Admin > Users: list all players, create account, explicitly approve, block, reset password, link existing road and cyclocross players. No public signups.
- Display current user and only their profile/picks; admin sees admin menu. Apply server-side permissions, not client checks only.
- Keep five existing player records, saved picks, scores, calendars, road/cyclocross settings and all draft order/scoring rules unchanged.
- No account duplication. Never write passwords/identity records to public GitHub feeds.

If this ChatGPT Site cannot host a Node service or access/migrate its existing datastore, tell the administrator and leave the current live Site intact. Do not falsely simulate independent authentication using localStorage.

Before publication test different users on different devices and confirm no player can submit on another's behalf, and that draft concurrency and private Top 10 access are enforced by the backend.
