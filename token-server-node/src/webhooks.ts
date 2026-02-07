/**
 * WooCommerce Webhook Handler
 * Receives subscription events from WordPress
 */

import { Request, Response } from 'express';
import { getFirestore, FieldValue } from 'firebase-admin/firestore';
import { timingSafeEqual } from 'crypto';

interface SubscriptionWebhookPayload {
  eventType: 'user_created' | 'trial_started' | 'subscription_activated' | 
             'subscription_expired' | 'subscription_cancelled' | 'subscription_renewed' | 
             'subscription_sync' | 'email_changed';
  siteId: string;
  timestamp: string;
  data: {
    wpUserId: string;
    email: string;
    displayName?: string;
    wpOrderId?: string;
    wpSubscriptionId?: string;
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
  const expectedApiKey = process.env.WEBHOOK_API_KEY;
  
  if (!expectedApiKey || !apiKey || !siteId) return false;
  
  return apiKey.length === expectedApiKey.length && 
    timingSafeEqual(Buffer.from(apiKey), Buffer.from(expectedApiKey));
}

export async function handleSubscriptionWebhook(req: Request, res: Response): Promise<void> {
  try {
    if (!verifyWebhookAuth(req)) {
      res.status(401).json({ message: 'Unauthorized' });
      return;
    }
    
    const payload: SubscriptionWebhookPayload = req.body;
    const { eventType, siteId, data } = payload;
    const db = getFirestore();

    // 1. Handle Email Changes
    if (eventType === 'email_changed' && data.oldEmail && data.newEmail) {
      const oldUserSnapshot = await db.collection('users')
        .where('email', '==', data.oldEmail.toLowerCase())
        .where('wpSiteId', '==', siteId)
        .limit(1)
        .get();
      
      if (!oldUserSnapshot.empty) {
        const userDoc = oldUserSnapshot.docs[0];
        const uid = userDoc.data().uid;
        
        const batch = db.batch();
        batch.update(userDoc.ref, {
          email: data.newEmail.toLowerCase(),
          updatedAt: new Date()
        });
        
        if (uid) {
          // Wipe history and keys
          const convs = await db.collection('conversations').where('user_id', '==', uid).get();
          convs.forEach(doc => batch.delete(doc.ref));
          
          batch.update(db.collection('users').doc(uid), {
            history_key_wrapped: FieldValue.delete(),
            history_key_wrapped_nonce: FieldValue.delete(),
            history_key_kek_version: FieldValue.delete(),
            history_key_v: FieldValue.delete(),
            email: data.newEmail.toLowerCase(),
            updatedAt: new Date()
          });
        }
        await batch.commit();
        res.json({ success: true, message: 'Email updated and history wiped' });
        return;
      }
    }

    // 2. Handle Subscription Updates
    if (!data.email) {
      res.status(400).json({ message: 'Missing email in data' });
      return;
    }

    const normalizedEmail = data.email.toLowerCase();
    const usersSnapshot = await db.collection('users')
      .where('email', '==', normalizedEmail)
      .where('wpSiteId', '==', siteId)
      .limit(1)
      .get();
    
    const subscriptionData: any = {
      email: normalizedEmail,
      wpUserId: data.wpUserId || 'unknown',
      wpSiteId: siteId,
      subscription: {
        status: data.subscriptionStatus || 'active',
        plan: data.plan || 'basic',
        lastVerifiedAt: new Date()
      },
      updatedAt: new Date()
    };

    // Only add optional fields if they are explicitly provided and not null/undefined
    if (data.displayName) subscriptionData.displayName = data.displayName;
    if (data.startedAt) subscriptionData.subscription.startedAt = new Date(data.startedAt);
    if (data.expiresAt) subscriptionData.subscription.expiresAt = new Date(data.expiresAt);
    
    if (eventType === 'user_created' || usersSnapshot.empty) {
      subscriptionData.createdAt = new Date();
      subscriptionData.createdBy = 'woocommerce_webhook';
      // Only set uid to null if we are creating a fresh record
      if (usersSnapshot.empty) {
        subscriptionData.uid = null;
      }
    }

    if (!usersSnapshot.empty) {
      await usersSnapshot.docs[0].ref.update(subscriptionData);
    } else {
      await db.collection('users').add(subscriptionData);
    }
    
    res.json({ success: true, email: normalizedEmail });
    
  } catch (error) {
    console.error('Webhook processing error:', error);
    res.status(500).json({ message: 'Failed to process webhook' });
  }
}
