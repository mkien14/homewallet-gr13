## Local development

Run commands from `frontend` after installing dependencies with `npm install`.

- `npm run dev` starts the Vite development server using `VITE_API_TARGET` from `.env.local`.
- `npm run dev:mock` starts the UI with browser-local sample data.
- `npm run build` creates the production frontend bundle.

For local sign-in, configure the Cognito domain, SPA client ID, user pool ID, and `VITE_ENABLE_REACT_AUTH_UI=true` in `.env.local`. The branded sign-in screen uses Cognito SRP through AWS Amplify Auth; passwords are sent directly to Cognito, not to the HomeWallet API. Use the SRP form locally: the Hosted UI fallback is disabled because Cognito only registers the deployed CloudFront callback, not localhost. The production release enables that fallback on the deployed website.

The language selector supports Vietnamese and English. The selected language is saved in the browser before sign-in and synchronized to `/api/me` after sign-in. The light and dark themes are remembered in the browser. See `.env.example` for the required frontend settings; it contains placeholders only.
