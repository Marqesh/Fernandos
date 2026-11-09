// Portable browser client for the existing Peloton frontend.
// Fetch uses same-origin HttpOnly cookie session; no tokens in localStorage.
export function createPelotonClient(base = "") {
  async function call(path, method = "GET", body) {
    const res = await fetch(base + "/api/auth" + path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.error || "Request failed.");
    return result;
  }
  return {
    me: () => call("/me").then(x => x.member),
    login: (username, password) => call("/login", "POST", { username, password }).then(x => x.member),
    logout: () => call("/logout", "POST"),
    changePassword: (currentPassword, newPassword) =>
      call("/change-password", "POST", { currentPassword, newPassword }).then(x => x.member),
    listUsers: () => call("/admin/users").then(x => x.users),
    createUser: (user) => call("/admin/users", "POST", user),
    updateUser: (id, changes) => call("/admin/users/" + encodeURIComponent(id), "PATCH", changes),
    resetPassword: (id, password) =>
      call("/admin/users/" + encodeURIComponent(id) + "/password", "POST", { password })
  };
}
