export function hostedUiFallbackEnabled(setting, origin) {
  if (setting !== "true") return false;
  try {
    const url = new URL(origin);
    return url.protocol === "https:" && !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  } catch {
    return false;
  }
}
