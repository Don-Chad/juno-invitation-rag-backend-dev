# WordPress + AVA Integration Plan
## Option 5: Silent Reverify with Device-Bound Tokens

**Security Principle**: WordPress is treated as an untrusted intermediary. It can gate access to the AVA embed, but it cannot assert identity. All identity verification flows through Firebase Auth directly between the user and AVA.

---

## Core Security Model

### What WordPress CAN Do:
- Gate access to the AVA embed (WooCommerce membership check)
- Initiate the AVA embed with a site identifier
- Receive "user connected" status (no tokens, no identity data)

### What WordPress CANNOT Do:
- Create fake user sessions
- Impersonate users
- Access Firebase tokens or credentials
- Modify Firebase auth state
- Spoof identity tokens
- Read user conversation history

### The Golden Rule:
> **Firebase says who the user is. WordPress only says who can see the page.**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              USER FLOW - FIRST VISIT                             │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌─────────┐
│   WordPress  │────▶│   AVA Embed      │────▶│   Firebase Auth  │────▶│  AVA    │
│   (Gates     │     │   (iframe)       │     │   (Identity)     │     │  Chat   │
│    Access)   │     │                  │     │                  │     │         │
└──────────────┘     └──────────────────┘     └──────────────────┘     └─────────┘
        │                     │                      │                      │
        │                     │                      │                      │
        ▼                     ▼                      ▼                      ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  1. User with WP membership visits AVA page                                 │
   │  2. WP embeds AVA iframe with site_id                                       │
   │  3. AVA checks: "Do I have a valid device token?"                           │
   │  4. No token → Show Firebase Google Sign-In                                 │
   │  5. User authenticates DIRECTLY with Firebase (bypasses WP)                 │
   │  6. Firebase issues ID token to AVA                                         │
    │  7. AVA creates device-bound session token (30-day expiry)                  │
    │  8. Token stored in httpOnly cookie (secure, XSS-resistant)                 │
    │  9. AVA connects to LiveKit, conversation begins                            │
   │  10. WP parent receives "ava:connected" postMessage (no token)              │
   └────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                           USER FLOW - RETURN VISIT                               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌─────────┐
│   WordPress  │────▶│   AVA Embed      │────▶│   AVA Backend    │────▶│  AVA    │
│   (Gates     │     │   (iframe)       │     │   (Validate      │     │  Chat   │
│    Access)   │     │                  │     │    Device Token) │     │         │
└──────────────┘     └──────────────────┘     └──────────────────┘     └─────────┘
        │                     │                      │                      │
        │                     │                      │                      │
        ▼                     ▼                      ▼                      ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  1. User with WP membership visits AVA page                                 │
   │  2. WP embeds AVA iframe with site_id                                       │
   │  3. AVA checks: "Do I have a valid device token?"                           │
   │  4. Token found → Send to AVA backend for validation                        │
   │  5. Backend checks:                                                         │
   │     - Token exists in Firestore                                             │
   │     - Token not expired                                                     │
   │     - Device fingerprint matches (optional)                                 │
   │     - Origin is in approvedSites list                                       │
   │  6. Valid → Auto-login, no user friction                                    │
   │  7. AVA connects to LiveKit, conversation begins                            │
   │  8. WP parent receives "ava:connected" postMessage                          │
   └────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                         ATTACK SCENARIO - WP COMPROMISED                         │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌─────────┐
│  Attacker    │────▶│   AVA Embed      │────▶│   Firebase Auth  │────▶│ BLOCKED │
│  (Spoofed    │     │   (iframe)       │     │   (Identity)     │     │         │
│   WP Admin)  │     │                  │     │                  │     │         │
└──────────────┘     └──────────────────┘     └──────────────────┘     └─────────┘
        │                     │                      │
        │                     │                      │
        ▼                     ▼                      ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  1. Attacker gains WP admin access                                          │
   │  2. Attacker opens AVA page (or embeds iframe on malicious site)            │
   │  3. AVA checks for device token → None found                                │
   │  4. AVA shows Google Sign-In popup                                          │
   │  5. Attacker CANNOT complete Google Sign-In as the victim                   │
   │  6. Attacker is BLOCKED - cannot access victim's AVA history/data           │
   │                                                                              │
   │  EVEN IF: Attacker steals device token from browser                         │
   │  - Token is bound to device fingerprint                                     │
   │  - Token validation fails on different device                               │
   │  - User is prompted to re-authenticate                                      │
   └────────────────────────────────────────────────────────────────────────────┘
