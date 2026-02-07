# Dev vs Production Environment Separation

## The Rule
NEVER serve the `voice-assistant-frontend/out/` directory locally on a different port to test the frontend. The `out/` directory is a **static export built with production env vars** (baked-in `NEXT_PUBLIC_*` values). Serving it on `localhost:XXXX` causes Firebase domain mismatches and cookie origin issues.

## Architecture

| Component | Local Dev | Production |
|-----------|-----------|------------|
| AVA Frontend | `npm run dev` on `:3006` | Static export on Cloudflare (`the-invitation-2.makecontact.io`) |
| Token Server | `localhost:3011` | `token.makecontact.io` (systemd service) |
| Embed Test Server | `temp_embed_page_server.py` on `:3019` | N/A (customers embed via iframe on their own site) |

## How to Test Locally

### Testing the embed flow (simulating a customer site)
Run `temp_embed_page_server.py` on `:3019`. It serves `embed-example.html` which contains an iframe pointing to the **production** AVA domain. This correctly simulates how a customer's WordPress site would embed the assistant.

### Testing frontend changes
Use `npm run dev` (`:3006`) for the Next.js dev server. This picks up `.env.local` values at runtime.

### Building for production
Run `npm run build` in `voice-assistant-frontend/`. This bakes `NEXT_PUBLIC_*` values from `.env.local` into the static HTML. Deploy the `out/` directory to Cloudflare.

## Env File Structure (voice-assistant-frontend)
- **`.env`** (committed) — Firebase public client keys + `NEXT_PUBLIC_AVA_DOMAIN`. These are safe to commit (NEXT_PUBLIC_ keys are embedded in client-side JS anyway).
- **`.env.local`** (gitignored) — Local dev overrides: LiveKit secrets, `NEXT_PUBLIC_BACKEND_URL`, etc. Never commit this.

## Firebase Project
The active Firebase project is **`ai-chatbot-v1-645d6`** (NOT `the-invitatation-temp`). Both the frontend `.env` and the token server's Admin SDK service account must reference the same project. If they don't match, ID token verification will fail silently.

## Key Env Vars
- `NEXT_PUBLIC_AVA_DOMAIN` (in `.env`) — The production domain where the static export is hosted. Used in Magic Link redirect URLs so Firebase accepts them. Must be in Firebase's authorized domains list.
- `NEXT_PUBLIC_BACKEND_URL` (in `.env.local`) — Token server URL. For local dev: `http://127.0.0.1:3011`. For production: set to the production token server URL.

## Common Pitfalls
- **`auth/unauthorized-continue-uri`**: The Magic Link redirect domain is not in Firebase's authorized domains. Fix: ensure `NEXT_PUBLIC_AVA_DOMAIN` points to a domain listed in Firebase Console > Authentication > Settings > Authorized domains.
- **`ERR_BLOCKED_BY_CLIENT` on token calls**: CORS issue. The frontend's origin must be in the token server's `CORS_ORIGIN` env var.
- **Cookies not persisting in iframe**: Third-party cookie blocking. The token server sets `partitioned: true` (CHIPS) on cookies to work around this.
