/**
 * WooCommerce Webhook Handler
 * Receives subscription events from WordPress
 * 
 * CRITICAL: Does NOT create Firebase Auth users.
 * Firebase Auth users are created Just-in-Time when user clicks Magic Link.
 */

import { Request, Response } from 'express';
import { getFirestore, FieldValue } from 'firebase-admin/firestore';

interface SubscriptionWebhookPayload {
  eventType: 'user_created' | 'trial_started' | 'subscription_activated' | 
             'subscription_expired' | 'subscription_cancelled' | 'subscription_renewed' | 
             'subscription_sync' | 'email_changed';
  siteId: string;
  timestamp: string;
  data: {
    wpUserId: string;
    email: string;
    displayName: string;
    wpOrderId: string;
    wpSubscriptionId: string;
    subscriptionStatus: 'active' | 'expired' | 'cancelled' | 'trial';
    plan?: string;
    startedAt?: string;
    expiresAt?: string;
    trialEndsAt?: string;
    isTrial?: boolean;
    oldEmail?: string;
    newEmail?: string;
  };
}

/**
 * Verify webhook signature/API key
 */
function verifyWebhookAuth(req: Request): boolean {
  const apiKey = req.header('X-AVA-API-Key');
  const siteId = req.header('X-AVA-Site-ID');
  
  // TODO: Verify against stored API keys in Firestore
  return !!apiKey && !!siteId;
}

/**
 * Handle subscription webhook
 * POST /api/webhook/subscription
 *
 * FIXED: Only creates Firestore subscription record.
 * Firebase Auth user is created JIT when Magic Link is clicked.
 */
export async function handleSubscriptionWebhook(req: Request, res: Response): Promise<void> {
  try {
    // Verify webhook authenticity
    if (!verifyWebhookAuth(req)) {
      res.status(401).json({ message: 'Unauthorized' });
      return;
    }
    
    const payload: SubscriptionWebhookPayload = req.body;
    const { eventType, siteId, data } = payload;
    
    const db = getFirestore();

    // Special case for email changes
    if (eventType === 'email_changed') {
      const { oldEmail, newEmail } = data;
      if (oldEmail && newEmail) {
        // Find user by old email
        const oldUserSnapshot = await db.collection('users')
          .where('email', '==', oldEmail.toLowerCase())
          .where('wpSiteId', '==', siteId)
          .limit(1)
          .get();
        
        if (!oldUserSnapshot.empty) {
          const userDoc = oldUserSnapshot.docs[0];
          const userData = userDoc.data();
          const uid = userData.uid;
          
          // Update email in Firestore
          await userDoc.ref.update({
            email: newEmail.toLowerCase(),
            updatedAt: new Date()
          });
          
          // --- 🔒 SECURITY: WIPE HISTORY AND DESTROY KEYS ON EMAIL CHANGE ---
          if (uid) {
            // 1. Wipe all conversation documents
            const conversationsSnapshot = await db.collection('conversations')
              .where('user_id', '==', uid)
              .get();
            
            const batch = db.batch();
            conversationsSnapshot.forEach(doc => {
              batch.delete(doc.ref);
            });
            
            // 2. Destroy the encryption keys in the user profile
            // This makes any backed-up/restored messages unreadable forever
            const userRef = db.collection('users').doc(uid);
            batch.update(userRef, {
              history_key_wrapped: FieldValue.delete(),
              history_key_wrapped_nonce: FieldValue.delete(),
              history_key_kek_version: FieldValue.delete(),
              history_key_v: FieldValue.delete(),
              email: newEmail.toLowerCase(),
              updatedAt: new Date()
            });

            await batch.commit();
            console.log(`Destroyed history and encryption keys for UID ${uid} due to identity change.`);
          }
          
          res.json({ success: true, message: 'Email updated, history wiped, and keys burned' });
          return;
        } else {
            console.log(`Email change requested but user not found: ${oldEmail}`);
            res.status(404).json({ message: 'User not found' });
            return;
        }
      }
    }

    // FIX: Normalize email to lowercase to prevent case-sensitivity issues
    const normalizedEmail = data.email.toLowerCase();
    
    console.log(`Received webhook: ${eventType} for ${normalizedEmail}`);
    
    // Check if user document already exists (from previous login or webhook)
    const usersSnapshot = await db.collection('users')
      .where('email', '==', normalizedEmail)
      .where('wpSiteId', '==', siteId)
      .limit(1)
      .get();
    
    // Prepare subscription data
    const subscriptionData: any = {
      email: normalizedEmail,
      displayName: data.displayName,
      wpUserId: data.wpUserId,
      wpSiteId: siteId,
      subscription: {
        status: data.subscriptionStatus,
        plan: data.plan || 'basic',
        lastVerifiedAt: new Date()
      },
      updatedAt: new Date()
    };
    
    if (data.startedAt) {
      subscriptionData.subscription.startedAt = new Date(data.startedAt);
    }
    if (data.expiresAt) {
      subscriptionData.subscription.expiresAt = new Date(data.expiresAt);
    }
    
    if (data.isTrial || data.trialEndsAt) {
      subscriptionData.trial = {
        isTrial: true,
        startedAt: new Date(),
        endsAt: data.trialEndsAt ? new Date(data.trialEndsAt) : null
      };
    }
    
    if (eventType === 'user_created' || eventType === 'trial_started') {
      subscriptionData.createdAt = new Date();
      subscriptionData.createdBy = 'woocommerce_webhook';
      // NOTE: uid will be populated on first Magic Link login (JIT creation)
      // We only set it if it doesn't already exist
      if (usersSnapshot.empty) {
        subscriptionData.uid = null;
      }
    }
    
    // Update or create user document
    if (!usersSnapshot.empty) {
      // Update existing user
      const userDoc = usersSnapshot.docs[0];
      await userDoc.ref.update(subscriptionData);
      console.log(`Updated subscription for existing user: ${normalizedEmail}`);
    } else {
      // Create new user document (without uid - will be set on first login)
      await db.collection('users').add(subscriptionData);
      console.log(`Created subscription record for new user: ${normalizedEmail}`);
    }
    
    // Log event
    await db.collection('subscriptionEvents').add({
      eventId: `${eventType}_${Date.now()}`,
      userId: usersSnapshot.empty ? null : usersSnapshot.docs[0].id,
      email: normalizedEmail,
      eventType: eventType,
      wpOrderId: data.wpOrderId,
      wpSubscriptionId: data.wpSubscriptionId,
      timestamp: new Date(payload.timestamp),
      processedAt: new Date()
    });
    
    res.json({ success: true, email: normalizedEmail });
    
  } catch (error) {
    console.error('Webhook processing error:', error);
    res.status(500).json({ message: 'Failed to process webhook' });
  }
}