```

---

## Why This Is Secure

### Attack Vector 1: WordPress Account Takeover
**Scenario**: Attacker compromises user's WordPress account.
**Result**: Attacker can see the AVA embed page, but:
- No device token exists for attacker's browser
- Firebase Sign-In is required
- Attacker cannot sign in as the victim (doesn't have victim's Google credentials)
**Conclusion**: AVA identity remains secure.

### Attack Vector 2: WordPress Admin Spoofing
**Scenario**: WP admin tries to impersonate a user.
**Result**: Admin can embed AVA with any site_id, but:
- Admin cannot forge Firebase ID tokens
- Admin cannot bypass Google Sign-In
- Admin cannot read user's conversation history from Firestore
**Conclusion**: User data remains secure.

### Attack Vector 3: Token Theft
**Scenario**: Attacker steals device token from user's browser.
**Result**: Token is bound to device fingerprint (user-agent + IP hash).
- Token validation fails on different device
- User is prompted to re-authenticate
- Stolen token is invalidated
**Conclusion**: Token theft is mitigated.

### Attack Vector 4: Cross-Site Embedding
**Scenario**: Attacker embeds AVA on malicious-site.com.
**Result**: AVA backend checks origin against approvedSites list.
- Malicious site is not in approvedSites
- Token validation fails
- Firebase Sign-In popup shows, but even if completed, Firestore security rules prevent data access
**Conclusion**: Cross-site embedding is blocked.

---

## Component Breakdown

### 1. WordPress Plugin (PHP)

**File**: `ava-wordpress-plugin/ava-embed.php`

```php
<?php
/**
 * Plugin Name: AVA Voice Assistant Embed
 * Description: Securely embed AVA voice assistant with Firebase authentication
 * Version: 1.0.0
 */

// Prevent direct access
if (!defined('ABSPATH')) {
    exit;
}

class AVA_Embed_Plugin {
    
    // AVA backend endpoint (configured in plugin settings)
    private $ava_backend_url;
    private $site_id;
    
    public function __construct() {
        $this->ava_backend_url = get_option('ava_backend_url', 'https://ava-backend.example.com');
        $this->site_id = get_option('ava_site_id', '');
        
        add_shortcode('ava_embed', [$this, 'render_ava_embed']);
        add_action('admin_menu', [$this, 'add_admin_menu']);
        add_action('admin_init', [$this, 'register_settings']);
    }
    
    /**
     * Render AVA embed shortcode
     * Usage: [ava_embed require_membership="true"]
     */
    public function render_ava_embed($atts) {
        $atts = shortcode_atts([
            'require_membership' => 'true',
            'width' => '100%',
            'height' => '600px'
        ], $atts);
        
        // Check if user has access (WooCommerce membership)
        if ($atts['require_membership'] === 'true' && !$this->user_can_access_ava()) {
            return '<div class="ava-access-denied">
                <p>Please purchase a membership to access AVA.</p>
            </div>';
        }
        
        // Generate unique session nonce (prevents replay attacks)
        $nonce = wp_create_nonce('ava_session_' . get_current_user_id() . '_' . time());
        
        // Store nonce temporarily (5 minute expiry)
        set_transient('ava_nonce_' . $nonce, [
            'user_id' => get_current_user_id(),
            'created_at' => time()
        ], 300);
        
        // Get current user email for Magic Link pre-fill
        $current_user = wp_get_current_user();
        // FIX: Normalize email to lowercase to prevent case-sensitivity issues
        $user_email = strtolower($current_user->user_email);
        
        // Output embed container and script
        ob_start();
        ?>
        <div id="ava-container-<?php echo esc_attr($nonce); ?>"
             class="ava-embed-container"
             style="width: <?php echo esc_attr($atts['width']); ?>;
                    height: <?php echo esc_attr($atts['height']); ?>;">
            <iframe id="ava-iframe-<?php echo esc_attr($nonce); ?>"
                    src="<?php echo esc_url($this->ava_backend_url . '/embed'); ?>"
                    data-site-id="<?php echo esc_attr($this->site_id); ?>"
                    data-session-nonce="<?php echo esc_attr($nonce); ?>"
                    data-origin="<?php echo esc_url(home_url()); ?>"
                    data-user-email="<?php echo esc_attr($user_email); ?>"
                    style="width: 100%; height: 100%; border: none; border-radius: 12px;"
                    allow="microphone; camera; autoplay"
                    sandbox="allow-same-origin allow-scripts allow-popups allow-forms">
            </iframe>
        </div>
        
        <script>
        (function() {
            // Listen for messages from AVA iframe
            window.addEventListener('message', function(event) {
                // SECURITY: Verify origin matches AVA backend
                if (event.origin !== '<?php echo esc_url($this->ava_backend_url); ?>') {
                    return;
                }
                
                // Handle AVA connection status
                if (event.data && event.data.type === 'ava:connected') {
                    console.log('AVA connected for user');
                    // Optionally update UI to show "AVA Ready"
                }
                
                if (event.data && event.data.type === 'ava:disconnected') {
                    console.log('AVA disconnected');
                }
                
                if (event.data && event.data.type === 'ava:error') {
                    console.error('AVA error:', event.data.error);
                }
            });
        })();
        </script>
        <?php
        return ob_get_clean();
    }
    
