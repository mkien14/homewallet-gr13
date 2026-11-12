export function userDisplayName(user, fallback) {
  const name = typeof user?.display_name === "string" ? user.display_name.trim() : "";
  return name && !name.includes("@") ? name : fallback;
}
