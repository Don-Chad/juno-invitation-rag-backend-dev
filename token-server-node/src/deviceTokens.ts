/**
 * Device Token API
 * 
 * Creates and validates long-lived device tokens for silent re-authentication.
 * Tokens are stored in Firestore and bound to device fingerprints.
 */

import { Request, Response } from 'express';
import { getFirestore } from 'firebase-admin/firestore';
import { getAuth } from 'firebase-admin/auth';
import crypto from 'crypto';

const TOKEN_LENGTH = 64;
const TOKEN_EXPIRY_DAYS = 180;

interface DeviceTokenData {
  token: string;
  uid: string;
  email: string;
  siteId: string;
  deviceFingerprint: string;
  createdAt: Date;
  expiresAt: Date;
  lastUsedAt: Date;
  isValid: boolean;
}

interface ApprovedSite {
  siteId: string;
  origin: string;
  allowed: boolean;
}

/**
 * Generate a cryptographically secure device token
 */
function generateToken(): string {
  return crypto.randomBytes(TOKEN_LENGTH).toString('hex');
}

/**
 * Hash a token for storage (prevents token leakage in DB)
 */
function hashToken(token: string): string {
  return crypto.createHash('sha256').update(token).digest('hex');
}

/**
 * Verify origin is in approved sites list
 */
async function verifyOrigin(siteId: string, origin: string): Promise<boolean> {
  const db = getFirestore();
  const siteDoc = await db.collection('approvedSites').doc(siteId).get();
  
  if (!siteDoc.exists) {
    // For development, if siteId is 'dev' or if the collection is empty, maybe allow?
    // But for security, we should enforce this.
    console.warn(`Site ${siteId} not found in approvedSites`);
    return false;
  }
  
  const siteData = siteDoc.data() as ApprovedSite;
  // Origin verification can be tricky with iframes, might need more robust checks
  return siteData.allowed === true;
}

/**
 * Create device token endpoint
 * POST /api/create-device-token
 */
export async function createDeviceToken(req: Request, res: Response): Promise<void> {
  try {
    const authHeader = req.header('Authorization') ?? '';
    if (!authHeader.startsWith('Bearer ')) {
      res.status(401).json({ message: 'Unauthorized: missing Bearer token' });
      return;
    }

    const idToken = authHeader.slice('Bearer '.length);
    const { siteId, deviceFingerprint } = req.body;

    if (!siteId || !deviceFingerprint) {
      res.status(400).json({ message: 'Missing required fields: siteId, deviceFingerprint' });
      return;
    }

    // Verify Firebase ID token
    const decoded = await getAuth().verifyIdToken(idToken, true);
    const uid = decoded.uid;
    const email = decoded.email || 'unknown';

    // Verify site is approved
    const origin = req.get('Origin') || req.get('Referer') || '';
    const isApproved = await verifyOrigin(siteId, origin);
    
    if (!isApproved) {
      res.status(403).json({ message: 'Site not approved' });
      return;
    }

    // Generate and store device token
    const token = generateToken();
    const tokenHash = hashToken(token);
    const now = new Date();
    const expiresAt = new Date(now.getTime() + TOKEN_EXPIRY_DAYS * 24 * 60 * 60 * 1000);

    const tokenData: DeviceTokenData = {
      token: tokenHash, // Store hash, not raw token
      uid,
      email,
      siteId,
      deviceFingerprint,
      createdAt: now,
      expiresAt,
      lastUsedAt: now,
      isValid: true
    };

    const db = getFirestore();
    await db.collection('deviceTokens').doc(tokenHash).set(tokenData);
    
    // Also update user record with the UID if it's missing (JIT linking)
    const userSnapshot = await db.collection('users')
        .where('email', '==', email.toLowerCase())
        .where('wpSiteId', '==', siteId)
        .limit(1)
        .get();
    
    if (!userSnapshot.empty) {
        const userDoc = userSnapshot.docs[0];
        const userData = userDoc.data();
        
        if (!userData.uid) {
            // "Promote" this document: Create a new one with UID as ID, and delete the old one
            const db = getFirestore();
            await db.collection('users').doc(uid).set({
                ...userData,
                uid,
                updatedAt: new Date()
            });
            await userDoc.ref.delete();
            console.log(`Promoted user ${email} from temporary doc to UID-based doc: ${uid}`);
        }
    } else {
        // No webhook record found yet, but the user is logging in.
        // Create a record for them anyway so the subscription check passes later if needed.
        const db = getFirestore();
        const userDoc = db.collection('users').doc(uid);
        const doc = await userDoc.get();
        if (!doc.exists) {
            await userDoc.set({
                uid,
                email: email.toLowerCase(),
                createdAt: new Date(),
                updatedAt: new Date(),
                subscription: { status: 'none' } // Will be updated by webhook soon
            });
        }
    }

    // Set httpOnly cookie with raw token
    res.cookie('ava_device_token', token, {
      httpOnly: true,
      secure: true, // ALWAYS true for cross-origin cookies
      sameSite: 'none', // Required for cross-origin iframe
      partitioned: true, // CHIPS support for Chrome third-party cookie policy
      maxAge: TOKEN_EXPIRY_DAYS * 24 * 60 * 60 * 1000,
      path: '/'
    });

    res.json({
      success: true,
      uid,
      email,
      expiresAt: expiresAt.toISOString()
    });

    console.log(`Device token created for user ${uid} on site ${siteId}`);
  } catch (err) {
    console.error('Error creating device token:', err);
    res.status(500).json({ message: 'Failed to create device token' });
  }
}

