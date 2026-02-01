# WooCommerce Subscription + AVA Integration Plan
## User Provisioning & Subscription Management (Fixed)

**Core Principle**: WooCommerce is the source of truth for subscription status. Firebase Auth is created Just-in-Time via Magic Links. AVA checks subscription status on every session start.

---

## Critical Fixes Applied

1. **No Firebase Auth Pre-Creation**: Webhook only creates Firestore subscription record. Firebase Auth user is created automatically when user clicks Magic Link.
2. **Secure User Notification**: Uses `wp_new_user_notification()` instead of plaintext password emails.
3. **Magic Link Authentication**: Passwordless email login ensures WooCommerce email = Firebase email without conflicts.
4. **Race Condition Handling**: Retry/polling mechanism for webhook delays on first login.
5. **Email Normalization**: All emails converted to lowercase to prevent case-sensitivity issues.
6. **Safari Third-Party Cookie Support**: Storage Access API fallback for cookie-blocked browsers.
7. **Email Change Sync**: WordPress hook to update AVA when user changes email.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         USER LIFECYCLE FLOW                                      │
└─────────────────────────────────────────────────────────────────────────────────┘

PHASE 1: Purchase (WordPress/WooCommerce)
═══════════════════════════════════════════════════════════════════════════════════

┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌─────────┐
│   Customer   │────▶│   WooCommerce    │────▶│   WordPress      │────▶│  AVA    │
│   (Visitor)  │     │   (Purchase)     │     │   (User Created) │     │ Backend │
└──────────────┘     └──────────────────┘     └──────────────────┘     └─────────┘
        │                     │                      │                      │
        │                     │                      │                      │
        ▼                     ▼                      ▼                      ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  1. Visitor buys subscription via WooCommerce                               │
   │  2. WP creates user account                                                 │
   │  3. WP sends secure "Set your password" email (wp_new_user_notification)    │
   │  4. WP webhook fires → sends subscription data to AVA backend               │
   │  5. AVA stores subscription in Firestore (NO Firebase Auth user created)    │
   │  6. Customer can now access AVA page (WP gates by subscription)             │
   └────────────────────────────────────────────────────────────────────────────┘


PHASE 2: First AVA Login (Magic Link)
═══════════════════════════════════════════════════════════════════════════════════

┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌─────────┐
│   Customer   │────▶│   AVA Embed      │────▶│   Firebase       │────▶│  AVA    │
│   (Member)   │     │   (WordPress)    │     │   Magic Link     │     │ Chat    │
└──────────────┘     └──────────────────┘     └──────────────────┘     └─────────┘
        │                     │                      │                      │
        │                     │                      │                      │
        ▼                     ▼                      ▼                      ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  1. Member clicks "Open AVA" on WordPress (membership page)                │
   │  2. WP verifies subscription is active (gates page access)                  │
   │  3. WP embeds AVA iframe with: user_email, site_id, nonce                   │
   │  4. AVA checks: "Do I have a valid device token?"                           │
   │  5. No token → AVA sends Magic Link to user's email (pre-filled from WP)    │
   │  6. User receives email: "Click to verify your device for AVA"              │
   │  7. User clicks link (on same device) → Firebase Auth user created (JIT)    │
   │  8. AVA backend checks subscription status in Firestore                     │
   │  9. If active → Create device token (30-day) → Allow chat                   │
   │  10. If expired → Show "Renew subscription" message                         │
   └────────────────────────────────────────────────────────────────────────────┘


PHASE 3: Return Visit (Silent Auth)
═══════════════════════════════════════════════════════════════════════════════════

┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌─────────┐
│   Customer   │────▶│   AVA Embed      │────▶│   AVA Backend    │────▶│  AVA    │
│   (Member)   │     │   (WordPress)    │     │   (Validate)     │     │ Chat    │
└──────────────┘     └──────────────────┘     └──────────────────┘     └─────────┘
        │                     │                      │                      │
        │                     │                      │                      │
        ▼                     ▼                      ▼                      ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  1. Member returns to AVA page on WordPress                                 │
   │  2. WP verifies subscription is still active                                │
   │  3. WP embeds AVA iframe                                                    │
   │  4. AVA finds device token (httpOnly cookie)                                │
   │  5. AVA backend validates device token + checks subscription in Firestore   │
   │  6. If still active → Silent login, start chat immediately                  │
   │  7. If expired → Clear token, show "Renew" message                          │
   │  8. If no token → Send Magic Link again (re-verification)                   │
   └────────────────────────────────────────────────────────────────────────────┘


