-- Peloton identity mapping. Run once in the Supabase SQL Editor.
-- The hosted authentication provider owns passwords and sessions.
-- This migration does NOT modify existing races, picks, drafts, or results.

create table if not exists public.peloton_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (
    char_length(btrim(display_name)) between 1 and 80
  ),
  role text not null default 'player'
    check (role in ('admin', 'player')),
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.peloton_player_links (
  user_id uuid not null references public.peloton_profiles(id)
    on delete cascade,
  discipline text not null check (discipline in ('road', 'cyclocross')),
  existing_player_id text not null check (length(btrim(existing_player_id)) > 0),
  primary key (user_id, discipline),
  unique (discipline, existing_player_id)
);

-- Every identity can be linked to ONE pre-existing player per discipline.
-- No new player is generated when a person logs in.
-- Never put emails or authentication secrets in the public cycling feed.

alter table public.peloton_profiles enable row level security;
alter table public.peloton_player_links enable row level security;

-- Supabase projects may have permissive default grants.
revoke all on table public.peloton_profiles from anon, authenticated;
revoke all on table public.peloton_player_links from anon, authenticated;
grant select on table public.peloton_profiles to authenticated;
grant select on table public.peloton_player_links to authenticated;

drop policy if exists "peloton_profiles_read_self"
  on public.peloton_profiles;
create policy "peloton_profiles_read_self"
  on public.peloton_profiles for select to authenticated
  using (id = (select auth.uid()));

drop policy if exists "peloton_links_read_self"
  on public.peloton_player_links;
create policy "peloton_links_read_self"
  on public.peloton_player_links for select to authenticated
  using (user_id = (select auth.uid()));

-- Intentional: clients have no insert/update/delete grants or policies on
-- these two tables. Only trusted administration may provision or link players.
-- To provision an invited user, use the UUID in Authentication > Users.
--
-- Example, replacing every PLACEHOLDER with real, verified existing data:
-- insert into public.peloton_profiles (id, display_name, role)
-- values ('USER_UUID', 'Player name', 'player');
-- insert into public.peloton_player_links
--   (user_id, discipline, existing_player_id)
-- values ('USER_UUID', 'road', 'EXISTING_ROAD_PLAYER_ID');
-- insert into public.peloton_player_links
--   (user_id, discipline, existing_player_id)
-- values ('USER_UUID', 'cyclocross', 'EXISTING_CX_PLAYER_ID');
--
-- Do not execute the placeholder examples as written.
--
-- IMPORTANT: This schema secures ONLY the identity mapping tables.
-- Draft picks, predictions, league results, and admin actions also need
-- server-side validation and suitable RLS when moved into Supabase.
