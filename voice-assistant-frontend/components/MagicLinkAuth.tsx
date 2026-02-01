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
      // Create search params for the redirect URL
      const searchParams = new URLSearchParams(window.location.search);
      const siteId = searchParams.get('site_id');
      
      const actionCodeSettings = {
        // Redirect back to the finishSignUp page
        url: `${window.location.origin}/embed/finishSignUp${siteId ? `?site_id=${siteId}` : ''}`,
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
            
            <div className="bg-gray-50 p-3 rounded-lg mb-6 font-mono text-sm text-gray-700 break-all">
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
              <strong className="break-all">{userEmail}</strong>
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