PHASE 4: Subscription Expiry (Revocation)
═══════════════════════════════════════════════════════════════════════════════════

┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌─────────┐
│ WooCommerce  │────▶│   WP Webhook     │────▶│   AVA Backend    │────▶│Firebase │
│ (Subscription│     │   (Status Change)│     │   (Update Status)│     │/Firestore
│   Expires)   │     │                  │     │                  │     │         │
└──────────────┘     └──────────────────┘     └──────────────────┘     └─────────┘
        │                     │                      │                      │
        │                     │                      │                      │
        ▼                     ▼                      ▼                      ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  1. Subscription expires or is cancelled in WooCommerce                     │
   │  2. WP webhook fires → sends status change to AVA backend                   │
   │  3. AVA backend updates Firestore: subscription.status = 'expired'          │
   │  4. Existing chats: User can finish current session                         │
   │  5. New chats: Blocked with "Please renew your subscription"                │
   └────────────────────────────────────────────────────────────────────────────┘
```

---

## Why Magic Links?

| Problem | Magic Link Solution |
|---------|---------------------|
| **"Yahoo vs Gmail"** | Works with ANY email provider |
| **Double Account Confusion** | No password to remember - just verify email |
| **Pre-Creation Conflict** | Firebase Auth created JIT when link clicked |
| **Security** | WordPress cannot fake email verification |
| **UX** | "One-click" verification feels seamless |

---

## Firestore Schema

### Collection: `users`
```javascript
{
  // Firebase Auth UID (created JIT on first Magic Link click)
  uid: string,
  
  // Identity (must match WooCommerce email)
  email: string,
  displayName: string,
  
  // WooCommerce Link
  wpUserId: string,
  wpSiteId: string,
  
  // Subscription Status (Source of Truth: WooCommerce)
  subscription: {
    status: 'active' | 'expired' | 'cancelled' | 'trial',
    plan: 'basic',
    startedAt: timestamp,
    expiresAt: timestamp,
    lastVerifiedAt: timestamp
  },
  
  // Trial Status (managed by WordPress)
  trial: {
    isTrial: boolean,
    startedAt: timestamp,
    endsAt: timestamp
  },
  
  // Metadata
  createdAt: timestamp,
  lastLoginAt: timestamp,
  createdBy: 'woocommerce_webhook',
  
  // AVA Data
  chatHistory: subcollection,
  preferences: {
    theme: 'light' | 'dark',
    language: string
  }
}
```

### Collection: `subscriptionEvents`
```javascript
{
  eventId: string,
  userId: string,  // May be null until first login (JIT user creation)
  email: string,   // Always present - used to link
  eventType: 'created' | 'activated' | 'renewed' | 'expired' | 'cancelled',
  wpOrderId: string,
  wpSubscriptionId: string,
  timestamp: timestamp,
  processedAt: timestamp
}
```

---

## WordPress Plugin - Fixed

**File**: `ava-wordpress-plugin/ava-subscription.php`

```php
<?php
/**
 * AVA Subscription Management
 * Handles WooCommerce integration and webhooks
 */

class AVA_Subscription_Manager {
    
    private $ava_backend_url;
    private $site_id;
    private $api_key;
    
    public function __construct() {
        $this->ava_backend_url = get_option('ava_backend_url');
        $this->site_id = get_option('ava_site_id');
        $this->api_key = get_option('ava_api_key');
        
        // WooCommerce hooks
        add_action('woocommerce_order_status_completed', [$this, 'handle_purchase_complete'], 10, 1);
        add_action('woocommerce_subscription_status_active', [$this, 'handle_subscription_activated'], 10, 1);
        add_action('woocommerce_subscription_status_expired', [$this, 'handle_subscription_expired'], 10, 1);
        add_action('woocommerce_subscription_status_cancelled', [$this, 'handle_subscription_cancelled'], 10, 1);
        add_action('woocommerce_scheduled_subscription_payment', [$this, 'handle_subscription_renewed'], 10, 1);
        
        // Trial handling
        add_action('woocommerce_checkout_order_processed', [$this, 'handle_trial_start'], 10, 3);
        
        // Admin resync action
        add_action('admin_post_ava_resync_subscriptions', [$this, 'handle_resync_subscriptions']);
    }
    