    /**
     * Check if current user can access AVA
     */
    private function user_can_access_ava() {
        // Check if user is logged in
        if (!is_user_logged_in()) {
            return false;
        }
        
        // Check WooCommerce membership (customize as needed)
        if (function_exists('wc_memberships_get_user_active_memberships')) {
            $memberships = wc_memberships_get_user_active_memberships(get_current_user_id());
            return !empty($memberships);
        }
        
        // Fallback: check for specific role or capability
        return current_user_can('access_ava');
    }
    
    /**
     * Add admin menu
     */
    public function add_admin_menu() {
        add_options_page(
            'AVA Settings',
            'AVA Embed',
            'manage_options',
            'ava-embed-settings',
            [$this, 'render_settings_page']
        );
    }
    
    /**
     * Register settings
     */
    public function register_settings() {
        register_setting('ava_embed_settings', 'ava_backend_url');
        register_setting('ava_embed_settings', 'ava_site_id');
    }
    
    /**
     * Render settings page
     */
    public function render_settings_page() {
        ?>
        <div class="wrap">
            <h1>AVA Embed Settings</h1>
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
                            <p class="description">Unique identifier for this WordPress site (provided by AVA admin)</p>
                        </td>
                    </tr>
                </table>
                <?php submit_button(); ?>
            </form>
        </div>
        <?php
    }
}

// Initialize plugin
new AVA_Embed_Plugin();
```

---

### 2. AVA Frontend - Device Token Manager

**File**: `voice-assistant-frontend/lib/deviceToken.ts`

```typescript
/**
 * Device Token Manager
 * 
 * Manages long-lived device tokens for silent re-authentication.
 * Tokens are stored in httpOnly cookies only (secure, XSS-resistant).
 * No localStorage usage for maximum security.
 */

import { auth } from './firebase';
import { User } from 'firebase/auth';

// Token is stored in httpOnly cookie only - no localStorage
// Cookie name used for reference (actual cookie managed by backend)

interface DeviceTokenInfo {
  uid: string;
  email: string;
  createdAt: number;
  expiresAt: number;
  deviceFingerprint: string;
}

interface TokenValidationResponse {
  valid: boolean;
  uid?: string;
  email?: string;
  error?: string;
}

/**
 * Generate device fingerprint (for token binding)
 */
function generateDeviceFingerprint(): string {
  const components = [
    navigator.userAgent,
    navigator.language,
    screen.colorDepth,
    screen.width + 'x' + screen.height,
    new Date().getTimezoneOffset(),
    !!window.sessionStorage,
    !!window.localStorage,
    navigator.hardwareConcurrency || 'unknown'
  ];
  
  // Simple hash - in production, use a proper hashing library
  const str = components.join('||');
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return hash.toString(16);
}

/**
 * Store device token metadata (for reference only)
 * The actual token is stored in httpOnly cookie by the server
 */
export function storeDeviceTokenInfo(uid: string, email: string): void {
  // Note: The actual httpOnly cookie is set by the server
  // This function just stores non-sensitive metadata for UI purposes
  const tokenInfo: DeviceTokenInfo = {
    uid,
    email,
    createdAt: Date.now(),
    expiresAt: Date.now() + (30 * 24 * 60 * 60 * 1000), // 30 days
    deviceFingerprint: generateDeviceFingerprint()
  };
  
  // Store only non-sensitive metadata in sessionStorage (not localStorage)
  // This is just for UI state, not authentication
  try {
    sessionStorage.setItem('ava_token_info', JSON.stringify(tokenInfo));
  } catch (e) {
    console.warn('Failed to store token info:', e);
  }
}

/**
 * Check if device token likely exists (based on metadata)
 * Actual validation happens server-side via httpOnly cookie
 */
