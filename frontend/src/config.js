export const config = {
  cognitoDomain: import.meta.env.VITE_COGNITO_DOMAIN,
  clientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
  userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
  reactAuthEnabled: import.meta.env.VITE_ENABLE_REACT_AUTH_UI === "true" && Boolean(import.meta.env.VITE_COGNITO_USER_POOL_ID && import.meta.env.VITE_COGNITO_CLIENT_ID),
  vapidPublicKey: import.meta.env.VITE_VAPID_PUBLIC_KEY,
  redirectUri: `${window.location.origin}/auth/callback`,
  logoutUri: `${window.location.origin}/`,
  scopes: "openid email profile aws.cognito.signin.user.admin",
};
