// Cognito console/Terraform outputs can contain a hostname without a scheme.
// Always use an absolute HTTPS origin for authorize, token, and logout URLs.
export function normalizeCognitoOrigin(value) {
  const domain = (value || "").trim();
  if (!domain) return "";

  const invalid = () => new Error("VITE_COGNITO_DOMAIN must be a Cognito HTTPS origin without a path, query, or credentials");
  if (/[\s\\]/.test(domain)) throw invalid();

  let url;
  try {
    url = new URL(domain.includes("://") ? domain : `https://${domain}`);
  } catch {
    throw invalid();
  }
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password ||
      url.pathname !== "/" || url.search || url.hash) {
    throw invalid();
  }
  return url.origin;
}
