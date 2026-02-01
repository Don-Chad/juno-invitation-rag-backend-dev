import { RoomAgentDispatch, RoomConfiguration } from '@livekit/protocol';
import bodyParser from 'body-parser';
import cors from 'cors';
import dotenv from 'dotenv';
import express from 'express';
import type { Request, Response } from 'express';
import cookieParser from 'cookie-parser';
import { AccessToken } from 'livekit-server-sdk';
import { initializeApp, cert, getApps, App } from 'firebase-admin/app';
import { getAuth } from 'firebase-admin/auth';
import { getFirestore } from 'firebase-admin/firestore';
import rateLimit from 'express-rate-limit';
import fs from 'fs';
import path from 'path';
import { handleSubscriptionWebhook } from './webhooks.js';
import { createDeviceToken, validateDeviceToken, revokeDeviceToken } from './deviceTokens.js';

let appInstance: App;

type TokenRequest = {
  room_name?: string;
  participant_name?: string;
  participant_identity?: string;
  participant_metadata?: string;
  participant_attributes?: Record<string, string>;
  room_config?: ReturnType<RoomConfiguration['toJson']>;

  // (old fields, here for backwards compatibility)
  roomName?: string;
  participantName?: string;

  // Security field for anti-zombie check
  wpUserHash?: string;
};

// Load environment variables (server-side only)
// Support both .env and .env.local so you can keep secrets out of git easily.
dotenv.config({ path: '.env' });
dotenv.config({ path: '.env.local' });

function initFirebaseAdmin() {
  const apps = getApps();
  if (apps.length > 0) {
    appInstance = apps[0]!;
    return;
  }

  // Preferred: FIREBASE_SERVICE_ACCOUNT (stringified JSON)
  const inlineJson = process.env.FIREBASE_SERVICE_ACCOUNT;
  if (inlineJson) {
    const serviceAccount = JSON.parse(inlineJson);
    appInstance = initializeApp({ credential: cert(serviceAccount) });
    return;
  }

  // Optional: FIREBASE_SERVICE_ACCOUNT_PATH
  const envPath = process.env.FIREBASE_SERVICE_ACCOUNT_PATH;
  if (envPath && fs.existsSync(envPath)) {
    const serviceAccount = JSON.parse(fs.readFileSync(envPath, 'utf8'));
    appInstance = initializeApp({ credential: cert(serviceAccount) });
    return;
  }

  // Fallback: repo layout (your setup)
  // token-server-node/ (this project)
  // service account json is at: ../ai-chatbot-v1-645d6-firebase-adminsdk-....json
  const fallbackPath = path.resolve(process.cwd(), '..', 'ai-chatbot-v1-645d6-firebase-adminsdk-fbsvc-0b24386fbb.json');
  if (fs.existsSync(fallbackPath)) {
    const serviceAccount = JSON.parse(fs.readFileSync(fallbackPath, 'utf8'));
    appInstance = initializeApp({ credential: cert(serviceAccount) });
    return;
  }

  throw new Error('Firebase Admin not initialized: missing FIREBASE_SERVICE_ACCOUNT or service account file');
}

// This route handler creates a token for a given room and participant
async function createToken(request: TokenRequest) {
  const roomName = request.room_name ?? request.roomName!;
  const participantName = request.participant_name ?? request.participantName!;

  const at = new AccessToken(process.env.LIVEKIT_API_KEY, process.env.LIVEKIT_API_SECRET, {
    identity: request.participant_identity ?? participantName,
    ttl: process.env.TOKEN_TTL ?? '60m',
  });

  at.addGrant({
    roomJoin: true,
    room: roomName,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
    canUpdateOwnMetadata: true,
  });

  if (request.participant_metadata) {
    at.metadata = request.participant_metadata;
  }
  if (request.participant_attributes) {
    at.attributes = request.participant_attributes;
  }
  if (request.room_config) {
    at.roomConfig = RoomConfiguration.fromJson(request.room_config);
  }

  return at.toJwt();
}

const app = express();
app.set('trust proxy', true);
app.use(cookieParser());
app.use(bodyParser.json({ limit: '256kb' }));
const port = Number(process.env.PORT ?? '3011');

// CORS: needed if browser calls token server directly (separate origin).
// Use CORS_ORIGIN="https://your-frontend.com" to lock down; default "*" for local dev.
app.use(
  cors({
    origin: process.env.CORS_ORIGIN ?? '*',
    credentials: true,
  }),
);

// Secure mode: require Firebase login to mint tokens
const requireFirebaseAuth = (process.env.REQUIRE_FIREBASE_AUTH ?? 'true').toLowerCase() === 'true';
if (!requireFirebaseAuth) {
  throw new Error('REQUIRE_FIREBASE_AUTH must be true for this token server');
}
initFirebaseAdmin();

// 1. DEFINE RATE LIMITERS
// Allow max 10 token requests per minute per IP
const tokenLimiter = rateLimit({
  windowMs: 1 * 60 * 1000, // 1 minute
  max: 10,
  message: { message: "Too many token requests, please try again later." }
});

// Allow max 5 webhook requests per minute (should be rare)
const webhookLimiter = rateLimit({
  windowMs: 1 * 60 * 1000,
  max: 20, // Higher limit to allow for bulk syncs, but still prevents flooding
  message: { message: "Webhook rate limit exceeded." }
});

app.get('/healthz', (_req, res) => res.status(200).send({ ok: true }));

