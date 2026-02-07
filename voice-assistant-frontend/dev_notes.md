# AVA Voice Assistant - Authentication & Iframe Persistence

## Core Architecture
The AVA Voice Assistant uses a multi-layered authentication strategy to ensure users stay logged in even when embedded in third-party iframes (e.g., WordPress sites).

### 1. The "Split-Session" Problem
Modern browsers (Chrome, Safari) use **Storage Partitioning**. A Firebase login completed in a top-level tab (from a magic link email) is NOT visible inside an embedded iframe on another domain.

### 2. The Solution: Auth Handoff Flow
We use a custom handoff mechanism via the token server:
1. **Iframe**: Generates a random `handoffId` and includes it in the magic link redirect URL.
2. **Iframe**: Starts polling `POST /api/auth-handoff/status`.
3. **Magic Link Tab**: User clicks link, signs in to Firebase.
4. **Magic Link Tab**: Calls `POST /api/auth-handoff/complete` with its ID token and the `handoffId`.
5. **Token Server**: Verifies the ID token and stores the `uid/email` against the `handoffId` (TTL 10m).
6. **Iframe**: Poller receives `complete: true` and a **Firebase Custom Token**.
7. **Iframe**: Signs in locally using the custom token.

### 3. Session Persistence (Remembered Device)
- **Device Token Cookie**: After login, the frontend exchanges the Firebase token for a long-lived device token cookie (`ava_device_token`).
- **CHIPS (Partitioned Cookies)**: The cookie is set with the `partitioned: true` flag. This allows the browser to save the cookie specifically for the `[Customer Site + AVA Domain]` combination, bypassing third-party cookie blocks.
- **Silent Re-auth**: On page load, the iframe first checks Firebase. If no session, it calls `POST /api/validate-device-token`. If valid, it knows the device is trusted (though we currently still show the login UI for Firebase consistency).

## Environment Configuration
- **`.env`** (committed): Contains public Firebase keys for project `ai-chatbot-v1-645d6` and production URLs.
- **`.env.local`** (ignored): Contains local secrets (LiveKit API keys) and overrides.

### Key URLs
- **Frontend**: `https://the-invitation-2.makecontact.io`
- **Token Server**: `https://token.makecontact.io`
- **Logout**: Visit `/?action=logout` to clear all sessions and cookies.

## Observability & Rate Limits
The token server logs rate-limit events to `journalctl`.
- **`/createToken`**: 60/min
- **`/api/auth-handoff/status`**: 120/min
- **`/api/auth-handoff/complete`**: 30/min

## Common Pitfalls
- **Stale Build**: If you change `NEXT_PUBLIC_` variables, you MUST run `npm run build`. These are baked into the static JS files.
- **CORS**: The embedding site's origin must be in the token server's `CORS_ORIGIN` list.
- **Firebase Domains**: The `NEXT_PUBLIC_AVA_DOMAIN` must be in the Firebase "Authorized domains" list.
