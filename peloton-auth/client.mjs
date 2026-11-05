/**
 * Peloton Auth adapter for a host-created Supabase client.
 *
 * This module is independent of React, Vite, and ChatGPT Sites.
 * The host must initialize @supabase/supabase-js with its URL and
 * public publishable key (never the secret/service-role key).
 *
 * This is an identity bridge, not authorization for write operations.
 * Every protected write must be checked by backend rules/RLS.
 */

const DISCIPLINES = new Set(["road", "cyclocross"]);

export function createPelotonAuth(supabase) {
  if (!supabase || !supabase.auth || typeof supabase.from !== "function") {
    throw new TypeError("Supply an initialized Supabase client");
  }

  async function currentMember() {
    const { data: userData, error: userError } = await supabase.auth.getUser();
    if (userError) {
      if (userError.name === "AuthSessionMissingError") return null;
      throw userError;
    }
    const user = userData?.user;
    if (!user) return null;

    const { data: profile, error: profileError } = await supabase
      .from("peloton_profiles")
      .select("id, display_name, role, active")
      .eq("id", user.id)
      .maybeSingle();

    if (profileError) throw profileError;
    if (!profile || !profile.active) return null;

    const { data: links, error: linkError } = await supabase
      .from("peloton_player_links")
      .select("discipline, existing_player_id")
      .eq("user_id", user.id);

    if (linkError) throw linkError;
    const playerIds = { road: null, cyclocross: null };
    for (const link of links || []) {
      if (DISCIPLINES.has(link.discipline)) {
        playerIds[link.discipline] = link.existing_player_id;
      }
    }

    return {
      userId: user.id,
      email: user.email || "",
      displayName: profile.display_name,
      role: profile.role,
      isAdmin: profile.role === "admin",
      playerIds
    };
  }

  function canEnter(member) {
    return !!(member && (member.isAdmin ||
      member.playerIds.road || member.playerIds.cyclocross));
  }

  async function signIn(email, password) {
    if (!email?.trim() || !password) {
      throw new Error("Email and password are required.");
    }

    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password
    });
    if (error) throw error;

    let member;
    try {
      member = await currentMember();
    } catch (error) {
      await supabase.auth.signOut();
      throw error;
    }
    if (!canEnter(member)) {
      await supabase.auth.signOut();
      throw new Error("This account is not linked to an active Peloton member.");
    }
    return member;
  }

  async function restoreSession() {
    const { data, error } = await supabase.auth.getSession();
    if (error) throw error;
    if (!data?.session) return null;

    const member = await currentMember();
    if (!canEnter(member)) {
      await supabase.auth.signOut();
      return null;
    }
    return member;
  }

  async function signOut() {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
  }

  async function requestPasswordReset(email, redirectTo) {
    if (!email?.trim()) throw new Error("Email is required.");
    const options = redirectTo ? { redirectTo } : undefined;
    const { error } = await supabase.auth.resetPasswordForEmail(
      email.trim(),
      options
    );
    if (error) throw error;
  }

  // Schedule database calls outside the synchronous auth event handler.
  function onChange(callback) {
    const { data } = supabase.auth.onAuthStateChange(() => {
      setTimeout(async () => {
        try {
          callback(null, await restoreSession());
        } catch (error) {
          callback(error, null);
        }
      }, 0);
    });
    return () => data.subscription.unsubscribe();
  }

  return {
    signIn,
    signOut,
    restoreSession,
    currentMember,
    requestPasswordReset,
    onChange
  };
}
