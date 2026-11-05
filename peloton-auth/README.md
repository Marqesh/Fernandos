# Peloton: simple approved-player login

This folder provides **username + password + admin-approved whitelist** for the EXISTING Peloton site, without email, public registration, Supabase, or a third-party auth service.

## What it does
- An admin creates each account with a username and temporary password, and explicitly approves it.
- One username is linked to the **existing** road and/or cyclocross player IDs. Do not create duplicate players.
- Players log in independently on any device. The server issues a 7-day HttpOnly session cookie.
- The admin can approve, disable, reassign a player link, or reset passwords. No public signup route.
- Passwords are salted and scrypt-hashed, not stored in plaintext.
- Identities, sessions, approval and role checks live in a **private SQLite database**, not the public GitHub race feed.
- One shared login serves both road and cyclocross; picks and standings remain distinct.

## Files
- `server.mjs`: minimal Node 24+ HTTP service built with Node's `node:sqlite`, no extra packages.
- `client.mjs`: small browser fetch wrapper for the Site.
- `SITE_EDITOR_PROMPT.md`: instructions to connect the existing Site without resetting user or draft data.

## Local setup
1. Install Node.js 24 or newer on the future host.
2. From the repository root, run `node peloton-auth/server.mjs bootstrap-admin admin` and enter a **unique** password with at least 10 characters (the password prompt is not masked; use a trusted terminal). The admin account can only be bootstrapped once.
3. Set `NODE_ENV=production`, `APP_ORIGIN=https://your-real-domain`, `PELOTON_AUTH_DB=/private/persistent/path/peloton-auth.sqlite` and `PORT=3001`.
4. Run `node peloton-auth/server.mjs` behind an HTTPS reverse proxy routing `/api/auth/*` to localhost:3001. The API and website must be same-origin (the browser should only see the public HTTPS domain).
5. Use the site editor's actual frontend framework to build a sign-in screen, admin member list, approval and password reset UI calling `createPelotonClient()`. On app load, call `me()` to restore the user's login.
6. Set strong passwords for all five users. Back up the private SQLite database and WAL consistently. Do not commit it, share it in the GitHub repo, or expose it via a static folder.

## Critical integration requirement
This standalone service establishes **who** is logged in, but it does not yet protect your existing draft endpoints. The actual Site source and private datastore are not included in this GitHub repo. When integrating the Site, backend draft/result handlers **must** consult the authenticated session and account-to-player mapping instead of accepting caller-supplied user IDs. Enforce race deadlines, current picker, uniqueness of rider picks, and secret Top-10 access on the server. Browser-side hiding alone does not enforce permissions.

Until the Site is connected, **this is not a deployed working login**. If the ChatGPT Site editor cannot host a Node backend, keep this service for the future external deployment and do not pretend that a localStorage user selector provides independent authenticated accounts.

## API
- `POST /api/auth/login`: `{username,password}` -> member + secure cookie
- `POST /api/auth/logout`: clears current session
- `GET /api/auth/me`: returns logged-in member or null
- `GET /api/auth/admin/users`: admin list
- `POST /api/auth/admin/users`: admin creates whitelist entry; fields `username,password,approved,roadPlayerId,cyclocrossPlayerId`
- `PATCH /api/auth/admin/users/:id`: admin approves/disables/links players
- `POST /api/auth/admin/users/:id/password`: admin changes a user's password and revokes existing sessions

Never expose the SQLite database, hashed passwords, or password values in public JavaScript. Admin users must be approved server-side. The service uses a small in-memory login attempt limiter; for production use a reverse-proxy or managed rate limiter across instances and ensure CSRF protections for any additional cookie-authenticated write routes. A single server process is the intended deployment.

## Road and cyclocross mapping
Example response from `/api/auth/me`:
```json
{
  "member": {
    "id": "server-generated-uuid",
    "username": "player1",
    "role": "player",
    "roadPlayerId": "existing-road-player-id",
    "cyclocrossPlayerId": "existing-cyclocross-player-id"
  }
}
```

## Verification
Test with 2 separate browsers and 2 different users. Confirm sign-in/out, session restore on refresh, admin-only membership actions, account deactivation, old picks preserved, each user selecting only on their turn, no duplicate rider choices, no unauthorized pre-reveal Top 10 access, and shared identity across disciplines.

No live site has been modified by these GitHub changes.
