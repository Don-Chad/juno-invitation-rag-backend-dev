"use client";

import { CloseIcon } from "@/components/CloseIcon";
import { NoAgentNotification } from "@/components/NoAgentNotification";
import PasswordAuth from "@/components/PasswordAuth";
import { CustomChat } from "@/components/CustomChat";
import {
  DisconnectButton,
  RoomContext,
  useVoiceAssistant,
  useRoomContext,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { AnimatePresence, motion } from "framer-motion";
import { Room, ConnectionState } from "livekit-client";
import { useCallback, useEffect, useState } from "react";
import type { ConnectionDetails } from "./api/connection-details/route";

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

export default function Page() {
  const [room] = useState(new Room());
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [userName, setUserName] = useState("");
  const [hasEnteredName, setHasEnteredName] = useState(false);

  // Check for existing session on mount
  useEffect(() => {
    const checkSession = async () => {
      const token = localStorage.getItem('grace_session_token');
      const expiresAt = localStorage.getItem('grace_session_expires');
      
      if (token && expiresAt) {
        // Check if token is still valid
        const expiryDate = new Date(expiresAt);
        if (expiryDate > new Date()) {
          try {
            const response = await fetch('/api/auth', {
              method: 'GET',
              headers: {
                'Authorization': `Bearer ${token}`
              }
            });
            
            if (response.ok) {
              setIsAuthenticated(true);
            } else {
              // Session invalid, clear storage
              localStorage.removeItem('grace_session_token');
              localStorage.removeItem('grace_session_expires');
            }
          } catch (error) {
            console.error('Session check failed:', error);
          }
        } else {
          // Session expired, clear storage
          localStorage.removeItem('grace_session_token');
          localStorage.removeItem('grace_session_expires');
        }
      }
      setIsCheckingAuth(false);
    };

    checkSession();
  }, []);

  const onConnectButtonClicked = useCallback(async () => {
    const url = new URL(
      process.env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT ?? "/api/connection-details",
      window.location.origin
    );
    if (userName) {
      url.searchParams.append("participantName", userName);
    }
    const response = await fetch(url.toString());
    const connectionDetailsData: ConnectionDetails = await response.json();

    await room.connect(connectionDetailsData.serverUrl, connectionDetailsData.participantToken);
  }, [room, userName]);

  // Show loading while checking authentication
  if (isCheckingAuth) {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-[#B9965B] font-heading text-xl">Checking authentication...</div>
      </div>
    );
  }

  // Show password authentication if not authenticated
  if (!isAuthenticated) {
    return <PasswordAuth onAuthenticated={() => setIsAuthenticated(true)} />;
  }

  // Show name input if authenticated but no name entered
  if (!hasEnteredName) {
    return (
      <div className="h-full min-h-[100svh] flex items-center justify-center bg-white relative">
        <div className="absolute inset-0 flex items-center justify-center z-0 overflow-hidden">
          <img 
            src="/background.png" 
            alt="AVA Background" 
            className="opacity-90 w-full h-full object-cover sm:object-contain"
            style={{ 
              imageRendering: 'crisp-edges'
            }}
          />
        </div>
        <motion.div 
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="z-10 bg-white/90 backdrop-blur-md p-6 sm:p-8 rounded-xl shadow-2xl border border-[#B9965B]/30 w-[calc(100%-2rem)] sm:w-96 text-center"
        >
          <h2 className="text-2xl font-heading font-bold text-[#B9965B] mb-6">Welcome to AVA</h2>
          <div className="space-y-4">
            <input
              type="text"
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              placeholder="What should I call you?"
              className="w-full px-4 py-3 rounded-lg bg-white border border-[#B9965B]/50 text-black placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#B9965B] font-body transition-all text-base"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && userName.trim()) {
                  setHasEnteredName(true);
                }
              }}
            />
            <button
              onClick={() => setHasEnteredName(true)}
              disabled={!userName.trim()}
              className="w-full py-3 px-6 bg-[#B9965B] hover:bg-[#a3844e] text-white rounded-lg font-heading font-medium tracking-wide transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md"
            >
              Continue
            </button>
          </div>
        </motion.div>
      </div>
    );
  }

  return (
    <main data-lk-theme="default" className="h-full min-h-[100svh] w-full flex flex-col bg-white relative overflow-hidden">
      <div className="absolute inset-0 flex items-center justify-center z-0 pointer-events-none">
        <img 
          src="/background.png" 
          alt="AVA Background" 
          className="opacity-90 w-full h-full object-cover sm:object-contain"
          style={{ 
            imageRendering: 'crisp-edges'
          }}
        />
      </div>
      <RoomContext.Provider value={room}>
        <div className="relative z-10 w-full h-full flex flex-col overflow-hidden">
          <SimpleChatAssistant onConnectButtonClicked={onConnectButtonClicked} userName={userName} />
        </div>
      </RoomContext.Provider>
    </main>
  );
}

function SimpleChatAssistant(props: { onConnectButtonClicked: () => void, userName: string }) {
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
                className="px-10 py-4 bg-[#B9965B] text-white rounded-full font-heading text-lg tracking-wider hover:bg-[#a3844e] transition-all shadow-xl hover:scale-105 active:scale-95 whitespace-nowrap"
                onClick={() => props.onConnectButtonClicked()}
              >
                Start Chatting
              </button>
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
              {/* Custom Header */}
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
                <div className="text-[#B9965B]/70 font-body text-xs sm:text-sm">Connected as {props.userName}</div>
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