// --- 🌐 WEBHOOKS & DEVICE TOKENS ---
app.post('/api/webhook/subscription', webhookLimiter, handleSubscriptionWebhook);
app.post('/api/create-device-token', tokenLimiter, createDeviceToken);
app.post('/api/validate-device-token', tokenLimiter, validateDeviceToken);
app.post('/api/revoke-device-token', tokenLimiter, revokeDeviceToken);

// Apply limiter to the route
app.post('/createToken', tokenLimiter, async (req: Request, res: Response) => {
  const body: TokenRequest = req.body ?? {};

  try {
    if (!process.env.LIVEKIT_URL) return res.status(500).send({ message: 'LIVEKIT_URL not set' });
    if (!process.env.LIVEKIT_API_KEY) return res.status(500).send({ message: 'LIVEKIT_API_KEY not set' });
    if (!process.env.LIVEKIT_API_SECRET) return res.status(500).send({ message: 'LIVEKIT_API_SECRET not set' });

    const authHeader = req.header('Authorization') ?? '';
    if (!authHeader.startsWith('Bearer ')) {
      return res.status(401).send({ message: 'Unauthorized' });
    }

    const idToken = authHeader.slice('Bearer '.length);
    const decoded = await getAuth(appInstance).verifyIdToken(idToken, true);
    const uid = decoded.uid;
    const email = decoded.email;

    // --- 🛡️ CUSTOM SECURITY CHECKS START HERE ---

    // 2. CHECK SUBSCRIPTION IN FIRESTORE
    const enableSubscriptionCheck = (process.env.ENABLE_SUBSCRIPTION_CHECK ?? 'true').toLowerCase() === 'true';
    if (enableSubscriptionCheck) {
      const db = getFirestore(appInstance);
      // We now check the 'users' collection which is populated by webhooks
      const userSnapshot = await db.collection('users')
        .where('email', '==', email?.toLowerCase())
        .limit(1)
        .get();

      if (userSnapshot.empty) {
        console.warn(`Blocked access for ${email}: No user record found`);
        return res.status(403).send({ message: 'Subscription Required' });
      }

      const userData = userSnapshot.docs[0].data();
      const status = userData.subscription?.status;

      if (status !== 'active' && status !== 'trial') {
        console.warn(`Blocked access for ${email}: Subscription status is ${status}`);
        return res.status(403).send({ message: 'Subscription Required' });
      }
    }

    // 3. CHECK WP USER HASH (Anti-Zombie) (OPTIONAL - disabled by default)
    // To enable wpUserHash validation, set ENABLE_WPUSERHASH_CHECK=true in your .env
    // The frontend must send 'wpUserHash' in the body
    const enableWpUserHashCheck = (process.env.ENABLE_WPUSERHASH_CHECK ?? 'false').toLowerCase() === 'true';
    if (enableWpUserHashCheck) {
      const sentHash = body.wpUserHash;
      // You would compare this against what is stored in your deviceTokens collection
      // (If you are using the cookie-based flow we designed, this happens in 'validateDeviceToken')
      if (!sentHash) {
        console.warn(`Blocked access for ${email}: Missing wpUserHash`);
        return res.status(403).send({ message: 'Invalid device token' });
      }
    }

    // --- 🛡️ CUSTOM SECURITY CHECKS END ---

    const name = decoded.name ?? (email?.includes('@') ? email.split('@')[0] : uid);

    // Make each connect a fresh session.
    //
    // Why:
    // - Reusing the same (room, identity) can result in session-resume behavior in LiveKit Cloud,
    //   which can prevent the agent dispatcher from launching a new worker job reliably.
    // - A session-unique room name guarantees a "new room" path (and new dispatch) while we keep
    //   the stable uid in metadata/attributes for history + recognition.
    const sessionId = Date.now();
    const uniqueIdentity = `${uid}__${sessionId}`;

    // Session-unique room name, but still contains the stable uid prefix for backend parsing.
    body.roomName = `${uid}_conversation__${sessionId}`;
    body.participantName = name;
    body.participant_identity = uniqueIdentity;
    body.participant_metadata = JSON.stringify({ uid, email });
    body.participant_attributes = {
      ...(body.participant_attributes ?? {}),
      uid,
    };

    // Ensure agent dispatch is configured via RoomConfiguration on the token.
    // If your LiveKit Cloud project uses agent dispatch, this is the most reliable trigger.
    const configuredAgentName = process.env.LIVEKIT_AGENT_NAME ?? 'juno';
    if (!body.room_config) {
      body.room_config = new RoomConfiguration({
        agents: [
          new RoomAgentDispatch({
            agentName: configuredAgentName,
            metadata: JSON.stringify({ uid, email }),
          }),
        ],
      }).toJson();
    }

    const roomName = body.room_name ?? body.roomName!;
    const participantName = body.participant_name ?? body.participantName!;

    console.log(
      `Generating token for room: ${roomName}, user: ${uid}, identity: ${uniqueIdentity}, agent: ${
        configuredAgentName
      }`,
    );

    res.send({
      // Match the Next.js frontend shape so you can switch endpoints easily
      serverUrl: process.env.LIVEKIT_URL,
      roomName,
      participantName,
      participantToken: await createToken(body),
    });
  } catch (err) {
    console.error('Error generating token:', err);
    res.status(500).send({ message: 'Generating token failed' });
  }
});

app.listen(port, () => {
  console.log(`Server listening on port ${port}`);
});