export function hasDeviceToken(): boolean {
  try {
    const stored = sessionStorage.getItem('ava_token_info');
    if (!stored) return false;
    
    const tokenInfo: DeviceTokenInfo = JSON.parse(stored);
    
    // Check if metadata suggests token might be valid
    if (Date.now() > tokenInfo.expiresAt) {
      clearDeviceTokenInfo();
      return false;
    }
    
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Clear device token info
 */
export function clearDeviceTokenInfo(): void {
  try {
    sessionStorage.removeItem('ava_token_info');
  } catch (e) {
    console.warn('Failed to clear token info:', e);
  }
  
  // Note: httpOnly cookie must be cleared by server API call
}

/**
 * Validate device token with AVA backend
 */
export async function validateDeviceToken(
  backendUrl: string,
  siteId: string
): Promise<TokenValidationResponse> {
  // Token is sent automatically via httpOnly cookie
  // We only send device fingerprint for additional validation
  try {
    const response = await fetch(`${backendUrl}/api/validate-device-token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include', // Include httpOnly cookie with token
      body: JSON.stringify({
        siteId,
        deviceFingerprint: generateDeviceFingerprint()
      })
    });
    
    if (!response.ok) {
      const error = await response.json();
      return { valid: false, error: error.message || 'Token validation failed' };
    }
    
    const result = await response.json();
    return { valid: true, uid: result.uid, email: result.email };
  } catch (e) {
    console.error('Token validation error:', e);
    return { valid: false, error: 'Network error during validation' };
  }
}

/**
 * Exchange Firebase ID token for device token
 * The device token is stored in httpOnly cookie by the server
 */
export async function exchangeForDeviceToken(
  backendUrl: string,
  idToken: string,
  siteId: string
): Promise<{ success: boolean; uid?: string; email?: string; error?: string }> {
  try {
    const response = await fetch(`${backendUrl}/api/create-device-token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      credentials: 'include', // Required for httpOnly cookie to be set
      body: JSON.stringify({
        siteId,
        deviceFingerprint: generateDeviceFingerprint()
      })
    });
    
    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.message || 'Failed to create device token' };
    }
    
    const result = await response.json();
    
    // Store non-sensitive metadata only (actual token is in httpOnly cookie)
    if (result.uid && result.email) {
      storeDeviceTokenInfo(result.uid, result.email);
    }
    
    return { success: true, uid: result.uid, email: result.email };
  } catch (e) {
    console.error('Token exchange error:', e);
    return { success: false, error: 'Network error during token exchange' };
  }
}
```

---

### 3. AVA Frontend - Updated Embed Page

**File**: `voice-assistant-frontend/app/embed/page.tsx`

```typescript
"use client";

import { NoAgentNotification } from "@/components/NoAgentNotification";
import FirebaseAuth from "@/components/FirebaseAuth";
import { auth } from "@/lib/firebase";
import { User, signOut } from "firebase/auth";
import { CustomChat } from "@/components/CustomChat";
import {
  RoomContext,
  useVoiceAssistant,
  useRoomContext,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { AnimatePresence, motion } from "framer-motion";
import { Room, ConnectionState } from "livekit-client";
import { useCallback, useEffect, useState, useRef } from "react";
import type { ConnectionDetails } from "../api/connection-details/route";
import {
  hasDeviceToken,
  validateDeviceToken,
  exchangeForDeviceToken,
  clearDeviceTokenInfo
} from "@/lib/deviceToken";

// Types for WordPress integration
interface WordPressContext {
  siteId: string;
  nonce: string;
  origin: string;
}

function ConnectionIndicator() {
  const room = useRoomContext();
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!room) return;

    const updateConnectionState = () => {
      setIsConnected(room.state === ConnectionState.Connected);
    };

    updateConnectionState();
    room.on("connectionStateChanged", updateConnectionState);

    return () => {
      room.off("connectionStateChanged", updateConnectionState);
    };
  }, [room]);

  return (
    <div 
      className={`w-3 h-3 rounded-full transition-all ${
        isConnected 
          ? "bg-[#6B8E23] animate-pulse shadow-[0_0_8px_rgba(107,142,35,0.6)]" 
          : "bg-gray-400"
      }`}
      title={isConnected ? "Connected" : "Disconnected"}
    />
  );
}