    /**
     * Handle new subscription purchase
     */
    public function handle_purchase_complete($order_id) {
        $order = wc_get_order($order_id);
        if (!$order) return;
        
        // Check if order contains AVA subscription product
        if (!$this->order_contains_ava_product($order)) return;
        
        $user = $order->get_user();
        if (!$user) {
            // Create user account if guest checkout
            $user = $this->create_wp_user_from_order($order);
        }
        
        // Get subscription details
        $subscriptions = wcs_get_subscriptions_for_order($order_id);
        $subscription = reset($subscriptions);
        
        // Send to AVA backend (NO Firebase Auth user created - only subscription record)
        $this->notify_ava_backend('user_created', [
            'wpUserId' => $user->ID,
            'email' => $user->user_email,
            'displayName' => $user->display_name,
            'wpOrderId' => $order_id,
            'wpSubscriptionId' => $subscription ? $subscription->get_id() : null,
            'subscriptionStatus' => 'active',
            'plan' => 'basic',
            'startedAt' => $subscription ? $subscription->get_date('start') : current_time('mysql'),
            'expiresAt' => $subscription ? $subscription->get_date('end') : null,
            'isTrial' => false
        ]);
    }
    
    /**
     * Create WordPress user from order (FIXED: Secure password handling)
     */
    private function create_wp_user_from_order($order) {
        $email = $order->get_billing_email();
        $username = sanitize_user(current(explode('@', $email)));
        
        // Generate secure password
        $password = wp_generate_password(24, true, true);
        
        $user_id = wp_create_user($username, $password, $email);
        
        if (!is_wp_error($user_id)) {
            wp_update_user([
                'ID' => $user_id,
                'display_name' => $order->get_billing_first_name() . ' ' . $order->get_billing_last_name()
            ]);
            
            // FIXED: Use WordPress secure notification instead of plaintext password
            // This sends a "Set your password" link, not the actual password
            wp_new_user_notification($user_id, null, 'both');
        }
        
        return get_user_by('id', $user_id);
    }
    
    /**
     * Handle trial start
     */
    public function handle_trial_start($order_id, $posted_data, $order) {
        if (!$this->order_contains_ava_product($order)) return;
        
        $subscriptions = wcs_get_subscriptions_for_order($order_id);
        $subscription = reset($subscriptions);
        
        if ($subscription && $subscription->get_trial_period()) {
            $user = $order->get_user();
            
            $this->notify_ava_backend('trial_started', [
                'wpUserId' => $user->ID,
                'email' => $user->user_email,
                'displayName' => $user->display_name,
                'wpOrderId' => $order_id,
                'wpSubscriptionId' => $subscription->get_id(),
                'subscriptionStatus' => 'trial',
                'trialEndsAt' => $subscription->get_date('trial_end')
            ]);
        }
    }
    
    /**
     * Handle subscription expiry
     */
    public function handle_subscription_expired($subscription) {
        $user = $subscription->get_user();
        
        $this->notify_ava_backend('subscription_expired', [
            'wpUserId' => $user->ID,
            'email' => $user->user_email,
            'wpSubscriptionId' => $subscription->get_id(),
            'subscriptionStatus' => 'expired',
            'expiredAt' => current_time('mysql')
        ]);
    }
    
    /**
     * Handle subscription cancellation
     */
    public function handle_subscription_cancelled($subscription) {
        $user = $subscription->get_user();
        
        $this->notify_ava_backend('subscription_cancelled', [
            'wpUserId' => $user->ID,
            'email' => $user->user_email,
            'wpSubscriptionId' => $subscription->get_id(),
            'subscriptionStatus' => 'cancelled',
            'cancelledAt' => current_time('mysql')
        ]);
    }
    
    /**
     * Handle manual resync of all active subscriptions
     * Useful for debugging or recovering from missed webhooks
     */
    public function handle_resync_subscriptions() {
        if (!current_user_can('manage_options')) {
            wp_die('Unauthorized');
        }
        
        check_admin_referer('ava_resync_subscriptions');
        
        $count = 0;
        
        // Get all active subscriptions
        $subscriptions = wcs_get_subscriptions([
            'subscriptions_per_page' => -1,
            'subscription_status' => ['active', 'pending-cancel']
        ]);
        
        foreach ($subscriptions as $subscription) {
            $user = $subscription->get_user();
            if (!$user) continue;
            
            // Only sync if order contains AVA product
            if (!$this->order_contains_ava_product($subscription)) continue;
            
            $this->notify_ava_backend('subscription_sync', [
                'wpUserId' => $user->ID,
                'email' => $user->user_email,
                'displayName' => $user->display_name,
                'wpSubscriptionId' => $subscription->get_id(),
                'subscriptionStatus' => $subscription->get_status(),
                'expiresAt' => $subscription->get_date('end')
            ]);
            
            $count++;
        }
        
        wp_redirect(admin_url('options-general.php?page=ava-embed-settings&resynced=' . $count));
        exit;
    }
    
