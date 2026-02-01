"use client";

import { useState, useEffect, useRef } from "react";
import { 
  signInWithPopup, 
  GoogleAuthProvider, 
  onAuthStateChanged, 
  User,
  signOut 
} from "firebase/auth";
import { auth } from "@/lib/firebase";
import { motion } from "framer-motion";

interface FirebaseAuthProps {
  onAuthenticated: (user: User) => void;
}

export default function FirebaseAuth({ onAuthenticated }: FirebaseAuthProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Store callback in ref to avoid re-subscribing on every render
  const onAuthenticatedRef = useRef(onAuthenticated);
  onAuthenticatedRef.current = onAuthenticated;

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (user) {
        onAuthenticatedRef.current(user);
      }
      setLoading(false);
    });

    return () => unsubscribe();
  }, []); // Empty deps - only subscribe once

  const loginWithGoogle = async () => {
    setLoading(true);
    setError(null);
    try {
      const provider = new GoogleAuthProvider();
      const result = await signInWithPopup(auth, provider);
      onAuthenticated(result.user);
    } catch (err: any) {
      console.error("Login failed:", err);
      setError(err.message || "Failed to log in with Google");
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-[#B9965B] font-heading text-xl">Loading...</div>
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
        <h2 className="text-3xl font-heading font-bold text-[#B9965B] mb-2">Welcome to AVA</h2>
        <p className="text-gray-600 mb-8 font-body">Sign in to start your conversation</p>
        
        {error && (
          <div className="mb-4 p-3 bg-red-50 text-red-600 text-sm rounded-lg border border-red-100">
            {error}
          </div>
        )}

        <button
          onClick={loginWithGoogle}
          className="w-full flex items-center justify-center gap-3 py-3 px-6 bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 rounded-lg font-body font-medium transition-all shadow-sm active:scale-[0.98]"
        >
          <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="Google" className="w-5 h-5" />
          Continue with Google
        </button>
        
        <p className="mt-6 text-xs text-gray-400 font-body">
          By signing in, you agree to our Terms and Privacy Policy.
        </p>
      </motion.div>
    </div>
  );
}
