export const config = {
  cognitoDomain: import.meta.env.VITE_COGNITO_DOMAIN,
  clientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
  redirectUri: `${window.location.origin}/auth/callback`,
  logoutUri: `${window.location.origin}/`,
  scopes: "openid email profile",
};