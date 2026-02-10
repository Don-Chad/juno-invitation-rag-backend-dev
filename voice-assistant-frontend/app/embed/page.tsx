"use client";

import { NoAgentNotification } from "@/components/NoAgentNotification";
import MagicLinkAuth from "@/components/MagicLinkAuth";
import { auth } from "@/lib/firebase";
import { User, signOut, onAuthStateChanged, signInWithCustomToken } from "firebase/auth";
import { CustomChat } from "@/components/CustomChat";
import {
  RoomContext,
  useRoomContext,
  useVoiceAssistant,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { Room, ConnectionState } from "livekit-client";
import { useCallback, useEffect, useState, useRef } from "react";
import {
  validateDeviceToken,
  exchangeForDeviceToken,
  clearDeviceTokenInfo
} from "@/lib/deviceToken";

interface WordPressContext {
  siteId: string;
  userEmail: string;
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

function VoiceAssistantContent() {
  const { state } = useVoiceAssistant();
  return (
    <>
      <CustomChat />
      <NoAgentNotification state={state} />
    </>
  );
}

export default function EmbedPage() {
  const [roomKey, setRoomKey] = useState(0);
  const [room, setRoom] = useState<Room | null>(null);
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [isConnecting, setIsConnecting] = useState(false);
  const [subscriptionError, setSubscriptionError] = useState<{reason: string, email: string} | null>(null);
  const [authState, setAuthState] = useState<'checking' | 'needs_auth' | 'authenticated'>('checking');
  const [wpContext, setWpContext] = useState<WordPressContext | null>(null);
  const [handoffId, setHandoffId] = useState<string | null>(null);
  const didExchangeDeviceToken = useRef(false);
  const parentOrigin = useRef<string | null>(null);

  useEffect(() => {
    const newRoom = new Room();
    setRoom(newRoom);
    
    return () => {
      if (newRoom.state !== ConnectionState.Disconnected) {
        newRoom.disconnect().catch(console.error);
      }
    };
  }, [roomKey]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const siteId = params.get('site_id') || 'default';
    const userEmail = params.get('user_email') || '';

    // URL-based logout: /embed?action=logout
    if (params.get('action') === 'logout') {
      signOut(auth).then(() => {
        clearDeviceTokenInfo();
        // Remove the action param and reload clean
        params.delete('action');
        const clean = params.toString();
        window.location.replace(window.location.pathname + (clean ? '?' + clean : ''));
      });
      return;
    }
    
    setWpContext({ siteId, userEmail });

    // Create (or reuse) a handoff id for this embed session. This is used to
    // complete login inside the iframe after the user clicks the magic link in email.
    // It avoids relying on BroadcastChannel / shared Firebase storage, which can be
    // partitioned by the browser when embedded cross-site.
    try {
      const key = `ava_handoff_${siteId}`;
      const existing = sessionStorage.getItem(key);
      const fresh =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
      const id = existing || fresh;
      sessionStorage.setItem(key, id);
      setHandoffId(id);
    } catch (e) {
      console.warn('Failed to init handoff id:', e);
    }
    
    const handleParentMessage = (event: MessageEvent) => {
      parentOrigin.current = event.origin;
      if (event.data && event.data.type === 'ava:init') {
        setWpContext({
          siteId: event.data.siteId || 'default',
          userEmail: event.data.userEmail || ''
        });
      }
    };
    
    window.addEventListener('message', handleParentMessage);
    if (window.parent !== window) {
      window.parent.postMessage({ type: 'ava:ready' }, '*');
    }
    
    return () => window.removeEventListener('message', handleParentMessage);
  }, []);

  // Poll backend for handoff completion (magic link clicked in email).
  // When complete, we sign in *inside this iframe* using a Firebase custom token.
  useEffect(() => {
    if (authState !== 'needs_auth') return;
    if (!wpContext?.siteId || !handoffId) return;

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "https://token.makecontact.io";
    let cancelled = false;
    let attempts = 0;
    const startedAt = Date.now();
    // Keep trying for ~6 minutes max.
    const MAX_POLL_ATTEMPTS = 200;
    let delayMs = 1000;

    const jitter = (baseMs: number) => {
      // +/- 20% jitter to avoid synchronized thundering herd
      const delta = baseMs * 0.2;
      return Math.max(250, Math.round(baseMs + (Math.random() * 2 - 1) * delta));
    };

    const computeNextDelayMs = (elapsedMs: number, prevDelayMs: number, wasRateLimited: boolean) => {
      if (wasRateLimited) return 15000;
      // 0–15s: every 1s
      if (elapsedMs < 15_000) return 1000;
      // 15–60s: 2–5s (ramp up)
      if (elapsedMs < 60_000) {
        const t = (elapsedMs - 15_000) / 45_000; // 0..1
        return Math.round(2000 + t * 3000); // 2000..5000
      }
      // After 60s: backoff up to 10s
      return Math.min(10_000, Math.round(prevDelayMs * 1.5));
    };

    const tick = async () => {
      if (cancelled) return;
      attempts += 1;
      if (attempts > MAX_POLL_ATTEMPTS) return;
      const elapsedMs = Date.now() - startedAt;
      let wasRateLimited = false;

      try {
        const resp = await fetch(`${backendUrl}/api/auth-handoff/status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ handoffId, siteId: wpContext.siteId }),
        });
        if (resp.status === 429) {
          wasRateLimited = true;
          throw new Error('handoff status 429');
        }
        if (!resp.ok) throw new Error(`handoff status ${resp.status}`);
        const data = await resp.json();
        if (data?.complete && data?.customToken) {
          await signInWithCustomToken(auth, data.customToken);
          try { sessionStorage.removeItem(`ava_handoff_${wpContext.siteId}`); } catch {}
          return; // stop polling; onAuthStateChanged will take over
        }
      } catch (e) {
        // Non-blocking: just try again on next tick (with backoff)
      }

      delayMs = computeNextDelayMs(elapsedMs, delayMs, wasRateLimited);
      setTimeout(tick, jitter(delayMs));
    };

    const t = setTimeout(tick, 1000);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [authState, wpContext, handoffId]);

  useEffect(() => {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "https://token.makecontact.io";

    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (user) {
        setFirebaseUser(user);
        setAuthState('authenticated');
        setIsCheckingAuth(false);
        
        // Device token exchange is best-effort; don't block auth flow on failure
        if (wpContext && !didExchangeDeviceToken.current) {
          try {
            const idToken = await user.getIdToken();
            await exchangeForDeviceToken(backendUrl, idToken, wpContext.siteId);
            didExchangeDeviceToken.current = true;
          } catch (e) {
            console.warn('Device token exchange failed (non-blocking):', e);
          }
        }
      } else {
        // Firebase says no user. Try device token as a graceful fallback,
        // but don't let it block the UI — always resolve to needs_auth quickly.
        if (wpContext) {
          try {
            const validation = await validateDeviceToken(backendUrl, wpContext.siteId);
            if (validation.valid) {
              console.log('Device token valid, but Firebase session absent — showing auth UI');
            }
          } catch (e) {
            console.warn('Device token validation failed (non-blocking):', e);
          }
        }
        setAuthState('needs_auth');
        setIsCheckingAuth(false);
      }
    });

    // Listen for auth success from other tabs via BroadcastChannel
    let channel: BroadcastChannel | null = null;
    if (typeof BroadcastChannel !== 'undefined') {
      channel = new BroadcastChannel('ava_auth');
      channel.onmessage = (event) => {
        if (event.data.type === 'AUTH_SUCCESS') {
          // Firebase onAuthStateChanged will fire automatically on same-origin
          console.log('Auth success received from broadcast channel');
        }
      };
    }

    return () => {
      unsubscribe();
      if (channel) channel.close();
    };
  }, [wpContext]);

  const notifyParent = useCallback((status: 'connected' | 'disconnected' | 'error', error?: string) => {
    if (window.parent !== window && parentOrigin.current) {
      window.parent.postMessage({
        type: `ava:${status}`,
        timestamp: Date.now(),
        error
      }, parentOrigin.current);
    }
  }, []);

  const connectRetries = useRef(0);
  const MAX_RETRIES = 3;
  const RETRY_DELAY_MS = 10000;

  const onConnectButtonClicked = useCallback(async () => {
    if (!firebaseUser || !room || isConnecting) return;

    try {
      setIsConnecting(true);
      const idToken = await firebaseUser.getIdToken(true);
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "https://token.makecontact.io";
      
      const response = await fetch(`${backendUrl}/createToken`, {
        method: "POST",
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${idToken}`,
        },
      });

      if (response.status === 403) {
        const data = await response.json();
        if (data.message === 'Subscription Required') {
          setSubscriptionError({ reason: data.reason, email: data.email });
          return;
        }
      }

      if (!response.ok) {
        throw new Error(`Failed to get connection details: ${response.status}`);
      }

      const data = await response.json();
      await room.connect(data.serverUrl, data.participantToken);
      connectRetries.current = 0; // Reset on success
      notifyParent('connected');
    } catch (error) {
      console.error("Connection error:", error);
      notifyParent('error', error instanceof Error ? error.message : 'Unknown error');
      // Don't reset roomKey on every failure — that causes infinite loops
    } finally {
      setIsConnecting(false);
    }
  }, [firebaseUser, room, isConnecting, notifyParent]);

  // Auto-connect to room with retry logic (max 3 retries, 10s apart)
  useEffect(() => {
    if (authState !== 'authenticated' || !firebaseUser || !room || isConnecting) return;
    if (room.state !== ConnectionState.Disconnected) return;
    if (connectRetries.current >= MAX_RETRIES) {
      console.warn(`Gave up connecting after ${MAX_RETRIES} attempts.`);
      return;
    }

    const delay = connectRetries.current === 0 ? 0 : RETRY_DELAY_MS;
    const timer = setTimeout(() => {
      connectRetries.current += 1;
      console.log(`Connecting to room (attempt ${connectRetries.current}/${MAX_RETRIES})...`);
      onConnectButtonClicked();
    }, delay);

    return () => clearTimeout(timer);
  }, [authState, firebaseUser, room, isConnecting, onConnectButtonClicked]);

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
    return (
      <MagicLinkAuth
        userEmail={wpContext?.userEmail || ""}
        handoffId={handoffId || undefined}
        onAuthenticated={() => setAuthState('authenticated')}
      />
    );
  }

  if (subscriptionError) {
    return (
      <div className="h-full flex items-center justify-center bg-white p-8 text-center">
        <div className="max-w-sm">
          <div className="w-16 h-16 bg-amber-100 text-amber-600 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m0 0v2m0-2h2m-2 0h-2m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 className="text-2xl font-heading font-bold text-gray-800 mb-2">Abonnement Vereist</h2>
          <p className="text-gray-600 mb-6">
            Er is geen actief abonnement gevonden voor <strong>{subscriptionError.email}</strong>. 
            Neem contact op met de beheerder om toegang te krijgen.
          </p>
          <button
            onClick={handleLogout}
            className="text-[#B9965B] font-medium underline"
          >
            Inloggen met een ander account
          </button>
        </div>
      </div>
    );
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
        </div>
        
        <VoiceAssistantContent />
      </main>
    </RoomContext.Provider>
  );
}
