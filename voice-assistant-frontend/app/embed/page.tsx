"use client";

import { NoAgentNotification } from "@/components/NoAgentNotification";
import FirebaseAuth from "@/components/FirebaseAuth";
import MagicLinkAuth from "@/components/MagicLinkAuth";
import CookieConsent, { useStorageAccess } from "@/components/CookieConsent";
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
import { useCallback, useEffect, useState, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
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
  userEmail: string;
}

interface SubscriptionStatus {
  allowed: boolean;
  reason?: string;
  status?: string;
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

// Retry logic for subscription check (handles webhook race condition)
const checkSubscriptionWithRetry = async (
  tokenServerOrigin: string,
  idToken: string,
  maxRetries = 5
): Promise<SubscriptionStatus> => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      // Use the Token Server directly (port 3011)
      const url = new URL("/createToken", tokenServerOrigin);
      
      const checkRes = await fetch(url.toString(), {
        method: "POST",
        headers: { 
          'Authorization': `Bearer ${idToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      });
      
      if (checkRes.ok) {
        return { allowed: true };
      }
      
      if (checkRes.status === 403) {
        const data = await checkRes.json();
        if (data.message === 'Subscription Required' && i < maxRetries - 1) {
          await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
          continue;
        }
        return { allowed: false, reason: data.message };
      }
      
      throw new Error(`Check failed: ${checkRes.status}`);
    } catch (e) {
      if (i === maxRetries - 1) throw e;
      await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
    }
  }
  return { allowed: false, reason: 'Timeout' };
};

function EmbedContent() {
  const [roomKey, setRoomKey] = useState(0);
  const [room, setRoom] = useState<Room | null>(null);
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [isConnecting, setIsConnecting] = useState(false);
  const [authState, setAuthState] = useState<'checking' | 'needs_cookie_consent' | 'needs_auth' | 'activating' | 'subscription_required' | 'authenticated'>('checking');
  const [subscriptionError, setSubscriptionError] = useState<string | null>(null);
  const [wpContext, setWpContext] = useState<WordPressContext | null>(null);
  
  const searchParams = useSearchParams();
  const { hasStorageAccess, requestAccess } = useStorageAccess();
  const parentOrigin = useRef<string | null>(null);

  // Initialize Room
  useEffect(() => {
    const newRoom = new Room();
    setRoom(newRoom);
    return () => {
      if (newRoom.state !== ConnectionState.Disconnected) {
        newRoom.disconnect().catch(console.error);
      }
    };
  }, [roomKey]);

  // Parse WP Context
  useEffect(() => {
    const userEmail = searchParams.get('user_email');
    const siteId = searchParams.get('site_id');
    
    if (userEmail && siteId) {
      setWpContext({ userEmail, siteId });
    }
    
    // Notify parent
    if (window.parent !== window) {
      window.parent.postMessage({ type: 'ava:ready' }, '*');
    }
    
    const handleMessage = (e: MessageEvent) => {
      parentOrigin.current = e.origin;
      if (e.data?.type === 'ava:init') {
        setWpContext({ 
          userEmail: e.data.userEmail, 
          siteId: e.data.siteId 
        });
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [searchParams]);

  // Auth & Subscription Flow
  useEffect(() => {
    if (hasStorageAccess === false) {
      setAuthState('needs_cookie_consent');
      setIsCheckingAuth(false);
      return;
    }

    const checkAuth = async () => {
      const unsubscribe = auth.onAuthStateChanged(async (user) => {
        if (user) {
          handleAuthenticated(user);
        } else if (wpContext) {
          // Check for device token
          const tokenServerOrigin =
            process.env.NEXT_PUBLIC_TOKEN_SERVER_ORIGIN ||
            process.env.NEXT_PUBLIC_BACKEND_URL || // backwards-compat
            window.location.origin;
          
          try {
            const validation = await validateDeviceToken(tokenServerOrigin, wpContext.siteId);
            
            if (validation.valid && validation.uid) {
              // We have a valid device token, but Firebase doesn't know about it.
              // In this architecture, we still need the user to be signed into Firebase
              // for the LiveKit token server to verify them via ID token.
              // So we still show the MagicLinkAuth or FirebaseAuth.
              // BUT, if we wanted "Silent Re-auth", we'd need a way to sign into Firebase
              // using the device token (e.g. Custom Token from backend).
              
              // For now, let's stick to the plan: if no Firebase user, show auth.
              setAuthState('needs_auth');
              setIsCheckingAuth(false);
            } else {
              setAuthState('needs_auth');
              setIsCheckingAuth(false);
            }
          } catch (err) {
            console.warn("Silent login check failed (likely no token yet):", err);
            setAuthState('needs_auth');
            setIsCheckingAuth(false);
          }
        } else {
          setAuthState('needs_auth');
          setIsCheckingAuth(false);
        }
      });
      return () => unsubscribe();
    };

    if (hasStorageAccess === true) {
      checkAuth();
    }
  }, [hasStorageAccess, wpContext]);

  const notifyParent = useCallback((status: 'connected' | 'disconnected' | 'error', error?: string) => {
    if (window.parent !== window && parentOrigin.current) {
      window.parent.postMessage({
        type: `ava:${status}`,
        timestamp: Date.now(),
        error
      }, parentOrigin.current);
    }
  }, []);

  const handleAuthenticated = useCallback(async (user: User) => {
    setFirebaseUser(user);
    setAuthState('activating');
    
    try {
      const idToken = await user.getIdToken();
      const tokenServerOrigin =
        process.env.NEXT_PUBLIC_TOKEN_SERVER_ORIGIN ||
        process.env.NEXT_PUBLIC_BACKEND_URL || // backwards-compat
        window.location.origin;
      
      // 1. Exchange for device token if we have WP context
      if (wpContext) {
        await exchangeForDeviceToken(tokenServerOrigin, idToken, wpContext.siteId);
      }
      
      // 2. Check subscription with retry
      const sub = await checkSubscriptionWithRetry(tokenServerOrigin, idToken);
      
      if (!sub.allowed) {
        setAuthState('subscription_required');
        setSubscriptionError(sub.reason || 'Active subscription required');
        return;
      }
      
      setAuthState('authenticated');
      setIsCheckingAuth(false);
      notifyParent('connected');
    } catch (e) {
      console.error('Auth verification error:', e);
      setAuthState('subscription_required');
      setSubscriptionError('Failed to verify subscription. Please try again.');
      setIsCheckingAuth(false);
    }
  }, [wpContext, notifyParent]);

  const onConnectButtonClicked = useCallback(async () => {
    if (!firebaseUser || !room || isConnecting) return;

    try {
      setIsConnecting(true);
      const idToken = await firebaseUser.getIdToken(true);
      
      // Use the Token Server directly (port 3011) instead of the Next.js API proxy
      // This is required for 'output: export' mode because Next.js API routes are disabled.
      const tokenServerOrigin =
        process.env.NEXT_PUBLIC_TOKEN_SERVER_ORIGIN ||
        process.env.NEXT_PUBLIC_BACKEND_URL || // backwards-compat
        window.location.origin;
      const url = new URL("/createToken", tokenServerOrigin);
      
      const response = await fetch(url.toString(), {
        method: "POST",
        headers: { 
          'Authorization': `Bearer ${idToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to get connection details: ${response.statusText}`);
      }

      const data: ConnectionDetails = await response.json();
      await room.connect(data.serverUrl, data.participantToken);
      notifyParent('connected');
    } catch (error) {
      console.error("Connection failed:", error);
      alert("Failed to connect. Please try again.");
    } finally {
      setIsConnecting(false);
    }
  }, [room, firebaseUser, isConnecting, notifyParent]);

  const handleLogout = useCallback(async () => {
    if (room && room.state === ConnectionState.Connected) {
      await room.disconnect();
    }
    await signOut(auth);
    clearDeviceTokenInfo();
    setFirebaseUser(null);
    setAuthState('needs_auth');
    setRoomKey(prev => prev + 1);
    notifyParent('disconnected');
  }, [room, notifyParent]);

  if (isCheckingAuth || authState === 'checking') {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-[#B9965B] font-heading text-xl">Loading AVA...</div>
      </div>
    );
  }

  if (authState === 'needs_cookie_consent') {
    return <CookieConsent onGranted={() => window.location.reload()} />;
  }

  if (authState === 'needs_auth') {
    if (wpContext?.userEmail) {
      return <MagicLinkAuth userEmail={wpContext.userEmail} onAuthenticated={handleAuthenticated} />;
    }
    return <FirebaseAuth onAuthenticated={handleAuthenticated} />;
  }

  if (authState === 'activating') {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#B9965B] mx-auto mb-4"></div>
          <div className="text-[#B9965B] font-heading text-xl">Verifying Subscription...</div>
        </div>
      </div>
    );
  }

  if (authState === 'subscription_required') {
    return (
      <div className="h-full flex items-center justify-center bg-white p-6 text-center">
        <div>
          <h2 className="text-2xl font-heading text-red-600 mb-4">Subscription Required</h2>
          <p className="text-gray-600 mb-6">{subscriptionError}</p>
          <button 
            onClick={() => window.location.reload()}
            className="px-6 py-2 bg-[#B9965B] text-white rounded-lg"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!firebaseUser || !room) return null;

  return (
    <main data-lk-theme="default" className="h-full min-h-[100svh] w-full flex flex-col bg-white relative overflow-hidden">
      <div className="absolute inset-0 flex items-center justify-center z-0 pointer-events-none">
        <img 
          src="/background.png" 
          alt="AVA Background" 
          className="opacity-90 w-full h-full object-cover sm:object-contain"
          style={{ imageRendering: 'crisp-edges' }}
        />
      </div>
      <RoomContext.Provider value={room}>
        <div className="relative z-10 w-full h-full flex flex-col overflow-hidden">
          <SimpleChatAssistant 
            onConnectButtonClicked={onConnectButtonClicked} 
            userName={firebaseUser.displayName || firebaseUser.email?.split('@')[0] || "User"}
            onLogout={handleLogout}
            isConnecting={isConnecting}
          />
        </div>
      </RoomContext.Provider>
    </main>
  );
}

function SimpleChatAssistant(props: { onConnectButtonClicked: () => void, userName: string, onLogout: () => void, isConnecting: boolean }) {
  const { state: agentState } = useVoiceAssistant();
  
  return (
    <>
      <AnimatePresence>
        {agentState === "disconnected" && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.5 }}
            className="absolute inset-0 flex flex-col items-center justify-center text-center z-50 p-6"
          >
            <div className="max-w-sm">
              <h3 className="text-2xl font-heading text-[#B9965B] mb-6 drop-shadow-md">Hello, {props.userName}</h3>
              <button
                className={`px-10 py-4 bg-[#B9965B] text-white rounded-full font-heading text-lg tracking-wider transition-all shadow-xl whitespace-nowrap ${
                  props.isConnecting ? "opacity-70 cursor-not-allowed" : "hover:bg-[#a3844e] hover:scale-105 active:scale-95"
                }`}
                onClick={() => props.onConnectButtonClicked()}
                disabled={props.isConnecting}
              >
                {props.isConnecting ? "Connecting..." : "Start Chatting"}
              </button>
              {/* Logout disabled as per request */}
              {/* 
              <div className="mt-4">
                <button
                  className="px-6 py-2 text-[#B9965B] hover:text-[#a3844e] transition-all text-sm font-body underline"
                  onClick={props.onLogout}
                >
                  Logout
                </button>
              </div>
              */}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {agentState !== "disconnected" && (
          <motion.div 
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ 
              duration: 0.5, 
              ease: [0.16, 1, 0.3, 1],
              opacity: { duration: 0.3 }
            }}
            className="flex flex-col h-full w-full max-w-5xl mx-auto p-2 sm:p-4 items-center justify-center overflow-hidden"
          >
            <motion.div 
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              className="w-full rounded-lg overflow-hidden border border-[#B9965B] shadow-2xl backdrop-blur-sm flex flex-col flex-1 sm:flex-none sm:h-[800px] sm:min-h-[800px] bg-white/50" 
            >
              <motion.div 
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4, duration: 0.5 }}
                className="bg-[#B9965B]/10 border-b border-[#B9965B]/30 p-3 sm:p-4 flex justify-between items-center"
              >
                <div className="flex items-center gap-3">
                  <ConnectionIndicator />
                  <h2 className="text-[#B9965B] font-heading font-bold text-lg">AVA</h2>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-[#B9965B]/70 font-body text-xs sm:text-sm">Connected as {props.userName}</div>
                  {/* Logout disabled as per request */}
                  {/* 
                  <button
                    onClick={props.onLogout}
                    className="px-3 py-1 text-xs sm:text-sm text-[#B9965B] hover:text-white hover:bg-[#B9965B] border border-[#B9965B] rounded-md transition-all font-body"
                  >
                    Logout
                  </button>
                  */}
                </div>
              </motion.div>
              
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5, duration: 0.4 }}
                className="flex-1 overflow-hidden relative"
              >
                <CustomChat />
              </motion.div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <NoAgentNotification state={agentState} />
    </>
  );
}

export default function EmbedPage() {
  return (
    <Suspense fallback={<div className="h-full flex items-center justify-center">Loading...</div>}>
      <EmbedContent />
    </Suspense>
  );
}