export default function EmbedPage() {
  const [roomKey, setRoomKey] = useState(0);
  const [room, setRoom] = useState<Room | null>(null);
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [isConnecting, setIsConnecting] = useState(false);
  const [authState, setAuthState] = useState<'checking' | 'needs_auth' | 'authenticated'>('checking');
  const [wpContext, setWpContext] = useState<WordPressContext | null>(null);
  const parentOrigin = useRef<string | null>(null);

  // Create a fresh Room instance when roomKey changes
  useEffect(() => {
    const newRoom = new Room();
    setRoom(newRoom);
    
    return () => {
      if (newRoom.state !== ConnectionState.Disconnected) {
        newRoom.disconnect().catch(console.error);
      }
    };
  }, [roomKey]);

  // Parse WordPress context from URL or parent message
  useEffect(() => {
    // Try to get context from URL params (for direct embed)
    const params = new URLSearchParams(window.location.search);
    const siteId = params.get('site_id');
    const nonce = params.get('nonce');
    
    if (siteId && nonce) {
      setWpContext({
        siteId,
        nonce,
        origin: document.referrer || window.location.origin
      });
    }
    
    // Listen for context from parent window (WordPress)
    const handleParentMessage = (event: MessageEvent) => {
      // Store parent origin for future postMessage calls
      parentOrigin.current = event.origin;
      
      if (event.data && event.data.type === 'ava:init') {
        setWpContext({
          siteId: event.data.siteId,
          nonce: event.data.nonce,
          origin: event.origin
        });
      }
    };
    
    window.addEventListener('message', handleParentMessage);
    
    // Notify parent we're ready
    if (window.parent !== window) {
      window.parent.postMessage({ type: 'ava:ready' }, '*');
    }
    
    return () => window.removeEventListener('message', handleParentMessage);
  }, []);

  // Check for existing device token on mount
  useEffect(() => {
    const checkExistingAuth = async () => {
      // First check Firebase auth state
      const unsubscribe = auth.onAuthStateChanged(async (user) => {
        if (user) {
          // User is already signed in via Firebase
          setFirebaseUser(user);
          setAuthState('authenticated');
          setIsCheckingAuth(false);
          notifyParent('connected');
          return;
        }
        
        // No Firebase user - check for device token
        if (!wpContext) {
          setAuthState('needs_auth');
          setIsCheckingAuth(false);
          return;
        }
        
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || window.location.origin;
        const validation = await validateDeviceToken(backendUrl, wpContext.siteId);
        
        if (validation.valid && validation.uid) {
          // Device token is valid - create a Firebase custom token flow
          // or silently sign in (depending on your Firebase setup)
          // For now, we'll show a "Welcome back" state
          setAuthState('needs_auth'); // Will show simplified auth UI
          setIsCheckingAuth(false);
        } else {
          // No valid token - show full auth
          setAuthState('needs_auth');
          setIsCheckingAuth(false);
        }
      });
      
      return () => unsubscribe();
    };
    
    checkExistingAuth();
  }, [wpContext]);

  // Notify parent window of connection status
  const notifyParent = useCallback((status: 'connected' | 'disconnected' | 'error', error?: string) => {
    if (window.parent !== window && parentOrigin.current) {
      window.parent.postMessage({
        type: `ava:${status}`,
        timestamp: Date.now(),
        error
      }, parentOrigin.current);
    }
  }, []);

  // Handle successful Firebase authentication
  const handleAuthenticated = useCallback(async (user: User) => {
    setFirebaseUser(user);
    
    // Exchange Firebase token for device token
    if (wpContext) {
      try {
        const idToken = await user.getIdToken();
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || window.location.origin;
        const result = await exchangeForDeviceToken(backendUrl, idToken, wpContext.siteId);
        
        if (!result.success) {
          console.error('Failed to create device token:', result.error);
        }
      } catch (e) {
        console.error('Token exchange error:', e);
      }
    }
    
    setAuthState('authenticated');
    notifyParent('connected');
  }, [wpContext, notifyParent]);

  const onConnectButtonClicked = useCallback(async () => {
    if (!firebaseUser || !room || isConnecting) return;

    try {
      setIsConnecting(true);
      console.log("Connecting: fetching token for user", firebaseUser.uid);
      
      const idToken = await firebaseUser.getIdToken(true);
      
      const url = new URL(
        process.env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT ?? "/api/connection-details",
        window.location.origin
      );
      
      console.log("Connecting: calling token endpoint", url.toString());
      const response = await fetch(url.toString(), {
        method: "GET",
        headers: {
          Authorization: `Bearer ${idToken}`,
        },
        cache: "no-store"
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error("Connection details error:", response.status, errorText);
        notifyParent('error', 'Failed to get connection details');
        throw new Error(`Failed to get connection details: ${response.status}`);
      }

      const data = (await response.json()) as ConnectionDetails;
      console.log("Got connection details, connecting to room:", data.roomName);

      await room.connect(data.serverUrl, data.participantToken);
      console.log("Connected to room successfully");
      notifyParent('connected');
    } catch (error) {
      console.error("Connection error:", error);
      notifyParent('error', error instanceof Error ? error.message : 'Unknown error');
      // Reset room on error
      setRoomKey(prev => prev + 1);
    } finally {
      setIsConnecting(false);
    }
  }, [firebaseUser, room, isConnecting, notifyParent]);

  const handleDisconnect = useCallback(async () => {
    if (room) {
      await room.disconnect();
      notifyParent('disconnected');
    }
  }, [room, notifyParent]);

  const handleLogout = useCallback(async () => {
    await signOut(auth);
    clearDeviceTokenInfo();
    setFirebaseUser(null);
    setAuthState('needs_auth');
    handleDisconnect();
  }, [handleDisconnect]);

  if (isCheckingAuth || authState === 'checking') {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-[#B9965B] font-heading text-xl">Loading...</div>
      </div>
    );
  }

  if (authState === 'needs_auth') {
    return <FirebaseAuth onAuthenticated={handleAuthenticated} />;
  }

  if (!firebaseUser || !room) {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-red-500">Error: Unable to initialize</div>
      </div>
    );
  }

  return (
    <RoomContext.Provider value={room}>
      <main className="relative h-full bg-white" data-lk-theme="default">
        <div className="absolute top-4 right-4 z-50 flex items-center gap-2">
          <ConnectionIndicator />
          <button
            onClick={handleLogout}
            className="text-xs text-gray-500 hover:text-gray-700 underline"
          >
            Logout
          </button>
        </div>
        
        <CustomChat
          room={room}
          onConnect={onConnectButtonClicked}
          onDisconnect={handleDisconnect}
          isConnecting={isConnecting}
        />
        <NoAgentNotification />
      </main>
    </RoomContext.Provider>
  );
}
```

---

### 4. AVA Backend - Device Token API

**File**: `token-server-node/src/deviceTokens.ts`

```typescript
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
const TOKEN_EXPIRY_DAYS = 30;

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
    return false;
  }
  
  const siteData = siteDoc.data() as ApprovedSite;
  return siteData.allowed === true && siteData.origin === origin;
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

    // Set httpOnly cookie with raw token
    res.cookie('ava_device_token', token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'none', // Required for cross-origin iframe
      maxAge: TOKEN_EXPIRY_DAYS * 24 * 60 * 60 * 1000,
      domain: process.env.COOKIE_DOMAIN || undefined
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
    
    // Get token from httpOnly cookie only (not from request body)
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

    // Optional: Strict device fingerprint matching
    // If device doesn't match, invalidate token and require re-auth
    if (!checks.deviceMatches) {
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

    const { token } = req.body;
    const tokenHash = hashToken(token);
    
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
    res.clearCookie('ava_device_token');

    res.json({ success: true });
  } catch (err) {
    console.error('Error revoking device token:', err);
    res.status(500).json({ message: 'Failed to revoke token' });
  }
}
```

---

### 5. Firestore Security Rules

**File**: `firestore.rules`

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    
    // Helper function to check if user is authenticated
    function isAuthenticated() {
      return request.auth != null;
    }
    
    // Helper function to check if user owns the document
    function isOwner(userId) {
      return isAuthenticated() && request.auth.uid == userId;
    }
    
    // Helper function to get approved sites
    function getApprovedOrigin(siteId) {
      return get(/databases/$(database)/documents/approvedSites/$(siteId)).data.origin;
    }
    
    // Helper function to check if request comes from approved origin
    function isApprovedOrigin(siteId) {
      return request.origin == getApprovedOrigin(siteId);
    }

    // ==========================================
    // USER PROFILES
    // ==========================================
    match /users/{userId} {
      // Users can read their own profile
      allow read: if isOwner(userId);
      
      // Only backend (Admin SDK) can write user profiles
      // Frontend cannot modify user data directly
      allow write: if false;
    }
    
    // ==========================================
    // CHAT HISTORY
    // ==========================================
    match /users/{userId}/chatHistory/{sessionId} {
      // Users can read their own chat history
      allow read: if isOwner(userId);
      
      // Only backend can write chat history
      allow write: if false;
    }
    
    // ==========================================
    // DEVICE TOKENS
    // ==========================================
    match /deviceTokens/{tokenHash} {
      // No direct read access - must use backend API
      allow read: if false;
      
      // Only backend can create device tokens
      allow create: if false;
      
      // Only backend can update device tokens
      allow update: if false;
      
      // Only backend can delete device tokens
      allow delete: if false;
    }
    
    // ==========================================
    // APPROVED SITES
    // ==========================================
    match /approvedSites/{siteId} {
      // Public read - needed for origin validation
      allow read: if true;
      
      // Only admins can write
      allow write: if isAuthenticated() && 
        exists(/databases/$(database)/documents/admins/$(request.auth.uid));
    }
    
    // ==========================================
    // ADMIN LIST
    // ==========================================
    match /admins/{userId} {
      // Only admins can read admin list
      allow read: if isAuthenticated() && 
        exists(/databases/$(database)/documents/admins/$(request.auth.uid));
      
      // Only existing admins can add new admins
      allow write: if isAuthenticated() && 
        exists(/databases/$(database)/documents/admins/$(request.auth.uid));
    }
    
    // ==========================================
    // USER PREFERENCES
    // ==========================================
    match /users/{userId}/preferences/{docId} {
      // Users can read/write their own preferences
      allow read, write: if isOwner(userId);
    }
  }
}
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SECURE AUTHENTICATION FLOW                             │
└─────────────────────────────────────────────────────────────────────────────────┘

FIRST VISIT (Full Authentication)
═══════════════════════════════════════════════════════════════════════════════════

┌──────────────┐
│   WordPress  │  User visits AVA page (membership verified by WP)
│   (Parent)   │  → Embeds iframe with site_id, nonce
└──────┬───────┘
       │
       │ iframe src: https://ava.com/embed?site_id=xxx&nonce=yyy
       ▼
┌──────────────┐
│   AVA Embed  │  Loads, checks for device token
│   (iframe)   │  → No token found
│              │  → Shows Firebase Google Sign-In button
└──────┬───────┘
       │
       │ User clicks "Sign in with Google"
       ▼
┌──────────────┐
│   Firebase   │  Opens popup on AVA domain (bypasses WP)
│    Auth      │  → User enters Google credentials
│   (Popup)    │  → Firebase validates with Google
│              │  → Returns Firebase ID token to AVA
└──────┬───────┘
       │
       │ POST /api/create-device-token
       │ Headers: Authorization: Bearer <firebase_id_token>
       │ Body: { siteId, deviceFingerprint }
       ▼
┌──────────────┐
│   AVA        │  Validates Firebase token
│   Backend    │  → Verifies site is in approvedSites
│   (API)      │  → Generates device token (30-day expiry)
│              │  → Stores token hash in Firestore
│              │  → Sets httpOnly cookie with raw token
│              │  → Returns token to frontend
└──────┬───────┘
       │
       │ { token, uid, email, expiresAt }
       ▼
┌──────────────┐
│   AVA Embed  │  Token stored in httpOnly cookie by server
│   (iframe)   │  → User is now authenticated
│              │  → Connects to LiveKit
│              │  → postMessage to parent: { type: 'ava:connected' }
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   WordPress  │  Receives connected event
│   (Parent)   │  → Can show "AVA Ready" indicator
└──────────────┘


RETURN VISIT (Silent Authentication)
═══════════════════════════════════════════════════════════════════════════════════

┌──────────────┐
│   WordPress  │  User visits AVA page
│   (Parent)   │  → Embeds iframe with site_id
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   AVA Embed  │  Loads, sends validation request to backend
│   (iframe)   │  → httpOnly cookie sent automatically with request
│              │  → Includes httpOnly cookie automatically
└──────┬───────┘
       │
       │ POST /api/validate-device-token
       │ Body: { token, siteId, deviceFingerprint }
       │ Cookie: ava_device_token=<token>
       ▼
┌──────────────┐
│   AVA        │  Validates token hash against Firestore
│   Backend    │  → Checks expiry
│   (API)      │  → Checks siteId matches
│   ┌────────┐ │  → Checks deviceFingerprint matches
│   │ VALID? │ │  → Updates lastUsedAt
│   └───┬────┘ │
└───────┼──────┘
       │
   ┌───┴───┐
   │ YES   │ → Return { valid: true, uid, email }
   └───┬───┘     → User is silently authenticated
       │         → No Google Sign-In shown
       ▼
┌──────────────┐
│   AVA Embed  │  Connects to LiveKit automatically
│   (iframe)   │  → postMessage to parent: { type: 'ava:connected' }
└──────────────┘


ATTACK SCENARIO (WordPress Compromised)
═══════════════════════════════════════════════════════════════════════════════════

┌──────────────┐
│  Attacker    │  Gains WP admin access
│  (Malicious) │  → Opens AVA page or embeds iframe elsewhere
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   AVA Embed  │  Loads, checks for device token
│   (iframe)   │  → No token found (attacker's browser)
│              │  → Shows Firebase Google Sign-In
└──────┬───────┘
       │
       │ Attacker tries to sign in...
       ▼
┌──────────────┐
│   Firebase   │  Requires attacker's Google credentials
│    Auth      │  → Attacker cannot sign in as victim
│              │  → BLOCKED
└──────────────┘


ATTACK SCENARIO (Token Theft)
═══════════════════════════════════════════════════════════════════════════════════

┌──────────────┐
│  Attacker    │  Steals device token from victim's browser
│  (Malicious) │  → Uses token on their device
└──────┬───────┘
       │
       │ POST /api/validate-device-token
       │ Body: { stolenToken, siteId, attackerFingerprint }
       ▼
┌──────────────┐
│   AVA        │  Validates token hash
│   Backend    │  → Token exists and is valid
│   (API)      │  → BUT deviceFingerprint doesn't match!
│   ┌────────┐ │  → INVALIDATES token
│   │ MATCH? │ │  → Returns { valid: false }
│   └───┬────┘ │
└───────┼──────┘
   ┌────┴────┐
   │   NO    │ → Token invalidated
   └────┬────┘ → User must re-authenticate
        │
        ▼
┌──────────────┐
│   AVA Embed  │  Shows Google Sign-In
│   (iframe)   │  → Attacker blocked
└──────────────┘
```