    /**
     * Send notification to AVA backend
     * FIX: Normalize email to lowercase to prevent case-sensitivity issues
     */
    private function notify_ava_backend($eventType, $data) {
        // Normalize email to lowercase
        if (isset($data['email'])) {
            $data['email'] = strtolower($data['email']);
        }
        
        $payload = [
            'eventType' => $eventType,
            'siteId' => $this->site_id,
            'timestamp' => current_time('mysql'),
            'data' => $data
        ];
        
        $response = wp_remote_post($this->ava_backend_url . '/api/webhook/subscription', [
            'headers' => [
                'Content-Type' => 'application/json',
                'X-AVA-API-Key' => $this->api_key,
                'X-AVA-Site-ID' => $this->site_id
            ],
            'body' => json_encode($payload),
            'timeout' => 30
        ]);
        
        if (is_wp_error($response)) {
            error_log('AVA Webhook Error: ' . $response->get_error_message());
        }
    }
    
    /**
     * Check if order contains AVA product
     */
    private function order_contains_ava_product($order) {
        $ava_product_ids = get_option('ava_product_ids', []);
        
        foreach ($order->get_items() as $item) {
            if (in_array($item->get_product_id(), $ava_product_ids)) {
                return true;
            }
        }
        return false;
    }
}

// Initialize
new AVA_Subscription_Manager();
```

---

## WordPress Plugin - Admin Settings with Resync Button

**File**: `ava-wordpress-plugin/ava-embed.php` (Admin page section)

```php
/**
 * Render settings page with Resync button
 */