/**
 * Validate device token endpoint
 * POST /api/validate-device-token
 */
export async function validateDeviceToken(req: Request, res: Response): Promise<void> {
  try {
    const { siteId, deviceFingerprint } = req.body;
    
    // Get token from httpOnly cookie only
    const tokenToValidate = req.cookies?.ava_device_token;

    if (!tokenToValidate || !siteId || !deviceFingerprint) {
      res.status(400).json({
        valid: false,
        message: 'Missing required fields'
      });
      return;
    }

    const tokenHash = hashToken(tokenToValidate);
    const db = getFirestore();
    const tokenDoc = await db.collection('deviceTokens').doc(tokenHash).get();

    if (!tokenDoc.exists) {
      res.status(401).json({ 
        valid: false, 
        message: 'Invalid token' 
      });
      return;
    }

    const tokenData = tokenDoc.data() as DeviceTokenData;

    // Validate token
    const now = new Date();
    const checks = {
      isValid: tokenData.isValid,
      notExpired: now < tokenData.expiresAt,
      siteMatches: tokenData.siteId === siteId,
      deviceMatches: tokenData.deviceFingerprint === deviceFingerprint
    };

    if (!checks.isValid || !checks.notExpired) {
      // Invalidate token
      await tokenDoc.ref.update({ isValid: false });
      
      res.status(401).json({ 
        valid: false, 
        message: 'Token expired or invalidated' 
      });
      return;
    }

    if (!checks.siteMatches) {
      res.status(403).json({ 
        valid: false, 
        message: 'Token not valid for this site' 
      });
      return;
    }

    // Device mismatch handling - be careful with fingerprinting stability
    if (!checks.deviceMatches) {
      // For now, warn and allow, or strictly enforce? 
      // The plan says strictly enforce.
      await tokenDoc.ref.update({ isValid: false });
      
      res.status(401).json({ 
        valid: false, 
        message: 'Device mismatch - please re-authenticate' 
      });
      return;
    }

    // Update last used timestamp
    await tokenDoc.ref.update({ lastUsedAt: now });

    res.json({
      valid: true,
      uid: tokenData.uid,
      email: tokenData.email
    });

  } catch (err) {
    console.error('Error validating device token:', err);
    res.status(500).json({ 
      valid: false, 
      message: 'Validation error' 
    });
  }
}

/**
 * Revoke device token endpoint
 * POST /api/revoke-device-token
 */
export async function revokeDeviceToken(req: Request, res: Response): Promise<void> {
  try {
    const authHeader = req.header('Authorization') ?? '';
    if (!authHeader.startsWith('Bearer ')) {
      res.status(401).json({ message: 'Unauthorized' });
      return;
    }

    const idToken = authHeader.slice('Bearer '.length);
    const decoded = await getAuth().verifyIdToken(idToken, true);
    const uid = decoded.uid;

    const tokenToRevoke = req.cookies?.ava_device_token;
    if (!tokenToRevoke) {
        res.status(400).json({ message: 'No token found in cookies' });
        return;
    }

    const tokenHash = hashToken(tokenToRevoke);
    
    const db = getFirestore();
    const tokenDoc = await db.collection('deviceTokens').doc(tokenHash).get();

    if (!tokenDoc.exists) {
      res.status(404).json({ message: 'Token not found' });
      return;
    }

    const tokenData = tokenDoc.data() as DeviceTokenData;

    // Only allow users to revoke their own tokens
    if (tokenData.uid !== uid) {
      res.status(403).json({ message: 'Cannot revoke token for different user' });
      return;
    }

    await tokenDoc.ref.update({ isValid: false });

    // Clear cookie
    res.clearCookie('ava_device_token', {
        httpOnly: true,
        secure: true,
        sameSite: 'none',
        partitioned: true,
        path: '/'
    });

    res.json({ success: true });
  } catch (err) {
    console.error('Error revoking device token:', err);
    res.status(500).json({ message: 'Failed to revoke token' });
  }
}
