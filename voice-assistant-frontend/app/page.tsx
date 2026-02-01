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
  // Use state with a key to force re-creation of Room when needed
  const [roomKey, setRoomKey] = useState(0);
  const [room, setRoom] = useState<Room | null>(null);
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [isConnecting, setIsConnecting] = useState(false);

  // Create a fresh Room instance when roomKey changes
  useEffect(() => {
    const newRoom = new Room();
    setRoom(newRoom);
    
    // Cleanup: disconnect and dispose when creating new room or unmounting
    return () => {
      if (newRoom.state !== ConnectionState.Disconnected) {
        newRoom.disconnect().catch(console.error);
      }
    };
  }, [roomKey]);

  // Check for existing session on mount
  useEffect(() => {
    const unsubscribe = auth.onAuthStateChanged((user) => {
      // If user changes (and it's not the first load), reset the room
      if (firebaseUser && user && firebaseUser.uid !== user.uid) {
        setRoomKey(prev => prev + 1);
      }
      setFirebaseUser(user);
      setIsCheckingAuth(false);
    });
    return () => unsubscribe();
  }, [firebaseUser]);

  const onConnectButtonClicked = useCallback(async () => {
    if (!firebaseUser || !room || isConnecting) return;

    try {
      setIsConnecting(true);
      console.log("Connecting: fetching token for user", firebaseUser.uid);
      
      // Force refresh the token to ensure it's fresh (not cached)
      const idToken = await firebaseUser.getIdToken(true);
      
      // In production we run as `output: "export"` (static export), so Next.js API routes do not exist.
      // Call the Token Server directly.
      const url = new URL("http://178.156.186.166:3011/createToken");
      
      console.log("Connecting: calling token endpoint", url.toString());
      const response = await fetch(url.toString(), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${idToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error("Token fetch failed:", response.status, errorText);
        throw new Error(`Failed to get connection details: ${response.statusText}`);
      }

      const connectionDetailsData: ConnectionDetails = await response.json();
      console.log("Connecting: received details", {
        serverUrl: connectionDetailsData.serverUrl,
        roomName: connectionDetailsData.roomName,
        participantName: connectionDetailsData.participantName
      });

      console.log("Connecting: calling room.connect...");
      await room.connect(connectionDetailsData.serverUrl, connectionDetailsData.participantToken);
      console.log("Connecting: room.connect successful, state:", room.state);
    } catch (error) {
      console.error("Connection failed error:", error);
      alert("Failed to connect. Please try again.");
    } finally {
      setIsConnecting(false);
    }
  }, [room, firebaseUser, isConnecting]);

  const handleLogout = useCallback(async () => {
    try {
      // Disconnect from room if connected
      if (room && room.state === ConnectionState.Connected) {
        await room.disconnect();
      }
      // Reset room key to force creation of a fresh Room instance for next session
      setRoomKey(prev => prev + 1);
      // Sign out from Firebase
      await signOut(auth);
    } catch (error) {
      console.error("Logout failed:", error);
    }
  }, [room]);

  // Show loading while checking authentication or room not ready
  if (isCheckingAuth || !room) {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-[#B9965B] font-heading text-xl">Checking authentication...</div>
      </div>
    );
  }

  // Show Firebase authentication if not authenticated
  if (!firebaseUser) {
    return <FirebaseAuth onAuthenticated={(user) => setFirebaseUser(user)} />;
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