public function render_settings_page() {
    $resynced_count = isset($_GET['resynced']) ? intval($_GET['resynced']) : null;
    ?>
    <div class="wrap">
        <h1>AVA Embed Settings</h1>
        
        <?php if ($resynced_count !== null): ?>
        <div class="notice notice-success">
            <p>Successfully resynced <?php echo $resynced_count; ?> subscriptions to AVA.</p>
        </div>
        <?php endif; ?>
        
        <form method="post" action="options.php">
            <?php settings_fields('ava_embed_settings'); ?>
            <?php do_settings_sections('ava_embed_settings'); ?>
            <table class="form-table">
                <tr>
                    <th>AVA Backend URL</th>
                    <td>
                        <input type="url" name="ava_backend_url" 
                               value="<?php echo esc_attr(get_option('ava_backend_url')); ?>"
                               class="regular-text">
                        <p class="description">The URL of your AVA backend (e.g., https://ava.example.com)</p>
                    </td>
                </tr>
                <tr>
                    <th>Site ID</th>
                    <td>
                        <input type="text" name="ava_site_id" 
                               value="<?php echo esc_attr(get_option('ava_site_id')); ?>"
                               class="regular-text">
                        <p class="description">Unique identifier for this WordPress site</p>
                    </td>
                </tr>
                <tr>
                    <th>API Key</th>
                    <td>
                        <input type="password" name="ava_api_key" 
                               value="<?php echo esc_attr(get_option('ava_api_key')); ?>"
                               class="regular-text">
                        <p class="description">API key for secure communication with AVA backend</p>
                    </td>
                </tr>
                <tr>
                    <th>AVA Product IDs</th>
                    <td>
                        <input type="text" name="ava_product_ids" 
                               value="<?php echo esc_attr(implode(',', get_option('ava_product_ids', []))); ?>"
                               class="regular-text">
                        <p class="description">Comma-separated list of WooCommerce product IDs that grant AVA access</p>
                    </td>
                </tr>
            </table>
            <?php submit_button('Save Settings'); ?>
        </form>
        
        <hr>
        
        <h2>Subscription Resync</h2>
        <p>If subscriptions are out of sync between WooCommerce and AVA, you can manually resync all active subscriptions.</p>
        
        <form method="post" action="<?php echo admin_url('admin-post.php'); ?>">
            <?php wp_nonce_field('ava_resync_subscriptions'); ?>
            <input type="hidden" name="action" value="ava_resync_subscriptions">
            <?php submit_button('Resync All Active Subscriptions', 'secondary'); ?>
        </form>
    </div>
    <?php
}
```

---

## AVA Backend - Fixed Webhook Handler

**File**: `token-server-node/src/webhooks.ts` (FIXED - No Firebase Auth creation)

```typescript
/**
 * WooCommerce Webhook Handler
 * Receives subscription events from WordPress
 * 
 * CRITICAL: Does NOT create Firebase Auth users.
 * Firebase Auth users are created Just-in-Time when user clicks Magic Link.
 */

import { Request, Response } from 'express';
import { getFirestore } from 'firebase-admin/firestore';

interface SubscriptionWebhookPayload {
  eventType: 'user_created' | 'trial_started' | 'subscription_activated' | 
             'subscription_expired' | 'subscription_cancelled' | 'subscription_renewed' | 
             'subscription_sync';
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
    
    // FIX: Normalize email to lowercase to prevent case-sensitivity issues
    const normalizedEmail = data.email.toLowerCase();
    
    console.log(`Received webhook: ${eventType} for ${normalizedEmail}`);
    
    const db = getFirestore();
    
    // Check if user document already exists (from previous login)
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
      subscriptionData.uid = null;
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
```

---

## AVA Frontend - Magic Link Authentication

**File**: `voice-assistant-frontend/components/MagicLinkAuth.tsx`

```typescript
"use client";

import { useState, useEffect } from "react";
import { 
  sendSignInLinkToEmail, 
  isSignInWithEmailLink, 
  signInWithEmailLink,
  User
} from "firebase/auth";
import { auth } from "@/lib/firebase";
import { motion } from "framer-motion";

interface MagicLinkAuthProps {
  userEmail: string; // Pre-filled from WordPress
  onAuthenticated: (user: User) => void;
}

export default function MagicLinkAuth({ userEmail, onAuthenticated }: MagicLinkAuthProps) {
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(60);

  // Check if this page load is from a Magic Link click
  useEffect(() => {
    if (isSignInWithEmailLink(auth, window.location.href)) {
      setLoading(true);
      
      // Get email from localStorage (saved when link was sent)
      let email = window.localStorage.getItem('emailForSignIn');
      
      // Safety: If email missing (user switched devices), ask for it
      if (!email) {
        email = window.prompt('Please provide your email for confirmation') || '';
      }
      
      if (!email) {
        setError('Email is required to complete sign-in');
        setLoading(false);
        return;
      }
      
      signInWithEmailLink(auth, email, window.location.href)
        .then((result) => {
          // Clear email from storage
          window.localStorage.removeItem('emailForSignIn');
          onAuthenticated(result.user);
        })
        .catch((err) => {
          console.error('Magic link sign-in error:', err);
          setError('Link expired or invalid. Please request a new one.');
          setLoading(false);
        });
    }
  }, [onAuthenticated]);

  // Countdown timer for resend
  useEffect(() => {
    if (sent && countdown > 0) {
      const timer = setTimeout(() => setCountdown(c => c - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [sent, countdown]);

  const sendMagicLink = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const actionCodeSettings = {
        url: `${window.location.origin}/embed/finishSignUp`,
        handleCodeInApp: true,
      };

      await sendSignInLinkToEmail(auth, userEmail, actionCodeSettings);
      
      // Save email for when user returns from email client
      window.localStorage.setItem('emailForSignIn', userEmail);
      
      setSent(true);
      setCountdown(60);
    } catch (err: any) {
      console.error('Failed to send magic link:', err);
      setError(err.message || 'Failed to send verification email');
    } finally {
      setLoading(false);
    }
  };

  if (loading && isSignInWithEmailLink(auth, window.location.href)) {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-[#B9965B] font-heading text-xl">Verifying your device...</div>
      </div>
    );
  }

  return (
    <div className="h-full min-h-[100svh] flex items-center justify-center bg-white relative">
      <div className="absolute inset-0 flex items-center justify-center z-0 overflow-hidden">
        <img 
          src="/background.png" 
          alt="AVA Background" 
          className="opacity-90 w-full h-full object-cover sm:object-contain"
          style={{ imageRendering: 'crisp-edges' }}
        />
      </div>
      
      <motion.div 
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="z-10 bg-white/90 backdrop-blur-md p-8 rounded-xl shadow-2xl border border-[#B9965B]/30 w-[calc(100%-2rem)] sm:w-96 text-center"
      >
        <h2 className="text-3xl font-heading font-bold text-[#B9965B] mb-2">Device Verification</h2>
        
        {!sent ? (
          <>
            <p className="text-gray-600 mb-6 font-body">
              To access your secure chat, we need to verify this device once.
              We'll send a magic link to:
            </p>
            
            <div className="bg-gray-50 p-3 rounded-lg mb-6 font-mono text-sm text-gray-700">
              {userEmail}
            </div>
            
            {error && (
              <div className="mb-4 p-3 bg-red-50 text-red-600 text-sm rounded-lg border border-red-100">
                {error}
              </div>
            )}

            <button
              onClick={sendMagicLink}
              disabled={loading}
              className="w-full py-3 px-6 bg-[#B9965B] hover:bg-[#A8854A] text-white rounded-lg font-body font-medium transition-all disabled:opacity-50"
            >
              {loading ? 'Sending...' : 'Send Magic Link'}
            </button>
            
            <p className="mt-6 text-xs text-gray-400 font-body">
              You won't need to do this again for 30 days on this device.
            </p>
          </>
        ) : (
          <>
            <div className="mb-6">
              <svg className="w-16 h-16 mx-auto text-[#B9965B]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            
            <p className="text-gray-600 mb-4 font-body">
              We've sent a magic link to:<br/>
              <strong>{userEmail}</strong>
            </p>
            
            <p className="text-sm text-gray-500 mb-6">
              Click the link in your email to verify this device.<br/>
              <span className="text-amber-600">Please open the link on this device.</span>
            </p>
            
            {countdown > 0 ? (
              <p className="text-xs text-gray-400">
                Resend available in {countdown}s
              </p>
            ) : (
              <button
                onClick={sendMagicLink}
                className="text-[#B9965B] hover:text-[#A8854A] text-sm underline"
              >
                Resend Magic Link
              </button>
            )}
          </>
        )}
      </motion.div>
    </div>
  );
}
```

---

## AVA Frontend - Finish Sign Up Page

**File**: `voice-assistant-frontend/app/embed/finishSignUp/page.tsx`

```typescript
"use client";

import { useEffect, useState } from "react";
import { isSignInWithEmailLink, signInWithEmailLink } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { useRouter, useSearchParams } from "next/navigation";

export default function FinishSignUpPage() {
  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>('verifying');
  const [error, setError] = useState<string>('');
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    async function completeSignIn() {
      // Check if this is a sign-in link
      if (!isSignInWithEmailLink(auth, window.location.href)) {
        setStatus('error');
        setError('Invalid or expired link. Please request a new magic link.');
        return;
      }

      // Get email from localStorage
      let email = window.localStorage.getItem('emailForSignIn');

      // If missing (user switched devices), ask for it
      if (!email) {
        email = window.prompt('Please provide your email for confirmation') || '';
      }

      if (!email) {
        setStatus('error');
        setError('Email is required to complete sign-in');
        return;
      }

      try {
        // Complete sign-in
        const result = await signInWithEmailLink(auth, email, window.location.href);
        
        // Clear email from storage
        window.localStorage.removeItem('emailForSignIn');
        
        // Get site_id from URL to redirect back properly
        const siteId = searchParams.get('site_id');
        
        setStatus('success');
        
        // Redirect back to embed page after short delay
        setTimeout(() => {
          const redirectUrl = siteId 
            ? `/embed?site_id=${siteId}`
            : '/embed';
          router.push(redirectUrl);
        }, 1500);
        
      } catch (err: any) {
        console.error('Sign-in error:', err);
        setStatus('error');
        setError(err.message || 'Failed to complete sign-in. The link may have expired.');
      }
    }

    completeSignIn();
  }, [router, searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-white">
      <div className="text-center">
        {status === 'verifying' && (
          <>
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#B9965B] mx-auto mb-4"></div>
            <h2 className="text-xl font-heading text-[#B9965B]">Verifying your device...</h2>
          </>
        )}
        
        {status === 'success' && (
          <>
            <svg className="w-16 h-16 mx-auto text-green-500 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <h2 className="text-xl font-heading text-[#B9965B] mb-2">Device Verified!</h2>
            <p className="text-gray-600">Redirecting you to AVA...</p>
          </>
        )}
        
        {status === 'error' && (
          <>
            <svg className="w-16 h-16 mx-auto text-red-500 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
            <h2 className="text-xl font-heading text-red-600 mb-2">Verification Failed</h2>
            <p className="text-gray-600 mb-4">{error}</p>
            <button
              onClick={() => window.location.href = '/embed'}
              className="px-6 py-2 bg-[#B9965B] text-white rounded-lg hover:bg-[#A8854A]"
            >
              Try Again
            </button>
          </>
        )}
      </div>
    </div>
  );
}
```

---

## Additional Critical Fixes

### 1. Race Condition Fix (Webhook Delay)

**Problem**: User buys subscription → WooCommerce redirects immediately to Member Area → Webhook hasn't arrived yet → AVA shows "Subscription Required"

**Solution**: Add retry/polling mechanism on first login

**File**: `voice-assistant-frontend/app/embed/page.tsx`

```typescript
// Add retry logic for subscription check
const checkSubscriptionWithRetry = async (
  backendUrl: string,
  idToken: string,
  maxRetries = 5
): Promise<SubscriptionStatus> => {
  for (let i = 0; i < maxRetries; i++) {
    const response = await fetch(`${backendUrl}/api/check-subscription`, {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${idToken}` }
    });
    
    if (response.ok) {
      return await response.json();
    }
    
    // If subscription not found, wait and retry (webhook might be delayed)
    if (response.status === 404 && i < maxRetries - 1) {
      await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1))); // Exponential backoff
      continue;
    }
    
    throw new Error('Subscription check failed');
  }
  
  throw new Error('Subscription not found after retries');
};

// In handleAuthenticated:
const handleAuthenticated = useCallback(async (user: User) => {
  setFirebaseUser(user);
  
  try {
    const idToken = await user.getIdToken();
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || window.location.origin;
    
    // Show activating state for first login
    setAuthState('activating');
    
    // Check subscription with retry (handles webhook race condition)
    const subscription = await checkSubscriptionWithRetry(backendUrl, idToken);
    
    if (!subscription.allowed) {
      setAuthState('subscription_required');
      setSubscriptionError(subscription.reason || 'Subscription required');
      return;
    }
    
    // Continue with device token creation...
    
  } catch (e) {
    console.error('Subscription check error:', e);
    setAuthState('subscription_required');
    setSubscriptionError('Failed to verify subscription. Please try again or contact support.');
  }
}, [wpContext, notifyParent]);
```

### 2. Safari Third-Party Cookie Fix

**Problem**: Safari blocks third-party cookies by default, breaking httpOnly cookie storage

**Solution**: Storage Access API fallback

**File**: `voice-assistant-frontend/components/CookieConsent.tsx`

```typescript
"use client";

import { useState, useEffect } from "react";

export function useStorageAccess() {
  const [hasStorageAccess, setHasStorageAccess] = useState<boolean | null>(null);
  const [isRequesting, setIsRequesting] = useState(false);

  useEffect(() => {
    // Check if we have storage access
    if (typeof document !== 'undefined' && 'hasStorageAccess' in document) {
      (document as any).hasStorageAccess().then(setHasStorageAccess);
    } else {
      // Browser doesn't support Storage Access API (not Safari)
      setHasStorageAccess(true);
    }
  }, []);

  const requestAccess = async (): Promise<boolean> => {
    if (typeof document === 'undefined' || !('requestStorageAccess' in document)) {
      return true; // Not Safari or not supported
    }

    setIsRequesting(true);
    try {
      await (document as any).requestStorageAccess();
      setHasStorageAccess(true);
      return true;
    } catch (err) {
      console.error('Storage access denied:', err);
      setHasStorageAccess(false);
      return false;
    } finally {
      setIsRequesting(false);
    }
  };

  return { hasStorageAccess, isRequesting, requestAccess };
}

// Usage in embed page:
export default function EmbedPage() {
  // ... existing code ...
  const { hasStorageAccess, isRequesting, requestAccess } = useStorageAccess();
  const [needsCookieConsent, setNeedsCookieConsent] = useState(false);

  useEffect(() => {
    // Detect if cookies are blocked
    if (hasStorageAccess === false) {
      setNeedsCookieConsent(true);
    }
  }, [hasStorageAccess]);

  if (needsCookieConsent) {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-center p-8">
          <h2 className="text-2xl font-heading text-[#B9965B] mb-4">Enable Cookies for AVA</h2>
          <p className="text-gray-600 mb-6">
            Your browser is blocking third-party cookies. Please click below to enable secure login.
          </p>
          <button
            onClick={async () => {
              const granted = await requestAccess();
              if (granted) {
                setNeedsCookieConsent(false);
                // Retry authentication
                window.location.reload();
              }
            }}
            disabled={isRequesting}
            className="px-6 py-3 bg-[#B9965B] text-white rounded-lg hover:bg-[#A8854A] disabled:opacity-50"
          >
            {isRequesting ? 'Requesting...' : 'Enable Secure Login'}
          </button>
        </div>
      </div>
    );
  }
  
  // ... rest of component
}
```

### 3. Email Change Synchronization

**Problem**: User changes email in WordPress → AVA still has old email → Login fails

**Solution**: WordPress hook to notify AVA of email changes

**File**: `ava-wordpress-plugin/ava-subscription.php`

```php
/**
 * Handle email changes in WordPress profile
 */
public function __construct() {
    // ... existing hooks ...
    
    // Email change synchronization
    add_action('profile_update', [$this, 'handle_email_change'], 10, 2);
}

/**
 * Handle user email change
 */
public function handle_email_change($user_id, $old_user_data) {
    $new_user_data = get_userdata($user_id);
    
    // FIX: Normalize both emails to lowercase for comparison
    $old_email = strtolower($old_user_data->user_email);
    $new_email = strtolower($new_user_data->user_email);
    
    if ($old_email !== $new_email) {
        // Email changed! Notify AVA backend
        $this->notify_ava_backend('email_changed', [
            'wpUserId' => $user_id,
            'oldEmail' => $old_email,
            'newEmail' => $new_email,
            'displayName' => $new_user_data->display_name
        ]);
    }
}
```

**File**: `token-server-node/src/webhooks.ts` (Add email change handler)

```typescript
// In handleSubscriptionWebhook, add case for 'email_changed':
case 'email_changed': {
  const { oldEmail, newEmail } = data;
  
  // Find user by old email
  const oldUserSnapshot = await db.collection('users')
    .where('email', '==', oldEmail.toLowerCase())
    .where('wpSiteId', '==', siteId)
    .limit(1)
    .get();
  
  if (!oldUserSnapshot.empty) {
    const userDoc = oldUserSnapshot.docs[0];
    
    // Update email in Firestore
    await userDoc.ref.update({
      email: newEmail.toLowerCase(),
      updatedAt: new Date()
    });
    
    console.log(`Updated email from ${oldEmail} to ${newEmail}`);
  }
  break;
}
```

---

## Complete Flow Summary

### 1. Purchase Flow
```
Customer buys in WooCommerce
    ↓
WP creates user account
    ↓
WP sends secure "Set password" email (wp_new_user_notification)
    ↓
WP webhook → AVA backend
    ↓
AVA creates Firestore subscription record (NO Firebase Auth user)
    ↓
Customer can access AVA page
```

### 2. First AVA Login (Magic Link)
```
Customer clicks "Open AVA" on WP
    ↓
WP verifies subscription, embeds AVA with user_email
    ↓
AVA: "No device token found"
    ↓
AVA shows: "Send Magic Link to alice@example.com"
    ↓
User clicks button → Magic Link sent
    ↓
User clicks link in email (same device)
    ↓
Firebase Auth user created JIT
    ↓
AVA checks subscription in Firestore
    ↓
Active → Device token created (30 days) → Chat starts
```

### 3. Return Visit (Silent)
```
Customer returns to AVA page
    ↓
WP verifies subscription
    ↓
AVA finds device token (httpOnly cookie)
    ↓
Silent login, chat starts immediately
```

### 4. Expiry Flow
```
Subscription expires in WooCommerce
    ↓
WP webhook → AVA backend
    ↓
AVA updates Firestore: status = 'expired'
    ↓
Existing chat: User can finish
    ↓
New chat: Blocked with renewal message
```

---

## Implementation Checklist

### Phase 1: WordPress Plugin
- [ ] Remove `provisionFirebaseUser()` equivalent
- [ ] Replace plaintext password email with `wp_new_user_notification()`
- [ ] Add Resync button to admin settings
- [ ] Pass `user_email` to iframe embed
- [ ] Test webhook firing on purchase/renewal/expiry

### Phase 2: AVA Backend
- [ ] Update webhook to NOT create Firebase Auth users
- [ ] Create Firestore subscription record only
- [ ] Handle JIT user linking on first login
- [ ] Implement subscription check endpoints

### Phase 3: AVA Frontend
- [ ] Create `MagicLinkAuth.tsx` component
- [ ] Create `/embed/finishSignUp` page
- [ ] Update embed page to pass user_email from WP
- [ ] Handle Magic Link flow (send → check inbox → verify)
- [ ] Test all subscription states

### Phase 4: Testing
- [ ] Test purchase → webhook → Firestore record
- [ ] Test first login with Magic Link
- [ ] Test return visit with device token
- [ ] Test expired subscription handling
- [ ] Test resync functionality
- [ ] Test "same device" Magic Link requirement
- [ ] Test webhook race condition (immediate redirect after purchase)
- [ ] Test email case sensitivity (JohnDoe@example.com vs johndoe@example.com)
- [ ] Test Safari third-party cookie blocking
- [ ] Test email change synchronization