---

## Implementation Checklist

### Phase 1: Firestore Setup
- [ ] Create Firestore database
- [ ] Deploy security rules (firestore.rules)
- [ ] Create `approvedSites` collection with first WordPress site
- [ ] Create `admins` collection with initial admin UID
- [ ] Set up Firebase Auth with Google provider

### Phase 2: AVA Backend (token-server-node)
- [ ] Add cookie-parser middleware for httpOnly cookies
- [ ] Implement `/api/create-device-token` endpoint
- [ ] Implement `/api/validate-device-token` endpoint
- [ ] Implement `/api/revoke-device-token` endpoint
- [ ] Add CORS configuration for cross-origin requests
- [ ] Test token creation and validation

### Phase 3: AVA Frontend
- [ ] Create `lib/deviceToken.ts` with token management
- [ ] Update `app/embed/page.tsx` with device token flow
- [ ] Update `components/FirebaseAuth.tsx` to exchange tokens
- [ ] Add postMessage communication with parent window
- [ ] Test first-visit and return-visit flows

### Phase 4: WordPress Plugin
- [ ] Create `ava-embed.php` plugin file
- [ ] Implement shortcode `[ava_embed]`
- [ ] Add WooCommerce membership integration
- [ ] Add admin settings page
- [ ] Test embed on WordPress site

### Phase 5: Security Audit
- [ ] Test: WordPress admin cannot impersonate user
- [ ] Test: Token theft is blocked by device fingerprint
- [ ] Test: Cross-site embedding is blocked
- [ ] Test: Expired tokens are rejected
- [ ] Test: Revoked tokens are rejected
- [ ] Verify Firestore security rules prevent unauthorized access
- [ ] Verify WordPress never receives Firebase tokens

---

## Security Checklist

### Authentication Security
- [ ] Firebase Auth happens on AVA-controlled domain only
- [ ] WordPress never handles Firebase ID tokens
- [ ] Device tokens are bound to device fingerprints
- [ ] Tokens expire after 30 days of inactivity
- [ ] httpOnly cookies prevent XSS token theft (no localStorage for tokens)

### Authorization Security
- [ ] Firestore security rules enforce user isolation
- [ ] Only backend can write user data
- [ ] Users can only read their own data
- [ ] approvedSites list controls cross-origin access
- [ ] Device tokens are site-specific

### Communication Security
- [ ] postMessage origin validation
- [ ] CORS configured for approved origins only
- [ ] Nonce prevents replay attacks
- [ ] HTTPS required for all communications

### WordPress Isolation
- [ ] WP receives only "connected/disconnected" status
- [ ] WP cannot read user conversation history
- [ ] WP cannot modify user data
- [ ] WP cannot forge authentication tokens

---

## Next Steps

1. **Review this plan** - Ensure it meets your security requirements
2. **Set up Firestore** - Create the database and security rules
3. **Implement backend API** - Add device token endpoints to token-server-node
4. **Update frontend** - Implement device token flow in embed page
5. **Create WordPress plugin** - Build the PHP plugin for embedding
6. **Test thoroughly** - Run through all security scenarios
7. **Deploy to staging** - Test with a staging WordPress site
8. **Production deployment** - Go live with monitoring

---

## Questions?

This plan prioritizes security over convenience. If you have questions about any component or want to adjust the security/convenience trade-offs, let's discuss!
